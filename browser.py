"""
Built-in browser for importing courses from HUST HUB system.

No background polling — user clicks "提取课程" when the table is visible.
A single JS extraction runs and returns results + diagnostics.
"""

import json
import logging
from typing import Any, Optional

import gi

try:
    gi.require_version("WebKit", "6.0")
    gi.require_version("JavaScriptCore", "6.0")
    from gi.repository import WebKit, JavaScriptCore, Gtk, Adw, GLib, Gio, GObject
    WEBKIT_AVAILABLE = True
except (ImportError, ValueError):
    WEBKIT_AVAILABLE = False

from models import Course

logger = logging.getLogger(__name__)

# ── Extraction script ─────────────────────────────────────────────
# Runs ONCE on user click.  Walks only .el-table / .el-tabs subtrees.
# Returns JSON with {found, courses, total_weeks, semester, term_start,
# diagnostics: {total_items, skipped_no_name, skipped_bad_period, ...}}

_EXTRACT_SCRIPT = r"""
(function() {
    var diag = { total_items: 0, skipped_no_name: 0, skipped_bad_period: 0,
                 found_courses: 0, weeks: 0 };

    // ── Walk UP the Vue tree from a known element ───────────
    function findWeekTableDataFrom(el) {
        var vm = el.__vue__;
        while (vm) {
            if (vm.weekTableData && Array.isArray(vm.weekTableData) && vm.weekTableData.length > 0) {
                return vm.weekTableData;
            }
            if (vm.$data && vm.$data.weekTableData && vm.$data.weekTableData.length > 0) {
                return vm.$data.weekTableData;
            }
            vm = vm.$parent;
        }
        return null;
    }

    var data = null;
    var tableEl = document.querySelector('.el-table');
    if (tableEl) { data = findWeekTableDataFrom(tableEl); }
    if (!data) {
        var tabsEl = document.querySelector('.el-tabs');
        if (tabsEl) { data = findWeekTableDataFrom(tabsEl); }
    }
    if (!data) {
        data = findWeekTableDataFrom(document.body);
    }

    if (!data) return JSON.stringify({ found: false, reason: 'no_vue_data' });

    diag.weeks = data.length;

    // ── Convert to WadwaitaUp format ─────────────────────────
    var DAY_KEYS = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY'];

    function parsePeriod(jc) {
        if (!jc) return [0, 0];
        var s = String(jc).trim();
        // Common: "1-2", "3-4", "5-6" → [1,2], [3,4], [5,6]
        var m = s.match(/^(\d+)\s*[-–—]\s*(\d+)$/);
        if (m) return [parseInt(m[1], 10), parseInt(m[2], 10)];
        // Single number: "3" → [3,3]
        m = s.match(/^(\d+)$/);
        if (m) {
            var n = parseInt(m[1], 10);
            return [n, n];
        }
        // Non-standard values like "实践", "全天", "上午" → fallback
        return [-1, -1];  // sentinel: keep but mark as unknown
    }

    function compactWeeks(arr) {
        if (!arr || arr.length === 0) return '';
        var ranges = [];
        var start = arr[0], end = arr[0];
        for (var i = 1; i < arr.length; i++) {
            if (arr[i] === end + 1) { end = arr[i]; }
            else {
                ranges.push(start === end ? String(start) : start + '-' + end);
                start = arr[i]; end = arr[i];
            }
        }
        ranges.push(start === end ? String(start) : start + '-' + end);
        return ranges.join(',');
    }

    var courseMap = new Map();
    var termStart = '';

    for (var wi = 0; wi < data.length; wi++) {
        var weekRow = data[wi];
        var weekNum = parseInt(weekRow.ZC, 10);
        if (isNaN(weekNum)) continue;

        // Extract term start date from first week
        if (!termStart && weekRow.KS) {
            termStart = String(weekRow.KS).trim();
        }

        for (var di = 0; di < DAY_KEYS.length; di++) {
            var dayNum = di + 1;
            var courses = weekRow[DAY_KEYS[di]];
            if (!Array.isArray(courses)) continue;

            for (var ci = 0; ci < courses.length; ci++) {
                var item = courses[ci];
                diag.total_items++;

                var name = (item.KCMC || '').trim();
                if (!name) { diag.skipped_no_name++; continue; }

                var pp = parsePeriod(item.JC);
                var sp = pp[0], ep = pp[1];
                // sp == -1 means non-standard JC (e.g. "实践", "全天")
                // Keep the course but mark period as unknown
                if (sp <= 0) {
                    diag.skipped_bad_period++;
                    sp = 1; ep = 1;  // fallback — user should fix in WadwaitaUp
                }

                var key = name + '|' + dayNum + '|' + sp + '-' + ep;
                var location = (item.JSMC || '').trim();

                if (!courseMap.has(key)) {
                    courseMap.set(key, {
                        name: name, day: dayNum, location: location,
                        teacher: '', weeks_list: [],
                        start_period: sp, end_period: ep,
                    });
                }
                courseMap.get(key).weeks_list.push(weekNum);
            }
        }
    }

    var courses = [];
    courseMap.forEach(function(c) {
        var weeksArr = c.weeks_list.sort(function(a, b) { return a - b; });
        courses.push({
            name: c.name, day: c.day,
            start_period: c.start_period, end_period: c.end_period,
            location: c.location, teacher: c.teacher,
            weeks: compactWeeks(weeksArr),
        });
    });
    courses.sort(function(a, b) {
        return a.day !== b.day ? a.day - b.day : a.start_period - b.start_period;
    });

    diag.found_courses = courses.length;

    return JSON.stringify({
        found: true, courses: courses,
        total_weeks: data.length, semester: '',
        term_start: termStart,
        diagnostics: diag,
    });
})();
"""


# ── Helper ────────────────────────────────────────────────────────

def _parse_js_result(js_value) -> dict:
    """Convert a JavaScriptCore.Value (JS string) to a Python dict."""
    if js_value is None:
        return {}
    if js_value.is_string():
        try:
            return json.loads(js_value.to_string())
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


# ═══════════════════════════════════════════════════════════════════
#  HustImportWindow
# ═══════════════════════════════════════════════════════════════════

class HustImportWindow(Adw.Window):
    """Embedded WebView for HUST HUB course extraction — single-click."""

    __gsignals__ = {
        "courses-extracted": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (GObject.TYPE_PYOBJECT, GObject.TYPE_STRING, GObject.TYPE_STRING),
        ),
    }

    HUB_URL = "https://hubs.hust.edu.cn/basicInformation/scheduleInformation/index"

    GUIDE = (
        "📋 使用说明：\n"
        "① 在上方页面登录 HUSTPass 账号\n"
        "② 点击左侧菜单「课表信息」\n"
        "③ 点击顶部「总课表」标签 → 选择学期\n"
        "④ 等待课表表格显示完整后，点击右上角「📥 提取课程」"
    )

    def __init__(self, parent: Optional[Gtk.Window] = None):
        super().__init__(
            title="从 HUST 教务系统导入课表",
            transient_for=parent,
            modal=True,
        )
        self.set_default_size(1024, 720)
        self.set_size_request(800, 600)

        if not WEBKIT_AVAILABLE:
            self._show_webkit_error()
            return

        self._extracted_courses: list[dict] = []
        self._term_start: str = ""

        # ── UI ─────────────────────────────────────────────────
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()

        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        nav_box.add_css_class("linked")
        for icon, tip, action in [
            ("go-previous-symbolic", "后退", lambda: self._webview.go_back()),
            ("go-next-symbolic", "前进", lambda: self._webview.go_forward()),
            ("view-refresh-symbolic", "刷新", lambda: self._webview.reload()),
        ]:
            btn = Gtk.Button(icon_name=icon)
            btn.set_tooltip_text(tip)
            btn.add_css_class("flat")
            btn.connect("clicked", lambda _b, a=action: a())
            nav_box.append(btn)
        header.pack_start(nav_box)

        goto_btn = Gtk.Button(label="🔗 课表页面")
        goto_btn.set_tooltip_text("直接跳转到课表查询页面")
        goto_btn.add_css_class("flat")
        goto_btn.connect("clicked", lambda _b: self._webview.load_uri(self.HUB_URL))
        header.pack_start(goto_btn)

        self._extract_btn = Gtk.Button(label="📥 提取课程")
        self._extract_btn.add_css_class("suggested-action")
        self._extract_btn.set_tooltip_text("提取当前页面上的课表数据")
        self._extract_btn.connect("clicked", self._on_extract_clicked)
        header.pack_end(self._extract_btn)

        toolbar.add_top_bar(header)

        # ── WebView ───────────────────────────────────────────
        self._webview = WebKit.WebView()
        self._webview.set_vexpand(True)
        self._webview.set_hexpand(True)

        ns = self._webview.get_network_session()
        cm = ns.get_cookie_manager()
        cm.set_accept_policy(WebKit.CookieAcceptPolicy.ALWAYS)
        cm.set_persistent_storage(
            GLib.get_user_data_dir() + "/wadwaitaup/cookies.sqlite",
            WebKit.CookiePersistentStorage.SQLITE,
        )

        self._webview.connect("load-changed", self._on_load_changed)
        self._webview.load_uri(self.HUB_URL)

        sw = Gtk.ScrolledWindow()
        sw.set_child(self._webview)
        toolbar.set_content(sw)

        # ── Guide bar ─────────────────────────────────────────
        guide_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        guide_box.add_css_class("mascot-card")
        guide_box.set_margin_start(12)
        guide_box.set_margin_end(12)
        guide_box.set_margin_bottom(6)

        self._guide_label = Gtk.Label(label=self.GUIDE)
        self._guide_label.set_xalign(0.0)
        self._guide_label.set_wrap(True)
        self._guide_label.set_hexpand(True)
        guide_box.append(self._guide_label)
        toolbar.add_bottom_bar(guide_box)

        self.set_content(toolbar)

    # ── URL monitoring ────────────────────────────────────────

    def _on_load_changed(self, webview, load_event):
        if load_event != WebKit.LoadEvent.FINISHED:
            return
        uri = webview.get_uri() or ""
        if "scheduleInformation" in uri:
            self._guide_label.set_text(
                "📍 已到达课表页面。\n"
                "👉 请点击「总课表」标签 → 选择学期 → 等待课表加载，然后点击「📥 提取课程」"
            )
        elif "login" in uri.lower() or "hustpass" in uri.lower():
            self._guide_label.set_text("🔐 请使用 HUSTPass 账号登录")

    # ── Extraction ────────────────────────────────────────────

    def _on_extract_clicked(self, _btn):
        self._extract_btn.set_sensitive(False)
        self._extract_btn.set_label("⏳ 提取中…")
        self._guide_label.set_text("⏳ 正在从页面提取课表数据…")
        self._webview.evaluate_javascript(
            _EXTRACT_SCRIPT, -1, None, None, None,
            self._on_extract_result, None,
        )

    def _on_extract_result(self, webview, result, _user_data):
        self._extract_btn.set_label("📥 提取课程")
        self._extract_btn.set_sensitive(True)

        try:
            js_value = webview.evaluate_javascript_finish(result)
            info = _parse_js_result(js_value)
        except Exception as exc:
            self._guide_label.set_text(f"❌ 提取失败：{exc}")
            return

        if not isinstance(info, dict) or not info.get("found"):
            reason = info.get("reason", "unknown") if isinstance(info, dict) else "format error"
            self._guide_label.set_text(
                f"❌ 未检测到课表数据（{reason}）。\n"
                f"请确认：已切换到「总课表」标签、已选择学期、课表表格已完整显示。"
            )
            return

        courses_raw = info.get("courses", [])
        if not courses_raw:
            self._guide_label.set_text("❌ 未提取到任何课程，请检查课表是否已加载完整。")
            return

        self._extracted_courses = courses_raw
        self._term_start = info.get("term_start", "")

        # Show diagnostics
        diag = info.get("diagnostics", {})
        n = len(courses_raw)
        diag_msg = f"✅ 成功提取 {n} 门课程"
        if diag:
            diag_msg += (
                f"（共扫描 {diag.get('total_items', 0)} 条，"
                f"跳过无名课程 {diag.get('skipped_no_name', 0)} 条，"
                f"非标准节次 {diag.get('skipped_bad_period', 0)} 条）"
            )
        self._guide_label.set_text(diag_msg)
        self._show_import_dialog()

    # ── Import dialog ─────────────────────────────────────────

    def _show_import_dialog(self):
        n = len(self._extracted_courses)
        dlg = Adw.MessageDialog(
            transient_for=self,
            heading=f"已提取 {n} 门课程",
            body=f"从课表页面提取到 {n} 门课程。请选择导入方式：",
        )
        dlg.add_response("cancel", "取消")
        dlg.add_response("overwrite", "覆盖当前课表")
        dlg.add_response("add", "添加到当前课表")
        dlg.add_response("new", "新建课表")
        dlg.set_response_appearance("overwrite", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_response_appearance("new", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("add")
        dlg.set_close_response("cancel")

        def on_response(d, response):
            if response != "cancel":
                self.emit("courses-extracted", self._extracted_courses, response, self._term_start)
            d.close()
            self.close()

        dlg.connect("response", on_response)
        dlg.present()

    # ── Error fallback ────────────────────────────────────────

    def _show_webkit_error(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        box.set_margin_top(60)
        box.set_margin_bottom(60)
        box.set_margin_start(40)
        box.set_margin_end(40)
        icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        icon.set_pixel_size(64)
        box.append(icon)
        title = Gtk.Label(label="需要安装 WebKitGTK")
        title.add_css_class("title-2")
        box.append(title)
        body = Gtk.Label(
            label=(
                "内置浏览器功能需要 WebKitGTK 4.1。\n\n"
                "安装命令：\n"
                "  Arch:     sudo pacman -S webkit2gtk-4.1\n"
                "  Fedora:   sudo dnf install webkit2gtk4.1\n"
                "  Debian:   sudo apt install libwebkit2gtk-4.1-0 gir1.2-webkit2-4.1"
            ),
            wrap=True, justify=Gtk.Justification.CENTER,
        )
        body.add_css_class("dim-label")
        body.set_max_width_chars(50)
        box.append(body)
        self.set_content(box)

    def do_close_request(self):
        try:
            self._webview.stop_loading()
        except Exception:
            pass
        try:
            self._webview.try_close()
        except Exception:
            pass
        Adw.Window.do_close_request(self)


# ── Helper ─────────────────────────────────────────────────────

def raw_to_courses(raw_courses: list[dict], periods: Optional[list] = None) -> list[Course]:
    """Convert extracted course dicts to Course objects."""
    import uuid as _uuid
    courses: list[Course] = []
    for item in raw_courses:
        name = item.get("name", "").strip()
        if not name:
            continue
        day = int(item.get("day", 1))
        sp = int(item.get("start_period", 1))
        ep = int(item.get("end_period", 1))
        location = item.get("location", "")
        teacher = item.get("teacher", "")
        weeks = item.get("weeks", "1-20")

        if periods and 0 < sp <= len(periods) and 0 < ep <= len(periods):
            start = periods[sp - 1].start
            end = periods[ep - 1].end
        else:
            base_h = 8 + (sp - 1) // 2
            start = f"{base_h:02d}:{'00' if sp % 2 == 1 else '50'}"
            end_h = 8 + ep // 2
            end = f"{end_h:02d}:{'45' if ep % 2 == 0 else '40'}"

        courses.append(Course(
            id=str(_uuid.uuid4()),
            name=name, day=day, start=start, end=end,
            location=location, teacher=teacher, weeks=weeks,
        ))
    return courses
