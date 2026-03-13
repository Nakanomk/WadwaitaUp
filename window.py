import uuid
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from models import Course, ClassPeriod, Schedule
from storage import ScheduleStorage, SettingsStorage
from utils import (
    WEEKDAY_CN,
    sort_courses,
    get_today_courses,
    get_next_course,
    humanize_delta_minutes,
    is_valid_hhmm,
    calc_current_week,
)

# ─────────────────────────── helpers ────────────────────────────


def _periods_from_settings(settings: dict) -> list[ClassPeriod]:
    return [ClassPeriod.from_dict(p) for p in settings.get("class_periods", [])]


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
        self.start_entry = Gtk.Entry(placeholder_text="08:00")
        self.end_entry = Gtk.Entry(placeholder_text="09:35")

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
        # Manual time entries (still editable)
        grid.attach(Gtk.Label(label="开始时间", xalign=0), 0, row, 1, 1)
        grid.attach(self.start_entry, 1, row, 1, 1)
        row += 1
        grid.attach(Gtk.Label(label="结束时间", xalign=0), 0, row, 1, 1)
        grid.attach(self.end_entry, 1, row, 1, 1)
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
            self.start_entry.set_text(course.start)
            self.end_entry.set_text(course.end)
            self.location_entry.set_text(course.location)
            self.teacher_entry.set_text(course.teacher)
            self.weeks_entry.set_text(course.weeks)

    # ── period picker callbacks ──────────────────────────────────

    def _on_period_changed(self, combo, _param):
        idx = combo.get_selected()
        if idx == 0 or idx > len(self._periods):
            return  # "自定义" selected or out of range — leave time entry as-is
        period = self._periods[idx - 1]
        if combo is self.start_period_combo:
            self.start_entry.set_text(period.start)
        else:
            self.end_entry.set_text(period.end)

    # ── public ──────────────────────────────────────────────────

    def get_course_data(self) -> Course | None:
        name = self.name_entry.get_text().strip()
        day = self.day_combo.get_selected() + 1
        start = self.start_entry.get_text().strip()
        end = self.end_entry.get_text().strip()
        location = self.location_entry.get_text().strip()
        teacher = self.teacher_entry.get_text().strip()
        weeks = self.weeks_entry.get_text().strip() or "1-20"

        if not name:
            self.error_label.set_text("课程名不能为空")
            self.error_label.set_visible(True)
            return None
        if not is_valid_hhmm(start) or not is_valid_hhmm(end):
            self.error_label.set_text("时间格式必须是 HH:MM，例如 08:00")
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
        self.start_entry = Gtk.Entry(placeholder_text="YYYY-MM-DD")
        self.total_weeks = Gtk.SpinButton.new_with_range(1, 40, 1)
        self.total_weeks.set_value(20.0)

        self.error_label = Gtk.Label(xalign=0)
        self.error_label.add_css_class("error")
        self.error_label.set_visible(False)

        grid.attach(Gtk.Label(label="课表名称", xalign=0),   0, 0, 1, 1)
        grid.attach(self.name_entry,                          1, 0, 1, 1)
        grid.attach(Gtk.Label(label="学期开始日期", xalign=0), 0, 1, 1, 1)
        grid.attach(self.start_entry,                         1, 1, 1, 1)
        grid.attach(Gtk.Label(label="总周数", xalign=0),     0, 2, 1, 1)
        grid.attach(self.total_weeks,                         1, 2, 1, 1)
        grid.attach(self.error_label,                         0, 3, 2, 1)
        content.append(grid)

        if schedule:
            self.name_entry.set_text(schedule.name)
            self.start_entry.set_text(schedule.term_start_date)
            self.total_weeks.set_value(float(schedule.total_weeks))

    def get_data(self) -> dict | None:
        from datetime import datetime
        name = self.name_entry.get_text().strip()
        start = self.start_entry.get_text().strip()
        total = int(self.total_weeks.get_value())

        if not name:
            self.error_label.set_text("课表名称不能为空")
            self.error_label.set_visible(True)
            return None
        if start:
            try:
                datetime.strptime(start, "%Y-%m-%d")
            except Exception:
                self.error_label.set_text("日期格式错误，请用 YYYY-MM-DD")
                self.error_label.set_visible(True)
                return None
        return {"name": name, "term_start_date": start, "total_weeks": total}


class ClassPeriodsDialog(Gtk.Dialog):
    """Edit the list of class-period time slots (global setting)."""

    _HELP = (
        "每行一个节次，格式：HH:MM-HH:MM\n"
        "节次编号按行顺序自动分配。"
    )

    def __init__(self, parent: Gtk.Window, class_periods: list[ClassPeriod]):
        super().__init__(title="节次时间设置", modal=True, transient_for=parent)
        self.set_default_size(320, 420)

        self.add_button("取消", Gtk.ResponseType.CANCEL)
        self.add_button("保存", Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        help_lbl = Gtk.Label(label=self._HELP, xalign=0, wrap=True)
        help_lbl.add_css_class("dim-label")
        box.append(help_lbl)

        self.text_view = Gtk.TextView()
        self.text_view.set_monospace(True)
        self.text_view.set_wrap_mode(Gtk.WrapMode.NONE)
        lines = "\n".join(f"{p.start}-{p.end}" for p in class_periods)
        self.text_view.get_buffer().set_text(lines)

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(self.text_view)
        box.append(sw)

        self.error_label = Gtk.Label(xalign=0, wrap=True)
        self.error_label.add_css_class("error")
        self.error_label.set_visible(False)
        box.append(self.error_label)

        content.append(box)

    def get_periods(self) -> list[ClassPeriod] | None:
        buf = self.text_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        periods: list[ClassPeriod] = []
        for idx, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            parts = line.split("-")
            if len(parts) != 2 or not is_valid_hhmm(parts[0]) or not is_valid_hhmm(parts[1]):
                self.error_label.set_text(f"第 {idx} 行格式有误（应为 HH:MM-HH:MM）")
                self.error_label.set_visible(True)
                return None
            periods.append(ClassPeriod(period=idx, start=parts[0], end=parts[1]))
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
        edit_periods_btn = Gtk.Button(label="编辑节次时间…")
        edit_periods_btn.add_css_class("pill")
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


# ──────────────────────────── main window ───────────────────────


class WadwaitaUpWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("WadwaitaUp 课程表")
        self.set_default_size(520, 760)

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

        # Left: global settings button
        settings_btn = Gtk.Button(icon_name="emblem-system-symbolic")
        settings_btn.set_tooltip_text("全局设置（节次时间 / 外观）")
        settings_btn.connect("clicked", self._on_global_settings_clicked)
        header.pack_start(settings_btn)

        # Left: edit current schedule button
        edit_schedule_btn = Gtk.Button(icon_name="document-edit-symbolic")
        edit_schedule_btn.set_tooltip_text("编辑当前课表信息")
        edit_schedule_btn.connect("clicked", self._on_edit_schedule_clicked)
        header.pack_start(edit_schedule_btn)

        # Center title widget: schedule switcher dropdown
        self._schedule_names_model = Gtk.StringList()
        self._rebuild_schedule_model()

        self._schedule_dropdown = Gtk.DropDown(
            model=self._schedule_names_model,
            selected=self._active_idx,
        )
        self._schedule_dropdown.set_tooltip_text("切换课表")
        self._schedule_dropdown.connect("notify::selected", self._on_schedule_switched)
        header.set_title_widget(self._schedule_dropdown)

        # Right: dark-mode toggle
        self._dark_btn = Gtk.ToggleButton(icon_name="weather-clear-night-symbolic")
        self._dark_btn.set_tooltip_text("切换深色/浅色模式")
        self._dark_btn.set_active(self._settings.get("color_scheme", "auto") == "dark")
        self._dark_btn.connect("toggled", self._on_dark_toggled)
        header.pack_end(self._dark_btn)

        # Right: add course button
        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("添加课程")
        add_btn.connect("clicked", self._on_add_clicked)
        header.pack_end(add_btn)

        # Right: add schedule button
        add_schedule_btn = Gtk.Button(icon_name="folder-new-symbolic")
        add_schedule_btn.set_tooltip_text("新建课表")
        add_schedule_btn.connect("clicked", self._on_add_schedule_clicked)
        header.pack_end(add_schedule_btn)

        # Right: delete schedule button
        self._del_schedule_btn = Gtk.Button(icon_name="edit-delete-symbolic")
        self._del_schedule_btn.set_tooltip_text("删除当前课表")
        self._del_schedule_btn.connect("clicked", self._on_delete_schedule_clicked)
        header.pack_end(self._del_schedule_btn)

        # ── Body ────────────────────────────────────────────────
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)

        term_group = Adw.PreferencesGroup(title="学期信息")
        self._term_row = Adw.ActionRow(title="未设置学期开始日期", subtitle="点击左上角铅笔图标设置")
        term_group.add(self._term_row)
        root.append(term_group)

        next_group = Adw.PreferencesGroup(title="下一节课")
        self._next_row = Adw.ActionRow(title="暂无课程", subtitle="请先添加课程")
        next_group.add(self._next_row)
        root.append(next_group)

        today_title = Gtk.Label(label="今天")
        today_title.set_xalign(0)
        today_title.add_css_class("title-4")
        root.append(today_title)

        self._today_list = Gtk.ListBox()
        self._today_list.add_css_class("boxed-list")
        self._today_list.set_selection_mode(Gtk.SelectionMode.NONE)
        root.append(self._today_list)

        week_title = Gtk.Label(label="本周全部课程")
        week_title.set_xalign(0)
        week_title.add_css_class("title-4")
        root.append(week_title)

        self._week_list = Gtk.ListBox()
        self._week_list.add_css_class("boxed-list")
        self._week_list.set_selection_mode(Gtk.SelectionMode.NONE)
        root.append(self._week_list)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(root)
        toolbar_view.set_content(scrolled)
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