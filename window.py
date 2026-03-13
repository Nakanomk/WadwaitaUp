import uuid
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from models import Course
from storage import CourseStorage, SettingsStorage
from utils import (
    WEEKDAY_CN,
    sort_courses,
    get_today_courses,
    get_next_course,
    humanize_delta_minutes,
    is_valid_hhmm,
    calc_current_week,
)


class CourseDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, course: Course | None = None):
        super().__init__(title="添加课程" if course is None else "编辑课程", modal=True, transient_for=parent)
        self.set_default_size(420, 420)
        self.course = course

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
        self.day_combo = Gtk.DropDown.new_from_strings([WEEKDAY_CN[i] for i in range(1, 8)])
        self.start_entry = Gtk.Entry(placeholder_text="08:00")
        self.end_entry = Gtk.Entry(placeholder_text="09:35")
        self.error_label = Gtk.Label(xalign=0)
        self.error_label.add_css_class("error")
        self.error_label.set_visible(False)

        grid.attach(Gtk.Label(label="课程名", xalign=0), 0, 0, 1, 1)
        grid.attach(self.name_entry, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="星期", xalign=0), 0, 1, 1, 1)
        grid.attach(self.day_combo, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label="开始时间", xalign=0), 0, 2, 1, 1)
        grid.attach(self.start_entry, 1, 2, 1, 1)
        grid.attach(Gtk.Label(label="结束时间", xalign=0), 0, 3, 1, 1)
        grid.attach(self.end_entry, 1, 3, 1, 1)
        grid.attach(Gtk.Label(label="地点", xalign=0), 0, 4, 1, 1)
        grid.attach(self.location_entry, 1, 4, 1, 1)
        grid.attach(Gtk.Label(label="教师", xalign=0), 0, 5, 1, 1)
        grid.attach(self.teacher_entry, 1, 5, 1, 1)
        grid.attach(Gtk.Label(label="周次", xalign=0), 0, 6, 1, 1)
        grid.attach(self.weeks_entry, 1, 6, 1, 1)
        grid.attach(self.error_label, 0, 7, 2, 1)

        content.append(grid)

        if course:
            self.name_entry.set_text(course.name)
            self.day_combo.set_selected(course.day - 1)
            self.start_entry.set_text(course.start)
            self.end_entry.set_text(course.end)
            self.location_entry.set_text(course.location)
            self.teacher_entry.set_text(course.teacher)
            self.weeks_entry.set_text(course.weeks)

    def get_course_data(self):
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
            id=cid,
            name=name,
            day=day,
            start=start,
            end=end,
            location=location,
            teacher=teacher,
            weeks=weeks,
        )


class TermSettingsDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, settings: dict):
        super().__init__(title="学期设置", modal=True, transient_for=parent)
        self.set_default_size(380, 180)

        self.add_button("取消", Gtk.ResponseType.CANCEL)
        self.add_button("保存", Gtk.ResponseType.OK)

        content = self.get_content_area()
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)

        self.start_entry = Gtk.Entry(placeholder_text="YYYY-MM-DD")
        self.start_entry.set_text(settings.get("term_start_date", ""))

        self.total_weeks = Gtk.SpinButton.new_with_range(1, 40, 1)
        self.total_weeks.set_value(float(settings.get("total_weeks", 20)))

        self.error_label = Gtk.Label(xalign=0)
        self.error_label.add_css_class("error")
        self.error_label.set_visible(False)

        grid.attach(Gtk.Label(label="学期开始日期", xalign=0), 0, 0, 1, 1)
        grid.attach(self.start_entry, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="总周数", xalign=0), 0, 1, 1, 1)
        grid.attach(self.total_weeks, 1, 1, 1, 1)
        grid.attach(self.error_label, 0, 2, 2, 1)

        content.append(grid)

    def get_settings(self):
        from datetime import datetime

        start = self.start_entry.get_text().strip()
        total = int(self.total_weeks.get_value())

        if start:
            try:
                datetime.strptime(start, "%Y-%m-%d")
            except Exception:
                self.error_label.set_text("日期格式错误，请用 YYYY-MM-DD")
                self.error_label.set_visible(True)
                return None

        return {
            "term_start_date": start,
            "total_weeks": total
        }


class WakeupWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("Wakeup 课程表")
        self.set_default_size(520, 760)

        self.storage = CourseStorage()
        self.settings_storage = SettingsStorage()

        self.courses = sort_courses(self.storage.load())
        self.settings = self.settings_storage.load()

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        settings_btn = Gtk.Button(icon_name="emblem-system-symbolic")
        settings_btn.set_tooltip_text("学期设置")
        settings_btn.connect("clicked", self.on_settings_clicked)
        header.pack_start(settings_btn)

        add_btn = Gtk.Button(icon_name="list-add-symbolic")
        add_btn.set_tooltip_text("添加课程")
        add_btn.connect("clicked", self.on_add_clicked)
        header.pack_end(add_btn)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)

        term_group = Adw.PreferencesGroup(title="学期信息")
        self.term_row = Adw.ActionRow(title="未设置学期开始日期", subtitle="点击左上角设置")
        term_group.add(self.term_row)
        root.append(term_group)

        next_group = Adw.PreferencesGroup(title="下一节课")
        self.next_row = Adw.ActionRow(title="暂无课程", subtitle="请先添加课程")
        next_group.add(self.next_row)
        root.append(next_group)

        today_title = Gtk.Label(label="今天")
        today_title.set_xalign(0)
        today_title.add_css_class("title-4")
        root.append(today_title)

        self.today_list = Gtk.ListBox()
        self.today_list.add_css_class("boxed-list")
        self.today_list.set_selection_mode(Gtk.SelectionMode.NONE)
        root.append(self.today_list)

        week_title = Gtk.Label(label="本周全部课程")
        week_title.set_xalign(0)
        week_title.add_css_class("title-4")
        root.append(week_title)

        self.week_list = Gtk.ListBox()
        self.week_list.add_css_class("boxed-list")
        self.week_list.set_selection_mode(Gtk.SelectionMode.NONE)
        root.append(self.week_list)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(root)
        toolbar_view.set_content(scrolled)
        self.set_content(toolbar_view)

        self.refresh_ui()

    def persist_courses(self):
        self.courses = sort_courses(self.courses)
        self.storage.save(self.courses)

    def persist_settings(self):
        self.settings_storage.save(self.settings)

    def _clear_listbox(self, listbox: Gtk.ListBox):
        child = listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            listbox.remove(child)
            child = nxt

    def _make_row(self, course: Course) -> Gtk.ListBoxRow:
        subtitle_parts = [f"{WEEKDAY_CN[course.day]} {course.start}-{course.end}"]
        if course.location:
            subtitle_parts.append(course.location)
        if course.teacher:
            subtitle_parts.append(course.teacher)
        subtitle_parts.append(f"第{course.weeks}周")

        row = Adw.ActionRow(title=course.name, subtitle=" · ".join(subtitle_parts))

        edit_btn = Gtk.Button(icon_name="document-edit-symbolic")
        edit_btn.add_css_class("flat")
        edit_btn.set_tooltip_text("编辑")
        edit_btn.connect("clicked", self.on_edit_clicked, course.id)
        row.add_suffix(edit_btn)

        del_btn = Gtk.Button(icon_name="user-trash-symbolic")
        del_btn.add_css_class("flat")
        del_btn.set_tooltip_text("删除")
        del_btn.connect("clicked", self.on_delete_clicked, course.id)
        row.add_suffix(del_btn)

        wrapper = Gtk.ListBoxRow()
        wrapper.set_child(row)
        return wrapper

    def refresh_ui(self):
        term_start = self.settings.get("term_start_date", "")
        total_weeks = self.settings.get("total_weeks", 20)
        current_week = calc_current_week(term_start)

        if term_start:
            if current_week is None:
                self.term_row.set_title("学期日期格式错误")
                self.term_row.set_subtitle("请在设置中修正")
            elif current_week == 0:
                self.term_row.set_title(f"学期将开始（{term_start}）")
                self.term_row.set_subtitle(f"总周数 {total_weeks} 周")
            else:
                self.term_row.set_title(f"当前第 {current_week} 周")
                self.term_row.set_subtitle(f"学期开始于 {term_start} · 总周数 {total_weeks} 周")
        else:
            self.term_row.set_title("未设置学期开始日期")
            self.term_row.set_subtitle("点击左上角设置")

        next_course, delta = get_next_course(self.courses)
        if next_course:
            self.next_row.set_title(next_course.name)
            self.next_row.set_subtitle(
                f"{WEEKDAY_CN[next_course.day]} {next_course.start}-{next_course.end} · "
                f"{next_course.location or '地点未设置'} · {humanize_delta_minutes(delta)}"
            )
        else:
            self.next_row.set_title("暂无课程")
            self.next_row.set_subtitle("点击右上角 + 添加课程")

        self._clear_listbox(self.today_list)
        today_courses = get_today_courses(self.courses)
        if today_courses:
            for c in today_courses:
                self.today_list.append(self._make_row(c))
        else:
            empty = Gtk.ListBoxRow()
            empty.set_child(Adw.ActionRow(title="今天没有课", subtitle="享受一下空闲时间 ☕"))
            self.today_list.append(empty)

        self._clear_listbox(self.week_list)
        if self.courses:
            for c in self.courses:
                self.week_list.append(self._make_row(c))
        else:
            empty = Gtk.ListBoxRow()
            empty.set_child(Adw.ActionRow(title="还没有课程", subtitle="先添加几门课吧"))
            self.week_list.append(empty)

    def on_settings_clicked(self, _btn):
        dialog = TermSettingsDialog(self, self.settings)

        def on_settings_response(dlg, response):
            if response == Gtk.ResponseType.OK:
                data = dlg.get_settings()
                if data is not None:
                    self.settings = data
                    self.persist_settings()
                    self.refresh_ui()
                    dlg.close()
            else:
                dlg.close()

        dialog.connect("response", on_settings_response)
        dialog.present()

    def on_add_clicked(self, _btn):
        dialog = CourseDialog(self)

        def on_add_response(dlg, response):
            if response == Gtk.ResponseType.OK:
                data = dlg.get_course_data()
                if data is not None:
                    self.courses.append(data)
                    self.persist_courses()
                    self.refresh_ui()
                    dlg.close()
            else:
                dlg.close()

        dialog.connect("response", on_add_response)
        dialog.present()

    def on_edit_clicked(self, _btn, course_id: str):
        course = next((c for c in self.courses if c.id == course_id), None)
        if not course:
            return

        dialog = CourseDialog(self, course=course)

        def on_edit_response(dlg, response):
            if response == Gtk.ResponseType.OK:
                data = dlg.get_course_data()
                if data is not None:
                    idx = self.courses.index(course)
                    self.courses[idx] = data
                    self.persist_courses()
                    self.refresh_ui()
                    dlg.close()
            else:
                dlg.close()

        dialog.connect("response", on_edit_response)
        dialog.present()

    def on_delete_clicked(self, _btn, course_id: str):
        self.courses = [c for c in self.courses if c.id != course_id]
        self.persist_courses()
        self.refresh_ui()