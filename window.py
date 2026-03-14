import uuid
import calendar as _cal
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, Pango, GLib
from datetime import datetime, date, timedelta

import html as _html

from models import Course, ClassPeriod, Schedule, TimeScheme, HUST_SUMMER_PERIODS, HUST_WINTER_PERIODS
from storage import ScheduleStorage, SettingsStorage
from utils import (
    WEEKDAY_CN,
    sort_courses,
    get_today_courses,
    get_next_course,
    humanize_delta_minutes,
    calc_current_week,
    hhmm_to_minutes,
    is_course_active_this_week,
    is_course_ended,
    detect_conflicts,
    get_active_periods,
    parse_weeks,
    export_schedule_to_ics,
)

# ─────────────────────────── CSS ────────────────────────────────

_APP_CSS = """
/* ── Course cards (week grid) ─────────────────────────────────── */
.course-card {
    border-radius: 8px;
    padding: 4px 6px;
    min-height: 50px;
    margin: 2px;
}

/* ── Week grid ────────────────────────────────────────────────── */
.week-period-label {
    min-width: 40px;
    min-height: 50px;
}
.week-period-separator {
    background-image: repeating-linear-gradient(
        90deg,
        rgba(128,128,128,0.35) 0px,
        rgba(128,128,128,0.35) 4px,
        transparent 4px,
        transparent 8px
    );
    min-height: 1px;
}

/* ── Month calendar ───────────────────────────────────────────── */
.month-day-cell {
    min-width: 44px;
    min-height: 64px;
    border-radius: 8px;
    padding: 4px;
    margin: 1px;
}
.month-today-cell {
    background-color: alpha(@accent_color, 0.12);
}
.month-today-num {
    color: @accent_color;
    font-weight: bold;
}
.month-other-num {
    opacity: 0.6;
}

/* ── Mascot card ──────────────────────────────────────────────── */
.mascot-card {
    border-radius: 16px;
    padding: 14px 16px;
    background-color: alpha(@accent_color, 0.08);
    margin-bottom: 4px;
    min-height: 80px;
}
.mascot-card-urgent {
    background-color: alpha(#e5a50a, 0.14);
}
.mascot-card-warn {
    background-color: alpha(#ff7800, 0.12);
}
.mascot-card-happy {
    background-color: alpha(#33d17a, 0.12);
}
.mascot-card-accent {
    background-color: alpha(@accent_color, 0.14);
}
.mascot-emoji-bg {
    min-width: 52px;
    min-height: 52px;
    border-radius: 26px;
    background-color: alpha(@accent_color, 0.14);
}
.mascot-emoji {
    font-size: 26px;
}
.mascot-title {
    font-weight: bold;
}

/* ── Onboarding ───────────────────────────────────────────────── */
.onboarding-page {
    padding: 24px 16px;
}
.onboarding-icon {
    font-size: 52px;
    margin-bottom: 8px;
}
.onboarding-title {
    font-size: 20px;
    font-weight: bold;
    margin-bottom: 6px;
}
.onboarding-body {
    opacity: 0.8;
}
.dot-active {
    min-width: 10px;
    min-height: 10px;
    border-radius: 5px;
    background-color: @accent_color;
    margin: 0 4px;
}
.dot-inactive {
    min-width: 8px;
    min-height: 8px;
    border-radius: 4px;
    background-color: alpha(@accent_color, 0.35);
    margin: 0 4px;
}
"""

_CSS_LOADED = False
_CSS_CLASSES_REGISTERED: set = set()


def _load_app_css() -> None:
    global _CSS_LOADED
    if _CSS_LOADED:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(_APP_CSS)
    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    _CSS_LOADED = True


def _ensure_color_class(class_name: str, bg: str, fg: str) -> None:
    """Register a global CSS class for a course color, once per class name."""
    if class_name in _CSS_CLASSES_REGISTERED:
        return
    css = f".{class_name} {{ background-color: {bg}; color: {fg}; }}"
    provider = Gtk.CssProvider()
    provider.load_from_string(css)
    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10
        )
    _CSS_CLASSES_REGISTERED.add(class_name)


# ─────────────────────── Color palette ──────────────────────────

_COURSE_COLORS = [
    ("#3584e4", "#ffffff"),  # blue
    ("#e5a50a", "#000000"),  # amber
    ("#33d17a", "#000000"),  # green
    ("#ff7800", "#ffffff"),  # orange
    ("#9141ac", "#ffffff"),  # purple
    ("#ed333b", "#ffffff"),  # red
    ("#26a269", "#ffffff"),  # teal
    ("#986a44", "#ffffff"),  # brown
    ("#1b6acb", "#ffffff"),  # indigo
    ("#c64600", "#ffffff"),  # deep-orange
]


def _assign_colors(courses: list) -> dict:
    """Return {course_id: (bg, fg)} assigned deterministically by sorted id."""
    result = {}
    for i, c in enumerate(sorted(courses, key=lambda x: x.id)):
        result[c.id] = _COURSE_COLORS[i % len(_COURSE_COLORS)]
    return result


def _course_css_class(course_id: str) -> str:
    return "cc-" + course_id.replace("-", "")[:20]


# ─────────────────────── Mascot helper ──────────────────────────

def _get_mascot_info(
    courses: list,
    current_week: int | None,
    conflicts: list | None = None,
) -> tuple[str, str, str, bool]:
    """Return (emoji, message, extra_css_class, is_markup) for the mascot card.

    When *conflicts* is non-empty the message uses Pango markup (is_markup=True).
    All other messages are plain text (is_markup=False).
    """
    now = datetime.now()
    hour = now.hour

    if 5 <= hour < 12:
        greeting = "早上好"
    elif 12 <= hour < 14:
        greeting = "午安"
    elif 14 <= hour < 18:
        greeting = "下午好"
    elif 18 <= hour < 22:
        greeting = "晚上好"
    else:
        greeting = "夜深了"

    week_str = f"第 {current_week} 周 · " if current_week else ""
    today_name = WEEKDAY_CN.get(now.weekday() + 1, "")
    context = f"{week_str}{today_name}"

    # ── Conflict alert (highest priority) ───────────────────────
    if conflicts:
        ca, cb = conflicts[0]
        a_start = hhmm_to_minutes(ca.start)
        a_end   = hhmm_to_minutes(ca.end)
        b_start = hhmm_to_minutes(cb.start)
        b_end   = hhmm_to_minutes(cb.end)
        overlap_start = max(a_start, b_start)
        overlap_end   = min(a_end,   b_end)

        def _format_minutes(m: int) -> str:
            return f"{m // 60:02d}:{m % 60:02d}"

        name_a = _html.escape(ca.name)
        name_b = _html.escape(cb.name)
        msg = (
            f"Oops！课程撞车啦！\n"
            f"<b>{name_a}</b> 和 <b>{name_b}</b> 在 "
            f"{_format_minutes(overlap_start)} 到 {_format_minutes(overlap_end)} "
            f"之间安排冲突，请谨慎处理"
        )
        return ("⚠️", msg, "mascot-card-warn", True)

    if not courses:
        return (
            "🌟",
            f"{greeting}！添加几门课程，开始规划你的学期吧。\n{context}",
            "",
            False,
        )

    next_course, delta = get_next_course(courses)
    today_courses = get_today_courses(courses)

    if next_course and delta is not None:
        if delta == 0:
            return (
                "📚",
                f"{greeting}！「{next_course.name}」现在正在上课。\n{context}",
                "mascot-card-accent",
                False,
            )
        if delta < 30:
            return (
                "⏰",
                f"{greeting}！「{next_course.name}」还有 {delta} 分钟就要开始了，快准备一下！\n{context}",
                "mascot-card-urgent",
                False,
            )
        if delta < 90:
            return (
                "🎒",
                f"{greeting}！「{next_course.name}」再过 {humanize_delta_minutes(delta)} 开始，别迟到哦。\n{context}",
                "mascot-card-warn",
                False,
            )

    if not today_courses:
        return (
            "☕",
            f"{greeting}！今天没有课，好好休息一下吧。\n{context}",
            "mascot-card-happy",
            False,
        )

    if today_courses and next_course:
        return (
            "📅",
            f"{greeting}！今天还有 {len(today_courses)} 节课，"
            f"下一节「{next_course.name}」在 {next_course.start} 开始。\n{context}",
            "",
            False,
        )

    return ("🌟", f"{greeting}！祝你今天学习愉快！\n{context}", "mascot-card-happy", False)


# ─────────────────────── Period helpers ─────────────────────────

def _get_period_span(course: Course, periods: list) -> tuple:
    """
    Return (start_idx, span): the 0-based index of the first period
    contained in this course and how many consecutive periods it covers.
    Uses ±5 min tolerance so exact-match schedules always work.
    Returns (None, 0) when no periods match.
    """
    c_start = hhmm_to_minutes(course.start)
    c_end = hhmm_to_minutes(course.end)
    first = last = None
    for i, p in enumerate(periods):
        ps = hhmm_to_minutes(p.start)
        pe = hhmm_to_minutes(p.end)
        if (c_start - 5) <= ps and pe <= (c_end + 5):
            if first is None:
                first = i
            last = i
    if first is None:
        return None, 0
    return first, last - first + 1

# ─────────────────────────── helpers ────────────────────────────


def _periods_from_settings(settings: dict) -> list[ClassPeriod]:
    return [ClassPeriod.from_dict(p) for p in settings.get("class_periods", [])]


# ──────────────────────── Reusable picker widgets ───────────────


class DatePickerButton(Gtk.Box):
    """A button that shows a calendar popover for date selection.

    Usage::
        picker = DatePickerButton()
        picker.set_date("2024-09-01")  # or ""
        selected = picker.get_date()   # returns "YYYY-MM-DD" or ""
    """

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._date: str = ""

        self._btn = Gtk.MenuButton()
        self._btn.set_hexpand(True)
        self._btn.add_css_class("flat")

        self._label = Gtk.Label(label="选择日期")
        self._label.set_hexpand(True)
        self._label.set_xalign(0.0)
        self._btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._btn_box.append(Gtk.Image.new_from_icon_name("x-office-calendar-symbolic"))
        self._btn_box.append(self._label)
        self._btn.set_child(self._btn_box)

        # Calendar inside a popover
        self._calendar = Gtk.Calendar()
        self._calendar.set_margin_top(8)
        self._calendar.set_margin_bottom(8)
        self._calendar.set_margin_start(8)
        self._calendar.set_margin_end(8)
        self._calendar.connect("day-selected", self._on_day_selected)

        popover = Gtk.Popover()
        popover.set_child(self._calendar)
        self._btn.set_popover(popover)

        # Clear button
        clear_btn = Gtk.Button(icon_name="edit-clear-symbolic")
        clear_btn.set_tooltip_text("清除日期")
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", self._on_clear)

        self.append(self._btn)
        self.append(clear_btn)

    def _on_day_selected(self, cal: Gtk.Calendar) -> None:
        dt = cal.get_date()
        # GLib.DateTime uses 1-based month
        self._date = f"{dt.get_year():04d}-{dt.get_month():02d}-{dt.get_day_of_month():02d}"
        self._label.set_text(self._date)
        # Close the popover after selection
        popover = self._btn.get_popover()
        if popover:
            popover.popdown()

    def _on_clear(self, _btn) -> None:
        self._date = ""
        self._label.set_text("选择日期")

    def set_date(self, date_str: str) -> None:
        """Set date from 'YYYY-MM-DD' string (or "" to clear)."""
        self._date = date_str or ""
        if self._date:
            try:
                d = datetime.strptime(self._date, "%Y-%m-%d")
                gdt = GLib.DateTime.new_local(d.year, d.month, d.day, 0, 0, 0.0)
                self._calendar.select_day(gdt)
                self._label.set_text(self._date)
            except Exception:
                self._date = ""
                self._label.set_text("选择日期")
        else:
            self._label.set_text("选择日期")

    def get_date(self) -> str:
        """Return selected date as 'YYYY-MM-DD', or '' if none."""
        return self._date


class TimePickerBox(Gtk.Box):
    """Inline hour (0–23) + minute (0–59) spinner for HH:MM time input.

    Usage::
        picker = TimePickerBox()
        picker.set_time("08:00")
        hhmm = picker.get_time()   # "HH:MM"
    """

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.set_valign(Gtk.Align.CENTER)

        adj_h = Gtk.Adjustment(value=8, lower=0, upper=23, step_increment=1, page_increment=1)
        self._hour_spin = Gtk.SpinButton(adjustment=adj_h, climb_rate=1, digits=0)
        self._hour_spin.set_wrap(True)
        self._hour_spin.set_width_chars(2)
        self._hour_spin.set_numeric(True)

        sep = Gtk.Label(label=":")
        sep.add_css_class("dim-label")

        adj_m = Gtk.Adjustment(value=0, lower=0, upper=59, step_increment=1, page_increment=5)
        self._min_spin = Gtk.SpinButton(adjustment=adj_m, climb_rate=1, digits=0)
        self._min_spin.set_wrap(True)
        self._min_spin.set_width_chars(2)
        self._min_spin.set_numeric(True)

        # Format output as zero-padded 2-digit numbers
        self._hour_spin.connect("output", self._format_spin)
        self._min_spin.connect("output", self._format_spin)

        self.append(self._hour_spin)
        self.append(sep)
        self.append(self._min_spin)

    @staticmethod
    def _format_spin(spin: Gtk.SpinButton) -> bool:
        spin.set_text(f"{int(spin.get_value()):02d}")
        return True

    def set_time(self, hhmm: str) -> None:
        """Set time from 'HH:MM' string."""
        try:
            h, m = hhmm.split(":")
            self._hour_spin.set_value(int(h))
            self._min_spin.set_value(int(m))
        except Exception:
            self._hour_spin.set_value(8)
            self._min_spin.set_value(0)

    def get_time(self) -> str:
        """Return time as 'HH:MM'."""
        h = int(self._hour_spin.get_value())
        m = int(self._min_spin.get_value())
        return f"{h:02d}:{m:02d}"


# ────────────────────────── dialogs ─────────────────────────────


class CourseDialog(Gtk.Dialog):
    """Add / edit a single course.  Provides a period quick-picker."""

    def __init__(self, parent: Gtk.Window, course: Course | None = None,
                 class_periods: list[ClassPeriod] | None = None):
        super().__init__(
            title="添加课程" if course is None else "编辑课程",
            modal=True, transient_for=parent,
        )
        self.set_default_size(440, 480)
        self.course = course
        self._periods = class_periods or []

        self.add_button("取消", Gtk.ResponseType.CANCEL)
        self.add_button("保存", Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)

        self.name_entry = Gtk.Entry(placeholder_text="例如：高等数学")
        self.location_entry = Gtk.Entry(placeholder_text="例如：A-203")
        self.teacher_entry = Gtk.Entry(placeholder_text="例如：张老师")
        self.weeks_entry = Gtk.Entry(placeholder_text="例如：1-20")
        self.day_combo = Gtk.DropDown.new_from_strings(
            [WEEKDAY_CN[i] for i in range(1, 8)]
        )
        # Time pickers replace free-text entries
        self.start_picker = TimePickerBox()
        self.end_picker = TimePickerBox()
        self.end_picker.set_time("09:35")

        # Period quick-picker ──────────────────────────────────────
        period_labels = ["自定义"] + [p.label() for p in self._periods]
        self.start_period_combo = Gtk.DropDown.new_from_strings(period_labels)
        self.end_period_combo = Gtk.DropDown.new_from_strings(period_labels)
        self.start_period_combo.connect("notify::selected", self._on_period_changed)
        self.end_period_combo.connect("notify::selected", self._on_period_changed)

        self.error_label = Gtk.Label(xalign=0)
        self.error_label.add_css_class("error")
        self.error_label.set_visible(False)

        row = 0
        grid.attach(Gtk.Label(label="课程名", xalign=0), 0, row, 1, 1)
        grid.attach(self.name_entry, 1, row, 1, 1)
        row += 1
        grid.attach(Gtk.Label(label="星期", xalign=0), 0, row, 1, 1)
        grid.attach(self.day_combo, 1, row, 1, 1)
        row += 1
        # Period pickers
        grid.attach(Gtk.Label(label="开始节次", xalign=0), 0, row, 1, 1)
        grid.attach(self.start_period_combo, 1, row, 1, 1)
        row += 1
        grid.attach(Gtk.Label(label="结束节次", xalign=0), 0, row, 1, 1)
        grid.attach(self.end_period_combo, 1, row, 1, 1)
        row += 1
        # Time pickers (spinners for H:M)
        grid.attach(Gtk.Label(label="开始时间", xalign=0), 0, row, 1, 1)
        grid.attach(self.start_picker, 1, row, 1, 1)
        row += 1
        grid.attach(Gtk.Label(label="结束时间", xalign=0), 0, row, 1, 1)
        grid.attach(self.end_picker, 1, row, 1, 1)
        row += 1
        grid.attach(Gtk.Label(label="地点", xalign=0), 0, row, 1, 1)
        grid.attach(self.location_entry, 1, row, 1, 1)
        row += 1
        grid.attach(Gtk.Label(label="教师", xalign=0), 0, row, 1, 1)
        grid.attach(self.teacher_entry, 1, row, 1, 1)
        row += 1
        grid.attach(Gtk.Label(label="周次", xalign=0), 0, row, 1, 1)
        grid.attach(self.weeks_entry, 1, row, 1, 1)
        row += 1
        grid.attach(self.error_label, 0, row, 2, 1)

        content.append(grid)

        if course:
            self.name_entry.set_text(course.name)
            self.day_combo.set_selected(course.day - 1)
            self.start_picker.set_time(course.start)
            self.end_picker.set_time(course.end)
            self.location_entry.set_text(course.location)
            self.teacher_entry.set_text(course.teacher)
            self.weeks_entry.set_text(course.weeks)

    # ── period picker callbacks ──────────────────────────────────

    def _on_period_changed(self, combo, _param):
        idx = combo.get_selected()
        is_start = combo is self.start_period_combo
        picker = self.start_picker if is_start else self.end_picker

        if idx == 0 or idx > len(self._periods):
            # "自定义" selected — re-enable manual editing
            picker.set_sensitive(True)
            return

        # Non-custom period selected — fill time and lock the picker
        period = self._periods[idx - 1]
        picker.set_time(period.start if is_start else period.end)
        picker.set_sensitive(False)

    # ── public ──────────────────────────────────────────────────

    def get_course_data(self) -> Course | None:
        name = self.name_entry.get_text().strip()
        day = self.day_combo.get_selected() + 1
        start = self.start_picker.get_time()
        end = self.end_picker.get_time()
        location = self.location_entry.get_text().strip()
        teacher = self.teacher_entry.get_text().strip()
        weeks = self.weeks_entry.get_text().strip() or "1-20"

        if not name:
            self.error_label.set_text("课程名不能为空")
            self.error_label.set_visible(True)
            return None

        cid = self.course.id if self.course else str(uuid.uuid4())
        return Course(
            id=cid, name=name, day=day,
            start=start, end=end,
            location=location, teacher=teacher, weeks=weeks,
        )


class ScheduleDialog(Gtk.Dialog):
    """Add / edit a schedule (name + term info)."""

    def __init__(self, parent: Gtk.Window, schedule: Schedule | None = None):
        title = "新建课表" if schedule is None else "编辑课表"
        super().__init__(title=title, modal=True, transient_for=parent)
        self.set_default_size(380, 220)
        self.schedule = schedule

        self.add_button("取消", Gtk.ResponseType.CANCEL)
        self.add_button("保存", Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)

        self.name_entry = Gtk.Entry(placeholder_text="例如：2024-2025 秋季学期")
        # Calendar date picker replaces free-text YYYY-MM-DD entry
        self.date_picker = DatePickerButton()
        self.total_weeks = Gtk.SpinButton.new_with_range(1, 40, 1)
        self.total_weeks.set_value(20.0)

        self.error_label = Gtk.Label(xalign=0)
        self.error_label.add_css_class("error")
        self.error_label.set_visible(False)

        grid.attach(Gtk.Label(label="课表名称", xalign=0),   0, 0, 1, 1)
        grid.attach(self.name_entry,                          1, 0, 1, 1)
        grid.attach(Gtk.Label(label="学期开始日期", xalign=0), 0, 1, 1, 1)
        grid.attach(self.date_picker,                         1, 1, 1, 1)
        grid.attach(Gtk.Label(label="总周数", xalign=0),     0, 2, 1, 1)
        grid.attach(self.total_weeks,                         1, 2, 1, 1)
        grid.attach(self.error_label,                         0, 3, 2, 1)
        content.append(grid)

        if schedule:
            self.name_entry.set_text(schedule.name)
            self.date_picker.set_date(schedule.term_start_date)
            self.total_weeks.set_value(float(schedule.total_weeks))

    def get_data(self) -> dict | None:
        name = self.name_entry.get_text().strip()
        start = self.date_picker.get_date()
        total = int(self.total_weeks.get_value())

        if not name:
            self.error_label.set_text("课表名称不能为空")
            self.error_label.set_visible(True)
            return None
        return {"name": name, "term_start_date": start, "total_weeks": total}


class ClassPeriodsDialog(Gtk.Dialog):
    """Edit the list of class-period time slots (global setting).

    Each period is shown as a row with interactive time spinners.
    Preset buttons for HUST 夏令时 and 冬令时 are provided.
    """

    def __init__(self, parent: Gtk.Window, class_periods: list[ClassPeriod]):
        super().__init__(title="节次时间设置", modal=True, transient_for=parent)
        self.set_default_size(420, 520)

        self.add_button("取消", Gtk.ResponseType.CANCEL)
        self.add_button("保存", Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        # ── Preset buttons (HUST 夏令时 / 冬令时) ──────────────────
        preset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        preset_lbl = Gtk.Label(label="预设：")
        preset_lbl.add_css_class("dim-label")
        preset_box.append(preset_lbl)

        summer_btn = Gtk.Button(label="华中科技大学 夏令时")
        summer_btn.add_css_class("pill")
        summer_btn.connect("clicked", self._on_preset_summer)
        preset_box.append(summer_btn)

        winter_btn = Gtk.Button(label="华中科技大学 冬令时")
        winter_btn.add_css_class("pill")
        winter_btn.connect("clicked", self._on_preset_winter)
        preset_box.append(winter_btn)

        outer.append(preset_box)

        # ── Scrollable list of period rows ─────────────────────────
        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.add_css_class("boxed-list")

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(self._list_box)
        outer.append(sw)

        # ── "Add period" button ────────────────────────────────────
        add_btn = Gtk.Button(label="＋ 添加节次")
        add_btn.add_css_class("pill")
        add_btn.connect("clicked", self._on_add_period)
        outer.append(add_btn)

        self.error_label = Gtk.Label(xalign=0, wrap=True)
        self.error_label.add_css_class("error")
        self.error_label.set_visible(False)
        outer.append(self.error_label)

        content.append(outer)

        # Populate rows from existing periods
        self._rows: list[tuple[TimePickerBox, TimePickerBox]] = []
        for p in class_periods:
            self._append_row(p.start, p.end)

    # ── internal helpers ─────────────────────────────────────────

    @staticmethod
    def _period_label(n: int) -> str:
        return f"第 {n} 节"

    def _append_row(self, start: str = "08:00", end: str = "08:50") -> None:
        idx = len(self._rows) + 1

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_box.set_margin_top(6)
        row_box.set_margin_bottom(6)
        row_box.set_margin_start(8)
        row_box.set_margin_end(8)

        num_lbl = Gtk.Label(label=self._period_label(idx))
        num_lbl.set_width_chars(6)
        num_lbl.set_xalign(0.0)
        row_box.append(num_lbl)

        start_picker = TimePickerBox()
        start_picker.set_time(start)
        row_box.append(start_picker)

        sep_lbl = Gtk.Label(label="–")
        sep_lbl.add_css_class("dim-label")
        row_box.append(sep_lbl)

        end_picker = TimePickerBox()
        end_picker.set_time(end)
        row_box.append(end_picker)

        # Delete button
        del_btn = Gtk.Button(icon_name="user-trash-symbolic")
        del_btn.add_css_class("flat")
        del_btn.add_css_class("destructive-action")
        del_btn.set_tooltip_text("删除此节次")
        row_pair = (start_picker, end_picker)
        del_btn.connect("clicked", self._on_delete_row, row_pair)
        row_box.append(del_btn)

        list_row = Gtk.ListBoxRow()
        list_row.set_child(row_box)
        self._list_box.append(list_row)
        self._rows.append(row_pair)

    def _reload_rows(self, periods: list[dict]) -> None:
        """Replace all rows with the given period list."""
        # Remove all existing rows
        child = self._list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._list_box.remove(child)
            child = nxt
        self._rows.clear()
        for p in periods:
            self._append_row(p["start"], p["end"])

    # ── callbacks ────────────────────────────────────────────────

    def _on_add_period(self, _btn) -> None:
        self._append_row()

    def _on_delete_row(self, _btn, row_pair: tuple) -> None:
        idx = self._rows.index(row_pair)
        self._rows.pop(idx)
        # Remove from list box
        lbrow = self._list_box.get_row_at_index(idx)
        if lbrow:
            self._list_box.remove(lbrow)
        # Renumber remaining rows
        self._renumber_rows()

    def _renumber_rows(self) -> None:
        child = self._list_box.get_first_child()
        n = 1
        while child:
            row_box = child.get_child()
            if row_box:
                first_child = row_box.get_first_child()
                if isinstance(first_child, Gtk.Label):
                    first_child.set_text(self._period_label(n))
            child = child.get_next_sibling()
            n += 1

    def _on_preset_summer(self, _btn) -> None:
        self._reload_rows(HUST_SUMMER_PERIODS)

    def _on_preset_winter(self, _btn) -> None:
        self._reload_rows(HUST_WINTER_PERIODS)

    # ── public ──────────────────────────────────────────────────

    def get_periods(self) -> list[ClassPeriod] | None:
        periods: list[ClassPeriod] = []
        for idx, (sp, ep) in enumerate(self._rows, start=1):
            start = sp.get_time()
            end = ep.get_time()
            periods.append(ClassPeriod(period=idx, start=start, end=end))
        return periods


class TimeSchemeEditDialog(Gtk.Dialog):
    """Add or edit a single time scheme (令时方案)."""

    def __init__(self, parent: Gtk.Window, scheme: "TimeScheme | None" = None):
        title = "新建时间方案" if scheme is None else "编辑时间方案"
        super().__init__(title=title, modal=True, transient_for=parent)
        self.set_default_size(420, 300)

        self._periods: list[ClassPeriod] = list(scheme.periods) if scheme else []

        self.add_button("取消", Gtk.ResponseType.CANCEL)
        ok = self.add_button("保存", Gtk.ResponseType.OK)
        ok.add_css_class("suggested-action")

        content = self.get_content_area()
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(14)
        content.set_margin_end(14)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)

        # Name
        self._name_entry = Gtk.Entry(placeholder_text="例如：夏令时")
        if scheme:
            self._name_entry.set_text(scheme.name)
        grid.attach(Gtk.Label(label="方案名称", xalign=0), 0, 0, 1, 1)
        grid.attach(self._name_entry, 1, 0, 1, 1)

        # date_from
        self._from_entry = Gtk.Entry(placeholder_text="MM-DD，留空则无限制")
        if scheme:
            self._from_entry.set_text(scheme.date_from)
        grid.attach(Gtk.Label(label="生效开始（MM-DD）", xalign=0), 0, 1, 1, 1)
        grid.attach(self._from_entry, 1, 1, 1, 1)

        # date_to
        self._to_entry = Gtk.Entry(placeholder_text="MM-DD，留空则无限制")
        if scheme:
            self._to_entry.set_text(scheme.date_to)
        grid.attach(Gtk.Label(label="生效结束（MM-DD）", xalign=0), 0, 2, 1, 1)
        grid.attach(self._to_entry, 1, 2, 1, 1)

        # Period count indicator + edit button
        self._periods_lbl = Gtk.Label(xalign=0)
        self._update_periods_lbl()
        edit_periods_btn = Gtk.Button(label="设置节次时间…")
        edit_periods_btn.add_css_class("pill")
        edit_periods_btn.connect("clicked", self._on_edit_periods)
        periods_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        periods_box.append(self._periods_lbl)
        periods_box.append(edit_periods_btn)
        grid.attach(Gtk.Label(label="节次时间表", xalign=0), 0, 3, 1, 1)
        grid.attach(periods_box, 1, 3, 1, 1)

        self._error_lbl = Gtk.Label(xalign=0, wrap=True)
        self._error_lbl.add_css_class("error")
        self._error_lbl.set_visible(False)
        grid.attach(self._error_lbl, 0, 4, 2, 1)

        content.append(grid)

    def _update_periods_lbl(self) -> None:
        n = len(self._periods)
        self._periods_lbl.set_text(f"已配置 {n} 节" if n else "（未配置，使用全局设置）")

    def _on_edit_periods(self, _btn) -> None:
        dlg = ClassPeriodsDialog(self, self._periods)

        def on_response(d, response):
            if response == Gtk.ResponseType.OK:
                result = d.get_periods()
                if result is not None:
                    self._periods = result
                    self._update_periods_lbl()
            d.close()

        dlg.connect("response", on_response)
        dlg.present()

    def get_scheme(self) -> "TimeScheme | None":
        name = self._name_entry.get_text().strip()
        if not name:
            self._error_lbl.set_text("方案名称不能为空")
            self._error_lbl.set_visible(True)
            return None
        date_from = self._from_entry.get_text().strip()
        date_to   = self._to_entry.get_text().strip()
        return TimeScheme(
            name=name,
            date_from=date_from,
            date_to=date_to,
            periods=list(self._periods),
        )


class TimeSchemesDialog(Gtk.Dialog):
    """Manage the list of named time schemes (令时方案).

    Each scheme can have a date range (MM-DD to MM-DD) so the app
    automatically selects the correct period table by today's date.
    """

    def __init__(self, parent: Gtk.Window, schemes: list):
        super().__init__(title="管理时间方案（令时）", modal=True,
                         transient_for=parent)
        self.set_default_size(480, 420)

        self._schemes: list[TimeScheme] = list(schemes)

        self.add_button("关闭", Gtk.ResponseType.CLOSE)

        content = self.get_content_area()
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(14)
        content.set_margin_end(14)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        hint = Gtk.Label(
            label=(
                "可添加多个时间方案（如夏令时、冬令时），系统会根据今天日期自动选择当前方案。\n"
                "若均未配置日期范围，则使用第一个有节次的方案；否则回退到全局节次设置。"
            ),
            xalign=0, wrap=True,
        )
        hint.add_css_class("dim-label")
        outer.append(hint)

        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.add_css_class("boxed-list")
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(self._list_box)
        outer.append(sw)

        add_btn = Gtk.Button(label="＋ 添加方案")
        add_btn.add_css_class("pill")
        add_btn.connect("clicked", self._on_add)
        outer.append(add_btn)

        content.append(outer)
        self._rebuild_list()

    # ── internals ─────────────────────────────────────────────

    def _rebuild_list(self) -> None:
        child = self._list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._list_box.remove(child)
            child = nxt

        for i, scheme in enumerate(self._schemes):
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row_box.set_margin_top(6)
            row_box.set_margin_bottom(6)
            row_box.set_margin_start(8)
            row_box.set_margin_end(8)

            name_lbl = Gtk.Label(label=scheme.name)
            name_lbl.set_hexpand(True)
            name_lbl.set_xalign(0.0)

            date_parts = []
            if scheme.date_from and scheme.date_to:
                date_parts.append(f"{scheme.date_from} → {scheme.date_to}")
            elif scheme.date_from or scheme.date_to:
                date_parts.append(scheme.date_from or scheme.date_to)
            date_parts.append(f"{len(scheme.periods)} 节")
            sub_lbl = Gtk.Label(label=" · ".join(date_parts))
            sub_lbl.add_css_class("caption")
            sub_lbl.add_css_class("dim-label")
            sub_lbl.set_xalign(0.0)

            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            info_box.set_hexpand(True)
            info_box.append(name_lbl)
            info_box.append(sub_lbl)
            row_box.append(info_box)

            edit_btn = Gtk.Button(icon_name="document-edit-symbolic")
            edit_btn.add_css_class("flat")
            edit_btn.set_tooltip_text("编辑")
            edit_btn.connect("clicked", self._on_edit, i)
            row_box.append(edit_btn)

            del_btn = Gtk.Button(icon_name="user-trash-symbolic")
            del_btn.add_css_class("flat")
            del_btn.add_css_class("destructive-action")
            del_btn.set_tooltip_text("删除")
            del_btn.connect("clicked", self._on_delete, i)
            row_box.append(del_btn)

            lbrow = Gtk.ListBoxRow()
            lbrow.set_child(row_box)
            self._list_box.append(lbrow)

    def _on_add(self, _btn) -> None:
        dlg = TimeSchemeEditDialog(self)

        def on_response(d, response):
            if response == Gtk.ResponseType.OK:
                scheme = d.get_scheme()
                if scheme:
                    self._schemes.append(scheme)
                    self._rebuild_list()
            d.close()

        dlg.connect("response", on_response)
        dlg.present()

    def _on_edit(self, _btn, idx: int) -> None:
        dlg = TimeSchemeEditDialog(self, self._schemes[idx])

        def on_response(d, response):
            if response == Gtk.ResponseType.OK:
                scheme = d.get_scheme()
                if scheme:
                    self._schemes[idx] = scheme
                    self._rebuild_list()
            d.close()

        dlg.connect("response", on_response)
        dlg.present()

    def _on_delete(self, _btn, idx: int) -> None:
        del self._schemes[idx]
        self._rebuild_list()

    def get_schemes(self) -> list[TimeScheme]:
        return list(self._schemes)


class GlobalSettingsDialog(Gtk.Dialog):
    """Global settings: color scheme + class periods."""

    _COLOR_SCHEMES = ["auto", "light", "dark"]
    _SCHEME_LABELS = ["跟随系统（自动）", "浅色模式", "深色模式"]

    def __init__(self, parent: Gtk.Window, settings: dict):
        super().__init__(title="全局设置", modal=True, transient_for=parent)
        self.set_default_size(320, 160)
        self._parent = parent
        self._settings = settings

        self.add_button("关闭", Gtk.ResponseType.CLOSE)

        content = self.get_content_area()
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        # Color scheme ─────────────────────────────────────────────
        scheme_group = Adw.PreferencesGroup(title="外观")
        color_options = Gtk.StringList()
        for opt in self._SCHEME_LABELS:
            color_options.append(opt)
        current_scheme = settings.get("color_scheme", "auto")
        self._scheme_row = Adw.ComboRow(title="配色方案")
        self._scheme_row.set_model(color_options)
        self._scheme_row.set_selected(
            self._COLOR_SCHEMES.index(current_scheme)
            if current_scheme in self._COLOR_SCHEMES else 0
        )
        self._scheme_row.connect("notify::selected", self._on_scheme_changed)
        scheme_group.add(self._scheme_row)
        box.append(scheme_group)

        # Class periods ────────────────────────────────────────────
        periods_group = Adw.PreferencesGroup(title="节次时间")
        edit_periods_btn = Gtk.Button(icon_name="document-edit-symbolic")
        edit_periods_btn.set_tooltip_text("编辑节次时间…")
        edit_periods_btn.add_css_class("flat")
        edit_periods_btn.set_valign(Gtk.Align.CENTER)
        edit_periods_btn.connect("clicked", self._on_edit_periods)
        periods_row = Adw.ActionRow(title="自定义上课节次时间段")
        periods_row.add_suffix(edit_periods_btn)
        periods_group.add(periods_row)
        box.append(periods_group)

        # Time schemes ─────────────────────────────────────────────
        schemes_group = Adw.PreferencesGroup(title="时间方案（令时）")
        active_name = self._active_scheme_name()
        manage_btn = Gtk.Button(icon_name="document-edit-symbolic")
        manage_btn.set_tooltip_text("管理时间方案…")
        manage_btn.add_css_class("flat")
        manage_btn.set_valign(Gtk.Align.CENTER)
        manage_btn.connect("clicked", self._on_manage_schemes)
        schemes_row = Adw.ActionRow(
            title="管理时间方案",
            subtitle=f"当前生效：{active_name}",
        )
        schemes_row.add_suffix(manage_btn)
        schemes_group.add(schemes_row)
        box.append(schemes_group)

        content.append(box)

    def _active_scheme_name(self) -> str:
        from utils import get_active_periods
        schemes_raw = self._settings.get("time_schemes", [])
        if not schemes_raw:
            return "全局节次设置"
        from datetime import date as _date
        today = _date.today()
        for s in schemes_raw:
            scheme = TimeScheme.from_dict(s)
            if scheme.periods and scheme.is_active_on(today):
                return scheme.name
        return "全局节次设置"

    def _on_scheme_changed(self, row, _param):
        idx = row.get_selected()
        if 0 <= idx < len(self._COLOR_SCHEMES):
            scheme = self._COLOR_SCHEMES[idx]
            self._settings["color_scheme"] = scheme
            self._parent.on_color_scheme_changed(scheme)

    def _on_edit_periods(self, _btn):
        periods = _periods_from_settings(self._settings)
        dlg = ClassPeriodsDialog(self, periods)

        def on_response(d, response):
            if response == Gtk.ResponseType.OK:
                new_periods = d.get_periods()
                if new_periods is not None:
                    self._settings["class_periods"] = [p.to_dict() for p in new_periods]
                    self._parent.on_periods_changed(self._settings["class_periods"])
                    d.close()
            else:
                d.close()

        dlg.connect("response", on_response)
        dlg.present()

    def _on_manage_schemes(self, _btn):
        schemes = [TimeScheme.from_dict(s) for s in self._settings.get("time_schemes", [])]
        dlg = TimeSchemesDialog(self, schemes)

        def on_response(d, _response):
            new_schemes = d.get_schemes()
            self._settings["time_schemes"] = [s.to_dict() for s in new_schemes]
            self._parent.on_time_schemes_changed(self._settings["time_schemes"])
            d.close()

        dlg.connect("response", on_response)
        dlg.present()


# ──────────────────────────── Onboarding Dialog ─────────────────


class OnboardingDialog(Gtk.Dialog):
    """First-time user guide shown on first launch."""

    _STEPS = [
        {
            "emoji": "🎓",
            "title": "欢迎使用 WadwaitaUp！",
            "body": (
                "这是一款专为大学生设计的课程表管理应用。\n"
                "轻松管理你的课程，再也不会忘记上课！"
            ),
        },
        {
            "emoji": "📅",
            "title": "创建你的课表",
            "body": (
                "点击右上角的📁按钮新建课表，\n"
                "输入学期名称和学期开始日期即可。\n"
                "你可以为不同学期创建多个课表。"
            ),
        },
        {
            "emoji": "📚",
            "title": "添加或导入课程",
            "body": (
                "点击右上角的 ＋ 按钮手动添加课程，\n"
                "或使用「导入课程」按钮从教务系统\n"
                "导出的 .ics 文件批量导入。"
            ),
        },
        {
            "emoji": "🌟",
            "title": "开始使用吧！",
            "body": (
                "概览页面会显示今日课程和下一节课提醒，\n"
                "周视图和月视图帮助你掌握全局安排。\n"
                "祝你学习愉快！"
            ),
        },
    ]

    def __init__(self, parent: Gtk.Window):
        super().__init__(title="新手引导", modal=True, transient_for=parent)
        self.set_default_size(400, 380)
        self._step = 0

        content = self.get_content_area()
        content.set_margin_top(0)
        content.set_margin_bottom(0)
        content.set_margin_start(0)
        content.set_margin_end(0)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # ── Step pages ─────────────────────────────────────────
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_transition_duration(250)
        self._stack.set_vexpand(True)

        for i, step in enumerate(self._STEPS):
            page = self._make_page(step)
            self._stack.add_named(page, f"step{i}")

        outer.append(self._stack)

        # ── Dot indicators ─────────────────────────────────────
        dots_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        dots_box.set_halign(Gtk.Align.CENTER)
        dots_box.set_margin_top(8)
        dots_box.set_margin_bottom(8)
        self._dots: list[Gtk.Box] = []
        for i in range(len(self._STEPS)):
            dot = Gtk.Box()
            dot.set_size_request(10, 10)
            dot.add_css_class("dot-active" if i == 0 else "dot-inactive")
            dot.set_margin_start(4)
            dot.set_margin_end(4)
            self._dots.append(dot)
            dots_box.append(dot)
        outer.append(dots_box)

        # ── Navigation buttons ──────────────────────────────────
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nav_box.set_margin_start(16)
        nav_box.set_margin_end(16)
        nav_box.set_margin_bottom(16)

        self._prev_btn = Gtk.Button(label="上一步")
        self._prev_btn.add_css_class("pill")
        self._prev_btn.set_sensitive(False)
        self._prev_btn.connect("clicked", self._on_prev)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)

        self._next_btn = Gtk.Button(label="下一步")
        self._next_btn.add_css_class("pill")
        self._next_btn.add_css_class("suggested-action")
        self._next_btn.connect("clicked", self._on_next)

        nav_box.append(self._prev_btn)
        nav_box.append(spacer)
        nav_box.append(self._next_btn)
        outer.append(nav_box)

        content.append(outer)

    def _make_page(self, step: dict) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.add_css_class("onboarding-page")

        emoji_lbl = Gtk.Label(label=step["emoji"])
        emoji_lbl.add_css_class("onboarding-icon")
        box.append(emoji_lbl)

        title_lbl = Gtk.Label(label=step["title"])
        title_lbl.add_css_class("onboarding-title")
        title_lbl.set_justify(Gtk.Justification.CENTER)
        title_lbl.set_wrap(True)
        box.append(title_lbl)

        body_lbl = Gtk.Label(label=step["body"])
        body_lbl.add_css_class("onboarding-body")
        body_lbl.set_justify(Gtk.Justification.CENTER)
        body_lbl.set_wrap(True)
        body_lbl.set_max_width_chars(40)
        box.append(body_lbl)

        return box

    def _go_to(self, idx: int):
        self._step = idx
        self._stack.set_visible_child_name(f"step{idx}")
        for i, dot in enumerate(self._dots):
            dot.remove_css_class("dot-active")
            dot.remove_css_class("dot-inactive")
            dot.add_css_class("dot-active" if i == idx else "dot-inactive")
        self._prev_btn.set_sensitive(idx > 0)
        last = len(self._STEPS) - 1
        if idx == last:
            self._next_btn.set_label("开始使用！")
        else:
            self._next_btn.set_label("下一步")

    def _on_prev(self, _btn):
        if self._step > 0:
            self._go_to(self._step - 1)

    def _on_next(self, _btn):
        if self._step < len(self._STEPS) - 1:
            self._go_to(self._step + 1)
        else:
            self.response(Gtk.ResponseType.OK)


# ──────────────────────────── Conflict Resolution Dialog ────────


class ConflictResolutionDialog(Gtk.Dialog):
    """
    Shown when imported courses share names with existing ones.

    The user can choose to:
      - SKIP    : only import courses whose names are new
      - OVERWRITE: remove existing courses with conflicting names, then import all
    """

    # Response codes (returned as response id)
    RESP_SKIP = 1
    RESP_OVERWRITE = 2

    def __init__(self, parent: Gtk.Window,
                 conflict_names: list[str]):
        super().__init__(title="导入冲突", modal=True, transient_for=parent)
        self.set_default_size(400, -1)

        self.add_button("取消", Gtk.ResponseType.CANCEL)
        self.add_button("仅导入新课程", self.RESP_SKIP)
        overwrite_btn = self.add_button("覆盖同名课程", self.RESP_OVERWRITE)
        overwrite_btn.add_css_class("destructive-action")

        content = self.get_content_area()
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        title_lbl = Gtk.Label(
            label="以下课程与已有课程重名",
            xalign=0,
        )
        title_lbl.add_css_class("title-4")
        box.append(title_lbl)

        names_text = "\n".join(f"• {n}" for n in conflict_names)
        names_lbl = Gtk.Label(label=names_text, xalign=0)
        names_lbl.set_selectable(True)
        box.append(names_lbl)

        hint_lbl = Gtk.Label(
            label=(
                "「仅导入新课程」：跳过重名课程，只添加无冲突的课程。\n"
                "「覆盖同名课程」：删除已有的同名课程，再导入所有新课程。"
            ),
            xalign=0,
            wrap=True,
        )
        hint_lbl.add_css_class("dim-label")
        box.append(hint_lbl)

        content.append(box)


# ──────────────────────────── Import Dialog ─────────────────────


class ImportCoursesDialog(Gtk.Dialog):
    """Import courses from a .ics / .json file or by pasting text."""

    _HINT = (
        "支持 iCalendar (.ics) 和 JSON 两种格式。\n"
        "JSON 中可用 start/end（HH:MM）或 start_period/end_period（节次编号）指定时间。\n"
        "一门课有多个上课时间时，可用 sessions 数组列出每节，共用 name/location/teacher/weeks。\n"
        "weeks 格式：\"1-16\"、\"1,3,5\"、\"单\"（奇周）、\"双\"（偶周）等。"
    )

    def __init__(self, parent: Gtk.Window,
                 class_periods: list | None = None):
        super().__init__(title="导入课程", modal=True, transient_for=parent)
        self.set_default_size(520, 520)
        self._imported_courses: list[Course] = []
        self._class_periods: list = class_periods or []

        self.add_button("取消", Gtk.ResponseType.CANCEL)
        self._ok_btn = self.add_button("导入", Gtk.ResponseType.OK)
        self._ok_btn.add_css_class("suggested-action")
        self._ok_btn.set_sensitive(False)

        content = self.get_content_area()
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(14)
        content.set_margin_end(14)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # Description
        hint = Gtk.Label(label=self._HINT, xalign=0, wrap=True)
        hint.add_css_class("dim-label")
        box.append(hint)

        # File chooser row
        file_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        file_row.set_valign(Gtk.Align.CENTER)
        file_btn = Gtk.Button(label="选择文件…")
        file_btn.add_css_class("pill")
        file_btn.connect("clicked", self._on_open_file)
        self._file_label = Gtk.Label(label="未选择文件", xalign=0)
        self._file_label.add_css_class("dim-label")
        self._file_label.set_ellipsize(Pango.EllipsizeMode.START)
        self._file_label.set_hexpand(True)
        file_row.append(file_btn)
        file_row.append(self._file_label)
        box.append(file_row)

        # Separator
        sep_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        sep_row.set_halign(Gtk.Align.FILL)
        left_sep = Gtk.Separator()
        left_sep.set_hexpand(True)
        left_sep.set_valign(Gtk.Align.CENTER)
        right_sep = Gtk.Separator()
        right_sep.set_hexpand(True)
        right_sep.set_valign(Gtk.Align.CENTER)
        or_lbl = Gtk.Label(label="或粘贴数据")
        or_lbl.add_css_class("dim-label")
        sep_row.append(left_sep)
        sep_row.append(or_lbl)
        sep_row.append(right_sep)
        box.append(sep_row)

        # Template button
        tpl_btn = Gtk.Button(label="查看 JSON 格式示例")
        tpl_btn.add_css_class("flat")
        tpl_btn.connect("clicked", self._on_show_template)
        box.append(tpl_btn)

        # Text area
        self._text_view = Gtk.TextView()
        self._text_view.set_monospace(True)
        self._text_view.set_wrap_mode(Gtk.WrapMode.NONE)
        self._text_view.get_buffer().connect("changed", self._on_text_changed)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_hexpand(True)
        sw.set_min_content_height(160)
        sw.set_child(self._text_view)
        box.append(sw)

        # Parse button
        parse_btn = Gtk.Button(label="解析预览")
        parse_btn.add_css_class("pill")
        parse_btn.connect("clicked", self._on_parse)
        box.append(parse_btn)

        # Result / error labels
        self._result_label = Gtk.Label(label="", xalign=0, wrap=True)
        self._result_label.set_visible(False)
        box.append(self._result_label)

        self._error_label = Gtk.Label(label="", xalign=0, wrap=True)
        self._error_label.add_css_class("error")
        self._error_label.set_visible(False)
        box.append(self._error_label)

        content.append(box)

    # ── file chooser ─────────────────────────────────────────────

    def _on_open_file(self, _btn):
        native = Gtk.FileChooserNative.new(
            "选择 .ics 或 .json 文件",
            self,
            Gtk.FileChooserAction.OPEN,
            "打开",
            "取消",
        )
        f = Gtk.FileFilter()
        f.set_name("课程文件 (*.ics, *.json)")
        f.add_pattern("*.ics")
        f.add_pattern("*.json")
        native.add_filter(f)
        native.connect("response", self._on_file_response)
        native.show()

    def _on_file_response(self, native, response):
        if response == Gtk.ResponseType.ACCEPT:
            gfile = native.get_file()
            if gfile:
                path = gfile.get_path()
                try:
                    with open(path, encoding="utf-8") as f:
                        text = f.read()
                except Exception as exc:
                    self._show_error(f"读取文件失败：{exc}")
                    return
                self._file_label.set_text(path)
                self._text_view.get_buffer().set_text(text)
                self._on_parse(None)

    # ── text / template ──────────────────────────────────────────

    def _on_text_changed(self, _buf):
        self._ok_btn.set_sensitive(False)
        self._result_label.set_visible(False)
        self._error_label.set_visible(False)

    def _on_show_template(self, _btn):
        from importer import JSON_TEMPLATE
        self._text_view.get_buffer().set_text(JSON_TEMPLATE)

    # ── parse ────────────────────────────────────────────────────

    def _on_parse(self, _btn):
        from importer import parse_ics, parse_json_courses

        buf = self._text_view.get_buffer()
        text = buf.get_text(
            buf.get_start_iter(), buf.get_end_iter(), False
        ).strip()

        if not text:
            self._show_error("请先输入课程数据或选择文件")
            return

        text_upper = text.upper()
        if "BEGIN:VCALENDAR" in text_upper or "BEGIN:VEVENT" in text_upper:
            courses, warnings = parse_ics(text)
        else:
            courses, warnings = parse_json_courses(text, periods=self._class_periods)

        if not courses:
            self._show_error("未能解析出任何课程，请检查格式是否正确")
            return

        self._imported_courses = courses
        msg = f"✅ 解析成功：{len(courses)} 门课程"
        if warnings:
            shown = "；".join(warnings[:3])
            extra = f"（共 {len(warnings)} 条警告）" if len(warnings) > 3 else ""
            msg += f"\n⚠️ {shown}{extra}"

        self._result_label.set_text(msg)
        self._result_label.set_visible(True)
        self._error_label.set_visible(False)
        self._ok_btn.set_sensitive(True)

    def _show_error(self, msg: str):
        self._error_label.set_text(msg)
        self._error_label.set_visible(True)
        self._result_label.set_visible(False)
        self._ok_btn.set_sensitive(False)

    # ── public ───────────────────────────────────────────────────

    def get_imported_courses(self) -> list[Course]:
        return list(self._imported_courses)


# ──────────────────────────── Week Grid View ────────────────────


class WeekGridView(Gtk.Box):
    """
    Full-week timetable grid with week navigation.
    Columns = Mon–Sun (7 days), rows = class periods, courses = coloured cards.
    The grid expands to fill the available window width.
    """

    # Show Mon–Sun (7 days)
    _NUM_DAYS = 7            # Monday through Sunday
    _PERIOD_LABEL_WIDTH = 40  # px – fixed width of the period-label column
    _CELL_HEIGHT = 54         # px – minimum height of every grid row

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._courses: list = []
        self._periods: list = []
        self._color_map: dict = {}
        self._week_offset: int = 0        # 0 = current week
        self._term_start_date: str = ""
        self._total_weeks: int = 0

        # ── Navigation bar ────────────────────────────────────
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nav.set_halign(Gtk.Align.CENTER)
        nav.set_margin_top(12)
        nav.set_margin_bottom(4)

        prev_btn = Gtk.Button(icon_name="go-previous-symbolic")
        prev_btn.add_css_class("flat")
        prev_btn.connect("clicked", self._on_prev)

        self._nav_label = Gtk.Label()
        self._nav_label.add_css_class("title-3")
        self._nav_label.set_width_chars(18)
        self._nav_label.set_xalign(0.5)

        next_btn = Gtk.Button(icon_name="go-next-symbolic")
        next_btn.add_css_class("flat")
        next_btn.connect("clicked", self._on_next)

        nav.append(prev_btn)
        nav.append(self._nav_label)
        nav.append(next_btn)
        self.append(nav)

        # ── Scrollable grid area ───────────────────────────────
        sw = Gtk.ScrolledWindow()
        sw.set_hexpand(True)
        sw.set_vexpand(True)
        # No horizontal scrollbar – the grid always fills available width
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.set_margin_top(4)
        wrapper.set_margin_bottom(12)
        wrapper.set_margin_start(20)
        wrapper.set_margin_end(20)

        self._grid = Gtk.Grid()
        self._grid.set_row_spacing(3)
        self._grid.set_column_spacing(4)
        # All columns (including the period-label column) share equal width so
        # the day columns always stretch to fill the window.
        self._grid.set_column_homogeneous(True)
        self._grid.set_hexpand(True)
        wrapper.append(self._grid)
        sw.set_child(wrapper)
        self.append(sw)

    # ── public ──────────────────────────────────────────────────

    def refresh(self, courses: list, periods: list,
                term_start_date: str = "", total_weeks: int = 0) -> None:
        self._courses = courses
        self._periods = periods
        self._color_map = _assign_colors(courses)
        self._term_start_date = term_start_date
        self._total_weeks = total_weeks
        today_wd = datetime.now().weekday() + 1  # 1=Mon … 7=Sun
        self._build(today_wd)

    # ── internals ───────────────────────────────────────────────

    def _clear(self) -> None:
        child = self._grid.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._grid.remove(child)
            child = nxt

    @staticmethod
    def _ranges_overlap(p1: int, s1: int, p2: int, s2: int) -> bool:
        return p1 < p2 + s2 and p2 < p1 + s1

    def _displayed_week_num(self) -> int | None:
        """Return the week number (1-indexed) for the displayed week, or None."""
        if not self._term_start_date:
            return None
        base_week = calc_current_week(self._term_start_date)
        if not base_week:   # None or 0 (before term start)
            return None
        w = base_week + self._week_offset
        if w < 1:
            return None
        if self._total_weeks and w > self._total_weeks:
            return None
        return w

    def _update_nav_label(self, week_start: date) -> None:
        week_end = week_start + timedelta(days=6)
        date_str = (f"{week_start.month}/{week_start.day}"
                    f" – {week_end.month}/{week_end.day}")
        week_num = self._displayed_week_num()
        if week_num is not None:
            self._nav_label.set_text(f"第 {week_num} 周  {date_str}")
        else:
            self._nav_label.set_text(date_str)

    def _build(self, today_wd: int) -> None:
        self._clear()

        today       = date.today()
        this_monday = today - timedelta(days=today.weekday())   # Monday of current week
        week_start  = this_monday + timedelta(weeks=self._week_offset)
        week_dates  = [week_start + timedelta(days=i) for i in range(7)]

        self._update_nav_label(week_start)

        # Highlight today's column only when showing the current week
        effective_today_wd = today_wd if self._week_offset == 0 else -1

        # ── Header row ────────────────────────────────────────
        corner = Gtk.Label(label="节次")
        corner.add_css_class("caption")
        corner.add_css_class("dim-label")
        corner.set_margin_top(4)
        corner.set_margin_bottom(8)
        self._grid.attach(corner, 0, 0, 1, 1)

        for col in range(1, self._NUM_DAYS + 1):
            wd = col
            d  = week_dates[wd - 1]
            is_today = (wd == effective_today_wd)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.set_halign(Gtk.Align.CENTER)
            vbox.set_margin_bottom(8)

            name_lbl = Gtk.Label(label=WEEKDAY_CN[wd])
            name_lbl.add_css_class("caption-heading")
            if is_today:
                name_lbl.add_css_class("accent")

            date_lbl = Gtk.Label(label=f"{d.month}/{d.day}")
            date_lbl.add_css_class("caption")
            if is_today:
                date_lbl.add_css_class("accent")
            else:
                date_lbl.add_css_class("dim-label")

            vbox.append(name_lbl)
            vbox.append(date_lbl)
            self._grid.attach(vbox, col, 0, 1, 1)

        # ── No periods configured ──────────────────────────────
        if not self._periods:
            lbl = Gtk.Label(label="请在全局设置中配置节次时间")
            lbl.add_css_class("dim-label")
            lbl.set_margin_top(24)
            self._grid.attach(lbl, 0, 1, self._NUM_DAYS + 1, 1)
            return

        # ── Step 1: compute (col, pidx, span, is_active) per course ─
        from collections import defaultdict

        displayed_week = self._displayed_week_num()
        all_items = []   # (course, col, pidx, span, is_active)
        for course in self._courses:
            if course.day > self._NUM_DAYS:
                continue
            pidx, span = _get_period_span(course, self._periods)
            if pidx is None:
                continue
            is_active = is_course_active_this_week(course, displayed_week)
            all_items.append((course, course.day, pidx, span, is_active))

        # ── Step 2: group overlapping courses per column ─────────
        # Each group: (col, min_pidx, group_span, active_list, inactive_list)
        # where active_list = [(course, pidx, span), ...]
        by_col: dict = defaultdict(list)
        for item in all_items:
            by_col[item[1]].append(item)

        grid_placements = []  # (col, min_pidx, group_span, active, inactive)

        for col, items in by_col.items():
            n = len(items)
            parent = list(range(n))

            def _find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def _union(x: int, y: int) -> None:
                px, py = _find(x), _find(y)
                if px != py:
                    parent[px] = py

            for i in range(n):
                _, _, pidx_i, span_i, _ = items[i]
                for j in range(i + 1, n):
                    _, _, pidx_j, span_j, _ = items[j]
                    if self._ranges_overlap(pidx_i, span_i, pidx_j, span_j):
                        _union(i, j)

            groups: dict = defaultdict(list)
            for i in range(n):
                groups[_find(i)].append(items[i])

            for group_items in groups.values():
                min_pidx  = min(it[2] for it in group_items)
                max_end   = max(it[2] + it[3] for it in group_items)
                group_span = max_end - min_pidx
                active   = [(it[0], it[2], it[3]) for it in group_items if it[4]]
                inactive = [(it[0], it[2], it[3]) for it in group_items if not it[4]]
                grid_placements.append((col, min_pidx, group_span, active, inactive))

        # ── Step 3: build occupied set for placeholder cells ─────
        occupied: set = set()
        for col, min_pidx, group_span, active, inactive in grid_placements:
            for k in range(group_span):
                occupied.add((col, min_pidx + 1 + k))

        # ── Step 4: period labels + separators + empty placeholders ──
        for ridx, period in enumerate(self._periods):
            sep_row  = ridx * 2 + 1
            grid_row = ridx * 2 + 2

            sep = Gtk.Box()
            sep.set_size_request(-1, 1)
            sep.set_hexpand(True)
            sep.add_css_class("week-period-separator")
            self._grid.attach(sep, 0, sep_row, self._NUM_DAYS + 1, 1)

            pbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            pbox.set_halign(Gtk.Align.CENTER)
            pbox.set_valign(Gtk.Align.CENTER)
            pbox.set_size_request(self._PERIOD_LABEL_WIDTH, self._CELL_HEIGHT)
            pbox.add_css_class("week-period-label")

            n_lbl = Gtk.Label(label=str(period.period))
            n_lbl.add_css_class("caption-heading")
            t_lbl = Gtk.Label(label=period.start)
            t_lbl.add_css_class("caption")
            t_lbl.add_css_class("dim-label")
            pbox.append(n_lbl)
            pbox.append(t_lbl)
            self._grid.attach(pbox, 0, grid_row, 1, 1)

            period_row = ridx + 1
            for col in range(1, self._NUM_DAYS + 1):
                if (col, period_row) not in occupied:
                    ph = Gtk.Box()
                    ph.set_hexpand(True)
                    ph.set_size_request(-1, self._CELL_HEIGHT)
                    self._grid.attach(ph, col, grid_row, 1, 1)

        # ── Step 5: course cards ────────────────────────────────
        for col, min_pidx, group_span, active, inactive in grid_placements:
            grid_row  = min_pidx * 2 + 2
            grid_span = group_span * 2 - 1

            if active:
                if len(active) == 1:
                    course, pidx, span = active[0]
                    bg, fg = self._color_map.get(course.id, ("#888888", "#ffffff"))
                    card = self._make_card(course, bg, fg, span)
                    self._grid.attach(card, col, pidx * 2 + 2, 1, span * 2 - 1)
                else:
                    # Conflict: show all conflicting courses side by side
                    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
                    hbox.set_hexpand(True)
                    hbox.set_valign(Gtk.Align.FILL)
                    for course, pidx, span in active:
                        bg, fg = self._color_map.get(course.id, ("#888888", "#ffffff"))
                        card = self._make_card(course, bg, fg, span, is_conflict=True)
                        card.set_hexpand(True)
                        hbox.append(card)
                    self._grid.attach(hbox, col, grid_row, 1, grid_span)
            elif inactive:
                # No active course in this slot — show first inactive one dimmed
                course, pidx, span = inactive[0]
                bg, fg = self._color_map.get(course.id, ("#888888", "#ffffff"))
                card = self._make_card(course, bg, fg, span, is_inactive=True)
                self._grid.attach(card, col, pidx * 2 + 2, 1, span * 2 - 1)

    def _on_prev(self, _btn) -> None:
        self._week_offset -= 1
        today_wd = datetime.now().weekday() + 1
        self._build(today_wd)

    def _on_next(self, _btn) -> None:
        self._week_offset += 1
        today_wd = datetime.now().weekday() + 1
        self._build(today_wd)

    def _make_card(self, course: Course, bg: str, fg: str, span: int,
                   is_inactive: bool = False, is_conflict: bool = False) -> Gtk.Widget:
        cls = _course_css_class(course.id)
        _ensure_color_class(cls, bg, fg)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_halign(Gtk.Align.FILL)
        box.set_valign(Gtk.Align.FILL)
        box.set_hexpand(True)
        box.add_css_class("course-card")
        box.add_css_class(cls)

        if is_inactive:
            box.set_opacity(0.4)
            tag_lbl = Gtk.Label(label="非本周")
            tag_lbl.add_css_class("caption")
            tag_lbl.set_justify(Gtk.Justification.CENTER)
            box.append(tag_lbl)

        name_lbl = Gtk.Label(label=course.name)
        name_lbl.set_wrap(True)
        name_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        name_lbl.set_max_width_chars(4 if is_conflict else 5)
        name_lbl.add_css_class("caption-heading")
        name_lbl.set_justify(Gtk.Justification.CENTER)
        box.append(name_lbl)

        if course.location and span >= 2 and not is_conflict:
            loc_lbl = Gtk.Label(label=course.location)
            loc_lbl.add_css_class("caption")
            loc_lbl.set_justify(Gtk.Justification.CENTER)
            loc_lbl.set_wrap(True)
            loc_lbl.set_max_width_chars(5)
            box.append(loc_lbl)

        return box


# ──────────────────────────── Month View ────────────────────────


class MonthView(Gtk.Box):
    """Monthly calendar: 7-column grid with per-day course pills."""

    _MONTH_CN = ["", "一月", "二月", "三月", "四月", "五月", "六月",
                 "七月", "八月", "九月", "十月", "十一月", "十二月"]

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        self._year:  int  = date.today().year
        self._month: int  = date.today().month
        self._courses:   list = []
        self._color_map: dict = {}

        # ── Navigation bar ────────────────────────────────────
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        nav.set_halign(Gtk.Align.CENTER)
        nav.set_margin_bottom(12)

        prev_btn = Gtk.Button(icon_name="go-previous-symbolic")
        prev_btn.add_css_class("flat")
        prev_btn.connect("clicked", self._on_prev)

        self._nav_label = Gtk.Label()
        self._nav_label.add_css_class("title-3")
        self._nav_label.set_width_chars(10)
        self._nav_label.set_xalign(0.5)

        next_btn = Gtk.Button(icon_name="go-next-symbolic")
        next_btn.add_css_class("flat")
        next_btn.connect("clicked", self._on_next)

        nav.append(prev_btn)
        nav.append(self._nav_label)
        nav.append(next_btn)
        self.append(nav)

        # ── Day-of-week header ────────────────────────────────
        dow_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        dow_box.set_homogeneous(True)
        dow_box.set_margin_bottom(4)
        for name in ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]:
            lbl = Gtk.Label(label=name)
            lbl.add_css_class("caption-heading")
            lbl.add_css_class("dim-label")
            lbl.set_margin_top(4)
            lbl.set_margin_bottom(4)
            dow_box.append(lbl)
        self.append(dow_box)

        # ── Calendar grid ─────────────────────────────────────
        self._grid = Gtk.Grid()
        self._grid.set_row_spacing(2)
        self._grid.set_column_spacing(2)
        self._grid.set_row_homogeneous(True)
        self._grid.set_column_homogeneous(True)

        sw = Gtk.ScrolledWindow()
        sw.set_child(self._grid)
        sw.set_vexpand(True)
        sw.set_hexpand(True)
        self.append(sw)

    # ── public ──────────────────────────────────────────────────

    def refresh(self, courses: list, color_map: dict) -> None:
        self._courses = courses
        self._color_map = color_map
        self._rebuild()

    # ── internals ───────────────────────────────────────────────

    def _rebuild(self) -> None:
        child = self._grid.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._grid.remove(child)
            child = nxt

        self._nav_label.set_text(
            f"{self._year} 年 {self._MONTH_CN[self._month]}"
        )

        today  = date.today()
        matrix = _cal.monthcalendar(self._year, self._month)
        while len(matrix) < 6:
            matrix.append([0] * 7)

        # courses_by_wd: 1-7 -> [courses on that weekday]
        courses_by_wd: dict = {wd: [] for wd in range(1, 8)}
        for c in self._courses:
            courses_by_wd[c.day].append(c)

        for row, week in enumerate(matrix):
            for col, day_num in enumerate(week):
                wd   = col + 1    # 1=Mon … 7=Sun
                cell = self._make_cell(day_num, wd, today, courses_by_wd[wd])
                self._grid.attach(cell, col, row, 1, 1)

    def _make_cell(self, day_num: int, wd: int, today: date,
                   day_courses: list) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_size_request(44, 68)
        box.add_css_class("month-day-cell")

        if day_num == 0:
            return box   # padding cell outside the month

        is_today = (day_num == today.day and
                    self._year == today.year and
                    self._month == today.month)
        if is_today:
            box.add_css_class("month-today-cell")

        num_lbl = Gtk.Label(label=str(day_num))
        num_lbl.set_halign(Gtk.Align.START)
        num_lbl.add_css_class("month-today-num" if is_today else "month-other-num")
        box.append(num_lbl)

        # Course pills (max 3 visible)
        for c in day_courses[:3]:
            bg, fg = self._color_map.get(c.id, ("#888888", "#ffffff"))
            cls    = _course_css_class(c.id)
            _ensure_color_class(cls, bg, fg)

            pill = Gtk.Label(label=(c.name[:5] + ("…" if len(c.name) > 5 else "")))
            pill.add_css_class("caption")
            pill.add_css_class(cls)
            pill.set_halign(Gtk.Align.FILL)
            pill.set_xalign(0.0)

            # Round the pill slightly
            provider = Gtk.CssProvider()
            provider.load_from_string(
                "label { border-radius: 4px; padding: 1px 3px; }"
            )
            pill.get_style_context().add_provider(
                provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5
            )
            box.append(pill)

        if len(day_courses) > 3:
            more = Gtk.Label(label=f"+{len(day_courses) - 3}")
            more.add_css_class("caption")
            more.add_css_class("dim-label")
            more.set_halign(Gtk.Align.START)
            box.append(more)

        return box

    def _on_prev(self, _btn) -> None:
        if self._month == 1:
            self._year -= 1
            self._month = 12
        else:
            self._month -= 1
        self._rebuild()

    def _on_next(self, _btn) -> None:
        if self._month == 12:
            self._year += 1
            self._month = 1
        else:
            self._month += 1
        self._rebuild()


# ──────────────────────────── main window ───────────────────────


class WadwaitaUpWindow(Adw.ApplicationWindow):
    def __init__(self, app, version: str = "unknown"):
        super().__init__(application=app)
        self._app_version = version
        self.set_title("WadwaitaUp 课程表")
        self.set_default_size(760, 800)

        _load_app_css()

        self._schedule_storage = ScheduleStorage()
        self._settings_storage = SettingsStorage()

        self._schedules: list[Schedule] = self._schedule_storage.load()
        self._settings: dict = self._settings_storage.load()

        # Resolve active schedule ───────────────────────────────
        saved_id = self._settings.get("current_schedule_id")
        self._active_idx = 0
        if saved_id:
            for i, s in enumerate(self._schedules):
                if s.id == saved_id:
                    self._active_idx = i
                    break

        # Apply saved color scheme ──────────────────────────────
        self._apply_color_scheme(self._settings.get("color_scheme", "auto"))

        # ── Build UI ────────────────────────────────────────────
        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        # ── Header: left buttons ─────────────────────────────────
        settings_btn = Gtk.Button(icon_name="emblem-system-symbolic")
        settings_btn.set_tooltip_text("全局设置（节次时间 / 外观）")
        settings_btn.connect("clicked", self._on_global_settings_clicked)
        header.pack_start(settings_btn)

        edit_schedule_btn = Gtk.Button(icon_name="document-edit-symbolic")
        edit_schedule_btn.set_tooltip_text("编辑当前课表信息")
        edit_schedule_btn.connect("clicked", self._on_edit_schedule_clicked)
        header.pack_start(edit_schedule_btn)

        # ── Header: center – ViewSwitcher ───────────────────────
        self._view_stack = Adw.ViewStack()

        # ViewSwitcher sits in the header centre
        view_switcher = Adw.ViewSwitcher()
        view_switcher.set_stack(self._view_stack)
        view_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(view_switcher)

        # Schedule switcher dropdown lives in the header start group
        self._schedule_names_model = Gtk.StringList()
        self._rebuild_schedule_model()
        self._schedule_dropdown = Gtk.DropDown(
            model=self._schedule_names_model,
            selected=self._active_idx,
        )
        self._schedule_dropdown.set_tooltip_text("切换课表")
        self._schedule_dropdown.connect("notify::selected", self._on_schedule_switched)
        header.pack_start(self._schedule_dropdown)

        # ── Header: right buttons ────────────────────────────────
        self._dark_btn = Gtk.ToggleButton(icon_name="weather-clear-night-symbolic")
        self._dark_btn.set_tooltip_text("切换深色/浅色模式")
        self._dark_btn.set_active(self._settings.get("color_scheme", "auto") == "dark")
        self._dark_btn.connect("toggled", self._on_dark_toggled)
        header.pack_end(self._dark_btn)

        # Flag to prevent _on_dark_toggled re-entry during programmatic sync
        self._suppress_dark_toggle = False

        about_btn = Gtk.Button(icon_name="help-about-symbolic")
        about_btn.set_tooltip_text("关于 WadwaitaUp")
        about_btn.connect("clicked", self._on_about_clicked)
        header.pack_end(about_btn)

        export_cal_btn = Gtk.Button(icon_name="x-office-calendar-symbolic")
        export_cal_btn.set_tooltip_text("导出课程表到日历（.ics）")
        export_cal_btn.connect("clicked", self._on_export_calendar_clicked)
        header.pack_end(export_cal_btn)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("添加课程")
        add_btn.connect("clicked", self._on_add_clicked)
        header.pack_end(add_btn)

        import_btn = Gtk.Button(icon_name="document-save-symbolic")
        import_btn.set_tooltip_text("导入课程（.ics / JSON）")
        import_btn.connect("clicked", self._on_import_clicked)
        header.pack_end(import_btn)

        add_schedule_btn = Gtk.Button(icon_name="folder-new-symbolic")
        add_schedule_btn.set_tooltip_text("新建课表")
        add_schedule_btn.connect("clicked", self._on_add_schedule_clicked)
        header.pack_end(add_schedule_btn)

        self._del_schedule_btn = Gtk.Button(icon_name="edit-delete-symbolic")
        self._del_schedule_btn.set_tooltip_text("删除当前课表")
        self._del_schedule_btn.connect("clicked", self._on_delete_schedule_clicked)
        header.pack_end(self._del_schedule_btn)

        # ── View Stack: page 1 – Overview ────────────────────────
        overview_scroll = Gtk.ScrolledWindow()
        overview_scroll.set_policy(
            Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC
        )
        self._overview_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12
        )
        self._overview_box.set_margin_top(16)
        self._overview_box.set_margin_bottom(16)
        self._overview_box.set_margin_start(24)
        self._overview_box.set_margin_end(24)
        overview_scroll.set_child(self._overview_box)

        p_overview = self._view_stack.add_titled(overview_scroll, "overview", "概览")
        p_overview.set_icon_name("view-list-symbolic")

        # ── Mascot card (top of overview) ────────────────────────
        self._mascot_card = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=14
        )
        self._mascot_card.add_css_class("mascot-card")
        self._mascot_card.set_vexpand(False)

        # Emoji circle
        emoji_bg = Gtk.Box()
        emoji_bg.set_halign(Gtk.Align.CENTER)
        emoji_bg.set_valign(Gtk.Align.CENTER)
        emoji_bg.add_css_class("mascot-emoji-bg")
        self._mascot_emoji_lbl = Gtk.Label(label="🌟")
        self._mascot_emoji_lbl.add_css_class("mascot-emoji")
        self._mascot_emoji_lbl.set_hexpand(True)
        self._mascot_emoji_lbl.set_vexpand(True)
        emoji_bg.append(self._mascot_emoji_lbl)
        self._mascot_card.append(emoji_bg)

        # Text side
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        text_box.set_valign(Gtk.Align.CENTER)
        text_box.set_hexpand(True)
        self._mascot_msg_lbl = Gtk.Label(
            label="", xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR
        )
        self._mascot_msg_lbl.add_css_class("mascot-title")
        text_box.append(self._mascot_msg_lbl)
        self._mascot_card.append(text_box)

        self._overview_box.append(self._mascot_card)

        # Overview inner widgets
        term_group = Adw.PreferencesGroup(title="学期信息")
        self._term_row = Adw.ActionRow(
            title="未设置学期开始日期", subtitle="点击左上角铅笔图标设置"
        )
        term_group.add(self._term_row)
        self._overview_box.append(term_group)

        next_group = Adw.PreferencesGroup(title="下一节课")
        self._next_row = Adw.ActionRow(title="暂无课程", subtitle="请先添加课程")
        next_group.add(self._next_row)
        self._overview_box.append(next_group)

        today_group = Adw.PreferencesGroup(title="今天的课程")
        self._today_list = Gtk.ListBox()
        self._today_list.add_css_class("boxed-list")
        self._today_list.set_selection_mode(Gtk.SelectionMode.NONE)
        today_group.add(self._today_list)
        self._overview_box.append(today_group)

        all_group = Adw.PreferencesGroup(title="所有课程")
        self._week_list = Gtk.ListBox()
        self._week_list.add_css_class("boxed-list")
        self._week_list.set_selection_mode(Gtk.SelectionMode.NONE)
        all_group.add(self._week_list)
        self._overview_box.append(all_group)

        # ── View Stack: page 2 – Week Grid ───────────────────────
        self._week_grid = WeekGridView()
        p_week = self._view_stack.add_titled(self._week_grid, "week", "周视图")
        p_week.set_icon_name("view-grid-symbolic")

        # ── View Stack: page 3 – Month Calendar ──────────────────
        self._month_view = MonthView()
        p_month = self._view_stack.add_titled(
            self._month_view, "month", "月视图"
        )
        p_month.set_icon_name("x-office-calendar-symbolic")

        toolbar_view.set_content(self._view_stack)
        self.set_content(toolbar_view)

        self.refresh_ui()

        # ── Show onboarding on first launch ──────────────────────
        if not self._settings.get("onboarding_done", False):
            GLib.idle_add(self._show_onboarding)



    # ── schedule helpers ─────────────────────────────────────────

    @property
    def _active_schedule(self) -> Schedule:
        return self._schedules[self._active_idx]

    @property
    def _courses(self) -> list:
        return self._active_schedule.courses

    @_courses.setter
    def _courses(self, value):
        self._active_schedule.courses = value

    def _rebuild_schedule_model(self):
        while self._schedule_names_model.get_n_items():
            self._schedule_names_model.remove(0)
        for s in self._schedules:
            self._schedule_names_model.append(s.name)

    def _persist_schedules(self):
        self._active_schedule.courses = sort_courses(self._active_schedule.courses)
        self._schedule_storage.save(self._schedules)

    def _persist_settings(self):
        self._settings["current_schedule_id"] = self._active_schedule.id
        self._settings_storage.save(self._settings)

    # ── color scheme ─────────────────────────────────────────────

    def _apply_color_scheme(self, scheme: str):
        sm = Adw.StyleManager.get_default()
        if scheme == "dark":
            sm.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        elif scheme == "light":
            sm.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            sm.set_color_scheme(Adw.ColorScheme.DEFAULT)

    def on_color_scheme_changed(self, scheme: str):
        """Called by GlobalSettingsDialog when the user toggles the scheme."""
        self._settings["color_scheme"] = scheme
        self._apply_color_scheme(scheme)
        self._persist_settings()
        # Keep the header toggle in sync without re-triggering _on_dark_toggled
        self._suppress_dark_toggle = True
        self._dark_btn.set_active(scheme == "dark")
        self._suppress_dark_toggle = False

    def on_periods_changed(self, periods_raw: list):
        """Called by GlobalSettingsDialog when periods are saved."""
        self._settings["class_periods"] = periods_raw
        self._persist_settings()
        self.refresh_ui()

    def on_time_schemes_changed(self, schemes_raw: list):
        """Called by GlobalSettingsDialog when time schemes are saved."""
        self._settings["time_schemes"] = schemes_raw
        self._persist_settings()
        self.refresh_ui()

    # ── UI refresh ───────────────────────────────────────────────

    def _clear_listbox(self, listbox: Gtk.ListBox):
        child = listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            listbox.remove(child)
            child = nxt

    def _make_row(self, course: Course, is_active: bool = True) -> Gtk.ListBoxRow:
        subtitle_parts = [f"{WEEKDAY_CN[course.day]} {course.start}–{course.end}"]
        if not is_active:
            subtitle_parts.append("非本周")
        if course.location:
            subtitle_parts.append(course.location)
        if course.teacher:
            subtitle_parts.append(course.teacher)
        subtitle_parts.append(f"第{course.weeks}周")

        row = Adw.ActionRow(title=course.name, subtitle=" · ".join(subtitle_parts))
        if not is_active:
            row.set_opacity(0.5)

        edit_btn = Gtk.Button(icon_name="document-edit-symbolic")
        edit_btn.add_css_class("flat")
        edit_btn.set_tooltip_text("编辑")
        edit_btn.connect("clicked", self._on_edit_clicked, course.id)
        row.add_suffix(edit_btn)

        del_btn = Gtk.Button(icon_name="user-trash-symbolic")
        del_btn.add_css_class("flat")
        del_btn.set_tooltip_text("删除")
        del_btn.connect("clicked", self._on_delete_clicked, course.id)
        row.add_suffix(del_btn)

        wrapper = Gtk.ListBoxRow()
        wrapper.set_child(row)
        return wrapper

    def refresh_ui(self):
        schedule = self._active_schedule
        term_start = schedule.term_start_date
        total_weeks = schedule.total_weeks
        current_week = calc_current_week(term_start)

        # Update delete-schedule button sensitivity (can't delete last schedule)
        self._del_schedule_btn.set_sensitive(len(self._schedules) > 1)

        # ── Mascot card ─────────────────────────────────────────
        active_for_week = [
            c for c in self._courses
            if is_course_active_this_week(c, current_week)
        ]
        conflicts = detect_conflicts(active_for_week)
        emoji, msg, extra_cls, is_markup = _get_mascot_info(
            self._courses, current_week, conflicts
        )
        self._mascot_emoji_lbl.set_text(emoji)
        if is_markup:
            self._mascot_msg_lbl.set_use_markup(True)
            self._mascot_msg_lbl.set_markup(msg)
        else:
            self._mascot_msg_lbl.set_use_markup(False)
            self._mascot_msg_lbl.set_text(msg)
        for cls in ("mascot-card-urgent", "mascot-card-warn",
                    "mascot-card-happy", "mascot-card-accent"):
            self._mascot_card.remove_css_class(cls)
        if extra_cls:
            self._mascot_card.add_css_class(extra_cls)

        if term_start:
            if current_week is None:
                self._term_row.set_title("学期日期格式错误")
                self._term_row.set_subtitle("请编辑课表信息修正")
            elif current_week == 0:
                self._term_row.set_title(f"学期将开始（{term_start}）")
                self._term_row.set_subtitle(f"总周数 {total_weeks} 周")
            else:
                self._term_row.set_title(f"当前第 {current_week} 周")
                self._term_row.set_subtitle(
                    f"学期开始于 {term_start} · 总周数 {total_weeks} 周"
                )
        else:
            self._term_row.set_title("未设置学期开始日期")
            self._term_row.set_subtitle("点击左上角铅笔图标编辑课表信息")

        next_course, delta = get_next_course(self._courses)
        if next_course:
            self._next_row.set_title(next_course.name)
            self._next_row.set_subtitle(
                f"{WEEKDAY_CN[next_course.day]} {next_course.start}–{next_course.end} · "
                f"{next_course.location or '地点未设置'} · {humanize_delta_minutes(delta)}"
            )
        else:
            self._next_row.set_title("暂无课程")
            self._next_row.set_subtitle("点击右上角 + 添加课程")

        self._clear_listbox(self._today_list)
        today_courses = [
            c for c in get_today_courses(self._courses)
            if is_course_active_this_week(c, current_week)
        ]
        if today_courses:
            for c in today_courses:
                self._today_list.append(self._make_row(c))
        else:
            empty = Gtk.ListBoxRow()
            empty.set_child(Adw.ActionRow(title="今天没有课", subtitle="享受一下空闲时间 ☕"))
            self._today_list.append(empty)

        self._clear_listbox(self._week_list)
        if self._courses:
            # Show courses that have NOT fully ended; non-active-this-week
            # courses are still shown but marked "非本周".
            visible = [
                c for c in self._courses
                if not is_course_ended(c, current_week)
            ]
            if visible:
                for c in visible:
                    is_active = is_course_active_this_week(c, current_week)
                    self._week_list.append(self._make_row(c, is_active))
            else:
                empty = Gtk.ListBoxRow()
                empty.set_child(Adw.ActionRow(title="本学期课程已全部结束", subtitle="可切换到周视图查看历史课程"))
                self._week_list.append(empty)
        else:
            empty = Gtk.ListBoxRow()
            empty.set_child(Adw.ActionRow(title="还没有课程", subtitle="先添加几门课吧"))
            self._week_list.append(empty)

        # ── Refresh grid views ──────────────────────────────────
        periods = get_active_periods(self._settings)
        self._week_grid.refresh(
            self._courses, periods,
            term_start_date=schedule.term_start_date,
            total_weeks=schedule.total_weeks,
        )
        color_map = _assign_colors(self._courses)
        self._month_view.refresh(self._courses, color_map)


    # ── header button callbacks ──────────────────────────────────

    def _on_dark_toggled(self, btn):
        if self._suppress_dark_toggle:
            return
        scheme = "dark" if btn.get_active() else "auto"
        self._apply_color_scheme(scheme)
        self._settings["color_scheme"] = scheme
        self._persist_settings()

    def _on_export_calendar_clicked(self, _btn):
        schedule = self._active_schedule
        if not schedule.term_start_date:
            dlg = Adw.MessageDialog(
                transient_for=self,
                heading="无法导出",
                body="请先在课表信息（铅笔图标）中设置学期开始日期，再导出日历。",
            )
            dlg.add_response("ok", "确定")
            dlg.connect("response", lambda d, _r: d.close())
            dlg.present()
            return

        ics_content = export_schedule_to_ics(schedule, schedule.term_start_date)
        if not ics_content:
            return

        native = Gtk.FileChooserNative.new(
            "导出课程表到日历",
            self,
            Gtk.FileChooserAction.SAVE,
            "保存",
            "取消",
        )
        ff = Gtk.FileFilter()
        ff.set_name("iCalendar 文件 (*.ics)")
        ff.add_pattern("*.ics")
        native.add_filter(ff)
        safe_name = schedule.name.replace("/", "-").replace("\\", "-")
        native.set_current_name(f"{safe_name}.ics")

        def on_save_response(n, response):
            if response == Gtk.ResponseType.ACCEPT:
                gfile = n.get_file()
                if gfile:
                    path = gfile.get_path()
                    try:
                        with open(path, "w", encoding="utf-8") as fh:
                            fh.write(ics_content)
                    except Exception as exc:
                        err = Adw.MessageDialog(
                            transient_for=self,
                            heading="导出失败",
                            body=str(exc),
                        )
                        err.add_response("ok", "确定")
                        err.connect("response", lambda d, _r: d.close())
                        err.present()

        native.connect("response", on_save_response)
        native.show()

    def _on_global_settings_clicked(self, _btn):
        dlg = GlobalSettingsDialog(self, self._settings)

        def on_response(d, _response):
            d.close()

        dlg.connect("response", on_response)
        dlg.present()

    def _on_schedule_switched(self, dropdown, _param):
        idx = dropdown.get_selected()
        if idx == self._active_idx or idx < 0 or idx >= len(self._schedules):
            return
        self._active_idx = idx
        self._persist_settings()
        self.refresh_ui()

    def _on_add_schedule_clicked(self, _btn):
        dlg = ScheduleDialog(self)

        def on_response(d, response):
            if response == Gtk.ResponseType.OK:
                data = d.get_data()
                if data is not None:
                    new_s = Schedule(
                        id=str(uuid.uuid4()),
                        name=data["name"],
                        term_start_date=data["term_start_date"],
                        total_weeks=data["total_weeks"],
                    )
                    self._schedules.append(new_s)
                    self._active_idx = len(self._schedules) - 1
                    self._rebuild_schedule_model()
                    # Block signal to avoid re-entrant switch
                    self._schedule_dropdown.handler_block_by_func(self._on_schedule_switched)
                    self._schedule_dropdown.set_selected(self._active_idx)
                    self._schedule_dropdown.handler_unblock_by_func(self._on_schedule_switched)
                    self._schedule_storage.save(self._schedules)
                    self._persist_settings()
                    self.refresh_ui()
                    d.close()
            else:
                d.close()

        dlg.connect("response", on_response)
        dlg.present()

    def _on_edit_schedule_clicked(self, _btn):
        dlg = ScheduleDialog(self, self._active_schedule)

        def on_response(d, response):
            if response == Gtk.ResponseType.OK:
                data = d.get_data()
                if data is not None:
                    self._active_schedule.name = data["name"]
                    self._active_schedule.term_start_date = data["term_start_date"]
                    self._active_schedule.total_weeks = data["total_weeks"]
                    self._rebuild_schedule_model()
                    self._schedule_dropdown.handler_block_by_func(self._on_schedule_switched)
                    self._schedule_dropdown.set_selected(self._active_idx)
                    self._schedule_dropdown.handler_unblock_by_func(self._on_schedule_switched)
                    self._schedule_storage.save(self._schedules)
                    self.refresh_ui()
                    d.close()
            else:
                d.close()

        dlg.connect("response", on_response)
        dlg.present()

    def _on_delete_schedule_clicked(self, _btn):
        if len(self._schedules) <= 1:
            return
        # Simple confirmation via a message dialog
        confirm = Adw.MessageDialog(
            transient_for=self,
            heading="删除课表",
            body=f"确定要删除「{self._active_schedule.name}」吗？此操作不可撤销。",
        )
        confirm.add_response("cancel", "取消")
        confirm.add_response("delete", "删除")
        confirm.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        confirm.set_default_response("cancel")
        confirm.set_close_response("cancel")

        def on_confirm_response(d, response):
            if response == "delete":
                del self._schedules[self._active_idx]
                self._active_idx = max(0, self._active_idx - 1)
                self._rebuild_schedule_model()
                self._schedule_dropdown.handler_block_by_func(self._on_schedule_switched)
                self._schedule_dropdown.set_selected(self._active_idx)
                self._schedule_dropdown.handler_unblock_by_func(self._on_schedule_switched)
                self._schedule_storage.save(self._schedules)
                self._persist_settings()
                self.refresh_ui()

        confirm.connect("response", on_confirm_response)
        confirm.present()

    # ── course CRUD callbacks ────────────────────────────────────

    def _get_class_periods(self) -> list[ClassPeriod]:
        return get_active_periods(self._settings)

    def _on_import_clicked(self, _btn):
        dlg = ImportCoursesDialog(self, class_periods=self._get_class_periods())

        def on_response(d, response):
            if response == Gtk.ResponseType.OK:
                new_courses = d.get_imported_courses()
                if new_courses:
                    self._apply_imported_courses(new_courses)
            d.close()

        dlg.connect("response", on_response)
        dlg.present()

    def _apply_imported_courses(self, new_courses: list):
        """Add new_courses to the current schedule, handling name conflicts."""
        existing_names = {c.name for c in self._courses}
        conflict_names = sorted({
            c.name for c in new_courses if c.name in existing_names
        })

        if not conflict_names:
            # No conflicts – just add everything
            self._courses.extend(new_courses)
            self._persist_schedules()
            self.refresh_ui()
            return

        # Show conflict resolution dialog
        cdlg = ConflictResolutionDialog(self, conflict_names)

        def on_conflict_response(cd, resp):
            if resp == ConflictResolutionDialog.RESP_SKIP:
                # Only import courses whose names are new
                to_add = [c for c in new_courses if c.name not in existing_names]
                if to_add:
                    self._courses.extend(to_add)
                    self._persist_schedules()
                    self.refresh_ui()
            elif resp == ConflictResolutionDialog.RESP_OVERWRITE:
                # Remove existing courses that share a name with an imported one
                conflict_set = {c.name for c in new_courses}
                self._courses = [c for c in self._courses
                                 if c.name not in conflict_set]
                self._courses.extend(new_courses)
                self._persist_schedules()
                self.refresh_ui()
            # CANCEL / other: do nothing
            cd.close()

        cdlg.connect("response", on_conflict_response)
        cdlg.present()

    def _show_onboarding(self):
        dlg = OnboardingDialog(self)

        def on_response(d, _response):
            self._settings["onboarding_done"] = True
            self._persist_settings()
            d.close()

        dlg.connect("response", on_response)
        dlg.present()
        return False  # Remove GLib.idle_add callback

    def _on_add_clicked(self, _btn):
        dlg = CourseDialog(self, class_periods=self._get_class_periods())

        def on_response(d, response):
            if response == Gtk.ResponseType.OK:
                data = d.get_course_data()
                if data is not None:
                    self._courses.append(data)
                    self._persist_schedules()
                    self.refresh_ui()
                    d.close()
            else:
                d.close()

        dlg.connect("response", on_response)
        dlg.present()

    def _on_edit_clicked(self, _btn, course_id: str):
        course = next((c for c in self._courses if c.id == course_id), None)
        if not course:
            return
        dlg = CourseDialog(self, course=course, class_periods=self._get_class_periods())

        def on_response(d, response):
            if response == Gtk.ResponseType.OK:
                data = d.get_course_data()
                if data is not None:
                    idx = self._courses.index(course)
                    self._courses[idx] = data
                    self._persist_schedules()
                    self.refresh_ui()
                    d.close()
            else:
                d.close()

        dlg.connect("response", on_response)
        dlg.present()

    def _on_delete_clicked(self, _btn, course_id: str):
        self._courses = [c for c in self._courses if c.id != course_id]
        self._persist_schedules()
        self.refresh_ui()

    def _on_about_clicked(self, _btn):
        dlg = Adw.AboutDialog(
            application_name="WadwaitaUp",
            application_icon="x-office-calendar-symbolic",
            version=self._app_version,
            comments="一个 Adwaita 风格的课程表应用",
            website="https://github.com/Nakanomk/WadwaitaUp",
            developer_name="Nakanomk",
            license_type=Gtk.License.MIT_X11,
        )
        dlg.present(self)