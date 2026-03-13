import uuid
import calendar as _cal
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gdk, Pango, GLib
from datetime import datetime, date, timedelta

from models import Course, ClassPeriod, Schedule, HUST_SUMMER_PERIODS, HUST_WINTER_PERIODS
from storage import ScheduleStorage, SettingsStorage
from utils import (
    WEEKDAY_CN,
    sort_courses,
    get_today_courses,
    get_next_course,
    humanize_delta_minutes,
    calc_current_week,
    hhmm_to_minutes,
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
        if idx == 0 or idx > len(self._periods):
            return  # "自定义" selected or out of range — leave time picker as-is
        period = self._periods[idx - 1]
        if combo is self.start_period_combo:
            self.start_picker.set_time(period.start)
        else:
            self.end_picker.set_time(period.end)

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


class GlobalSettingsDialog(Gtk.Dialog):
    """Global settings: color scheme + class periods."""

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
        scheme_row = Adw.ActionRow(title="深色模式")
        self.dark_switch = Gtk.Switch()
        self.dark_switch.set_valign(Gtk.Align.CENTER)
        current = settings.get("color_scheme", "auto")
        self.dark_switch.set_active(current == "dark")
        self.dark_switch.connect("notify::active", self._on_dark_toggled)
        scheme_row.add_suffix(self.dark_switch)
        scheme_row.set_activatable_widget(self.dark_switch)
        scheme_group.add(scheme_row)
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

        content.append(box)

    def _on_dark_toggled(self, switch, _param):
        style_manager = Adw.StyleManager.get_default()
        if switch.get_active():
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            self._settings["color_scheme"] = "dark"
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            self._settings["color_scheme"] = "light"
        # Notify parent to persist
        self._parent.on_color_scheme_changed(self._settings["color_scheme"])

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


# ──────────────────────────── Week Grid View ────────────────────


class WeekGridView(Gtk.ScrolledWindow):
    """
    Full-week timetable grid.
    Columns = Mon–Fri (5 days), rows = class periods, courses = coloured cards.
    The grid expands to fill the available window width.
    """

    # Show Mon–Fri only (5 days) so the grid fills the window
    _NUM_DAYS = 5            # Monday through Friday
    _PERIOD_LABEL_WIDTH = 40  # px – fixed width of the period-label column
    _CELL_HEIGHT = 54         # px – minimum height of every grid row

    def __init__(self):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        # No horizontal scrollbar – the grid always fills available width
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._courses: list = []
        self._periods: list = []
        self._color_map: dict = {}

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.set_margin_top(12)
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
        self.set_child(wrapper)

    # ── public ──────────────────────────────────────────────────

    def refresh(self, courses: list, periods: list) -> None:
        self._courses = courses
        self._periods = periods
        self._color_map = _assign_colors(courses)
        today_wd = datetime.now().weekday() + 1  # 1=Mon … 7=Sun
        self._build(today_wd)

    # ── internals ───────────────────────────────────────────────

    def _clear(self) -> None:
        child = self._grid.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._grid.remove(child)
            child = nxt

    def _build(self, today_wd: int) -> None:
        self._clear()

        today      = date.today()
        week_start = today - timedelta(days=today.weekday())   # Monday
        week_dates = [week_start + timedelta(days=i) for i in range(7)]

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
            is_today = (wd == today_wd)

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

        # ── Compute placements, tracking occupied cells ─────────
        occupied: set   = set()
        placements: list = []          # (course, col, grid_row, span)

        for course in self._courses:
            if course.day > self._NUM_DAYS:
                continue   # skip weekend courses in 5-day view
            pidx, span = _get_period_span(course, self._periods)
            if pidx is None:
                continue
            col      = course.day
            grid_row = pidx + 1        # +1 for header row
            # Skip if conflicting with already-placed course
            if any((col, grid_row + k) in occupied for k in range(span)):
                continue
            for k in range(span):
                occupied.add((col, grid_row + k))
            placements.append((course, col, grid_row, span))

        # ── Period labels + empty-cell placeholders ─────────────
        for ridx, period in enumerate(self._periods):
            grid_row = ridx + 1

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

            for col in range(1, self._NUM_DAYS + 1):
                if (col, grid_row) not in occupied:
                    ph = Gtk.Box()
                    ph.set_hexpand(True)
                    ph.set_size_request(-1, self._CELL_HEIGHT)
                    self._grid.attach(ph, col, grid_row, 1, 1)

        # ── Course cards ──────────────────────────────────────
        for course, col, grid_row, span in placements:
            bg, fg = self._color_map.get(course.id, ("#888888", "#ffffff"))
            card   = self._make_card(course, bg, fg, span)
            self._grid.attach(card, col, grid_row, 1, span)

    def _make_card(self, course: Course, bg: str, fg: str, span: int) -> Gtk.Widget:
        cls = _course_css_class(course.id)
        _ensure_color_class(cls, bg, fg)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_halign(Gtk.Align.FILL)
        box.set_valign(Gtk.Align.FILL)
        box.set_hexpand(True)
        box.add_css_class("course-card")
        box.add_css_class(cls)

        name_lbl = Gtk.Label(label=course.name)
        name_lbl.set_wrap(True)
        name_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        name_lbl.set_max_width_chars(5)
        name_lbl.add_css_class("caption-heading")
        name_lbl.set_justify(Gtk.Justification.CENTER)
        box.append(name_lbl)

        if course.location and span >= 2:
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
    def __init__(self, app):
        super().__init__(application=app)
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

        # ── Header: center – ViewSwitcher + schedule dropdown ───
        self._view_stack = Adw.ViewStack()

        # ViewSwitcher sits in the header centre
        view_switcher = Adw.ViewSwitcher()
        view_switcher.set_stack(self._view_stack)
        view_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)

        # Schedule switcher dropdown also lives in the centre box
        self._schedule_names_model = Gtk.StringList()
        self._rebuild_schedule_model()
        self._schedule_dropdown = Gtk.DropDown(
            model=self._schedule_names_model,
            selected=self._active_idx,
        )
        self._schedule_dropdown.set_tooltip_text("切换课表")
        self._schedule_dropdown.connect("notify::selected", self._on_schedule_switched)

        center_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        center_box.set_halign(Gtk.Align.CENTER)
        center_box.append(self._schedule_dropdown)
        center_box.append(view_switcher)
        header.set_title_widget(center_box)

        # ── Header: right buttons ────────────────────────────────
        self._dark_btn = Gtk.ToggleButton(icon_name="weather-clear-night-symbolic")
        self._dark_btn.set_tooltip_text("切换深色/浅色模式")
        self._dark_btn.set_active(self._settings.get("color_scheme", "auto") == "dark")
        self._dark_btn.connect("toggled", self._on_dark_toggled)
        header.pack_end(self._dark_btn)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("添加课程")
        add_btn.connect("clicked", self._on_add_clicked)
        header.pack_end(add_btn)

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

        # ── Bottom switcher bar (shown on narrow windows) ────────
        switcher_bar = Adw.ViewSwitcherBar()
        switcher_bar.set_stack(self._view_stack)
        switcher_bar.set_reveal(True)
        toolbar_view.add_bottom_bar(switcher_bar)

        toolbar_view.set_content(self._view_stack)
        self.set_content(toolbar_view)

        self.refresh_ui()



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
        self._persist_settings()
        # Keep the header toggle in sync
        self._dark_btn.handler_block_by_func(self._on_dark_toggled)
        self._dark_btn.set_active(scheme == "dark")
        self._dark_btn.handler_unblock_by_func(self._on_dark_toggled)

    def on_periods_changed(self, periods_raw: list):
        """Called by GlobalSettingsDialog when periods are saved."""
        self._settings["class_periods"] = periods_raw
        self._persist_settings()

    # ── UI refresh ───────────────────────────────────────────────

    def _clear_listbox(self, listbox: Gtk.ListBox):
        child = listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            listbox.remove(child)
            child = nxt

    def _make_row(self, course: Course) -> Gtk.ListBoxRow:
        subtitle_parts = [f"{WEEKDAY_CN[course.day]} {course.start}–{course.end}"]
        if course.location:
            subtitle_parts.append(course.location)
        if course.teacher:
            subtitle_parts.append(course.teacher)
        subtitle_parts.append(f"第{course.weeks}周")

        row = Adw.ActionRow(title=course.name, subtitle=" · ".join(subtitle_parts))

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
        today_courses = get_today_courses(self._courses)
        if today_courses:
            for c in today_courses:
                self._today_list.append(self._make_row(c))
        else:
            empty = Gtk.ListBoxRow()
            empty.set_child(Adw.ActionRow(title="今天没有课", subtitle="享受一下空闲时间 ☕"))
            self._today_list.append(empty)

        self._clear_listbox(self._week_list)
        if self._courses:
            for c in self._courses:
                self._week_list.append(self._make_row(c))
        else:
            empty = Gtk.ListBoxRow()
            empty.set_child(Adw.ActionRow(title="还没有课程", subtitle="先添加几门课吧"))
            self._week_list.append(empty)

        # ── Refresh grid views ──────────────────────────────────
        periods = _periods_from_settings(self._settings)
        self._week_grid.refresh(self._courses, periods)
        color_map = _assign_colors(self._courses)
        self._month_view.refresh(self._courses, color_map)


    # ── header button callbacks ──────────────────────────────────

    def _on_dark_toggled(self, btn):
        scheme = "dark" if btn.get_active() else "light"
        self._apply_color_scheme(scheme)
        self._settings["color_scheme"] = scheme
        self._persist_settings()

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
        return _periods_from_settings(self._settings)

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