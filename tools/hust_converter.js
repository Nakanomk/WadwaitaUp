/**
 * HUST HUB 课表转换器 — 浏览器控制台脚本
 * HUST HUB Schedule Converter — Browser Console Script
 *
 * 使用方法 / Usage:
 *   1. 登录 https://hubs.hust.edu.cn/basicInformation/scheduleInformation/index
 *   2. 点击「总课表」标签
 *   3. 选择学期，等待课表加载完成
 *   4. 按 F12 打开开发者工具，切换到 Console 面板
 *   5. 粘贴本脚本并回车运行
 *   6. 脚本会自动下载一个 JSON 文件，可直接导入 WadwaitaUp
 *
 * 或者直接在 Console 中调用:
 *   hustToWadwaitaUp.download()
 *   hustToWadwaitaUp.copy()    // 复制到剪贴板
 *   hustToWadwaitaUp.print()   // 打印到控制台
 */

(function () {
  "use strict";

  // ── 星期映射 / Day mapping ───────────────────────────────────
  const DAY_KEYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"];
  const DAY_CN   = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

  // ── 节次映射到具体时间 / Period → time mapping ────────────────
  // 使用者可以根据自己的实际节次时间修改这里
  // You can adjust these times to match your actual schedule
  const HUST_SUMMER_TIMES = {
    1:  { start: "08:00", end: "08:45" },
    2:  { start: "08:55", end: "09:40" },
    3:  { start: "10:10", end: "10:55" },
    4:  { start: "11:05", end: "11:50" },
    5:  { start: "14:30", end: "15:15" },
    6:  { start: "15:20", end: "16:05" },
    7:  { start: "16:25", end: "17:10" },
    8:  { start: "17:15", end: "18:00" },
    9:  { start: "19:00", end: "19:45" },
    10: { start: "19:50", end: "20:35" },
    11: { start: "20:45", end: "21:30" },
    12: { start: "21:35", end: "22:20" },
  };

  const HUST_WINTER_TIMES = {
    1:  { start: "08:00", end: "08:45" },
    2:  { start: "08:55", end: "09:40" },
    3:  { start: "10:10", end: "10:55" },
    4:  { start: "11:05", end: "11:50" },
    5:  { start: "14:00", end: "14:45" },
    6:  { start: "14:50", end: "15:35" },
    7:  { start: "15:55", end: "16:40" },
    8:  { start: "16:45", end: "17:30" },
    9:  { start: "18:30", end: "19:15" },
    10: { start: "19:20", end: "20:05" },
    11: { start: "20:15", end: "21:00" },
    12: { start: "21:05", end: "21:50" },
  };

  // ── 默认使用夏令时，你可以改成 HUST_WINTER_TIMES ──────────────
  const PERIOD_TIMES = HUST_SUMMER_TIMES;

  // ═══════════════════════════════════════════════════════════════
  //  核心转换逻辑 / Core conversion logic
  // ═══════════════════════════════════════════════════════════════

  /**
   * Parse a period string like "1-2" or "3" into [startPeriod, endPeriod].
   */
  function parsePeriod(jc) {
    if (!jc) return [null, null];
    const parts = jc.toString().trim().split("-");
    const start = parseInt(parts[0], 10);
    const end = parseInt(parts[parts.length - 1], 10);
    return [start, end];
  }

  /**
   * Convert period numbers to HH:MM time strings using PERIOD_TIMES.
   * Returns null if the period number is not in the time map.
   */
  function periodToTime(periodNum, which) {
    const t = PERIOD_TIMES[periodNum];
    if (!t) return null;
    return which === "start" ? t.start : t.end;
  }

  /**
   * Main conversion: raw API data → WadwaitaUp JSON format.
   *
   * @param {Array}  weekTableData  - The raw weekTableData from the Vue app.
   * @param {Object} [opts]         - Optional config.
   * @param {string} [opts.defaultWeeks] - Weeks string for courses without week data (default "1-20").
   * @param {boolean} [opts.useStartEnd] - Use "start"/"end" times instead of periods (default true).
   * @returns {Array} Array of WadwaitaUp-compatible course objects.
   */
  function convert(weekTableData, opts) {
    opts = opts || {};
    const defaultWeeks = opts.defaultWeeks || "1-20";
    const useStartEnd = opts.useStartEnd !== false;

    if (!Array.isArray(weekTableData) || weekTableData.length === 0) {
      console.error("❌ weekTableData 为空或不是数组。请确保已切换到「总课表」并加载了数据。");
      return [];
    }

    // ── Step 1: Collect all unique courses ─────────────────────
    // Key: "name|day|periodRange"
    const courseMap = new Map();

    for (const weekRow of weekTableData) {
      const weekNum = parseInt(weekRow.ZC, 10);
      if (isNaN(weekNum)) continue;

      for (let dayIdx = 0; dayIdx < DAY_KEYS.length; dayIdx++) {
        const dayKey = DAY_KEYS[dayIdx];
        const dayNum = dayIdx + 1; // 1=Mon … 7=Sun
        const courses = weekRow[dayKey];

        if (!Array.isArray(courses) || courses.length === 0) continue;

        for (const item of courses) {
          const name = (item.KCMC || "").trim();
          if (!name) continue;

          const [startPeriod, endPeriod] = parsePeriod(item.JC);
          const periodKey = startPeriod + "-" + endPeriod;
          const location = (item.JSMC || "").trim();

          // Unique key for deduplication
          const key = name + "|" + dayNum + "|" + periodKey;

          if (!courseMap.has(key)) {
            const course = {
              name: name,
              day: dayNum,
              location: location,
              teacher: "",
              weeks: new Set(),
            };

            if (useStartEnd) {
              const s = periodToTime(startPeriod, "start");
              const e = periodToTime(endPeriod, "end");
              if (s && e) {
                course.start = s;
                course.end = e;
              } else {
                // Fall back to period numbers if time not found
                course.start_period = startPeriod;
                course.end_period = endPeriod;
              }
            } else {
              course.start_period = startPeriod;
              course.end_period = endPeriod;
            }

            courseMap.set(key, course);
          }

          courseMap.get(key).weeks.add(weekNum);
        }
      }
    }

    // ── Step 2: Build output with compact weeks strings ────────
    const result = [];

    for (const [, course] of courseMap) {
      const weeksArr = Array.from(course.weeks).sort((a, b) => a - b);
      const weeksStr = compactWeeks(weeksArr) || defaultWeeks;

      const entry = {
        name: course.name,
        day: course.day,
        location: course.location,
        teacher: course.teacher,
        weeks: weeksStr,
      };

      if (course.start) {
        entry.start = course.start;
        entry.end = course.end;
      } else {
        entry.start_period = course.start_period;
        entry.end_period = course.end_period;
      }

      result.push(entry);
    }

    return result;
  }

  /**
   * Compact an array of week numbers into a human-readable string.
   * e.g. [1,2,3,5,6,7] → "1-3,5-7"
   */
  function compactWeeks(arr) {
    if (!arr || arr.length === 0) return "";
    const ranges = [];
    let start = arr[0];
    let end = arr[0];

    for (let i = 1; i < arr.length; i++) {
      if (arr[i] === end + 1) {
        end = arr[i];
      } else {
        ranges.push(start === end ? String(start) : start + "-" + end);
        start = arr[i];
        end = arr[i];
      }
    }
    ranges.push(start === end ? String(start) : start + "-" + end);
    return ranges.join(",");
  }

  // ═══════════════════════════════════════════════════════════════
  //  数据提取 / Data extraction
  // ═══════════════════════════════════════════════════════════════

  /**
   * Try to find the Vue app instance and extract weekTableData.
   */
  function extractData() {
    // Method 1: Try to find the Vue instance on the el-table's root element
    const tableEl = document.querySelector(".el-table");
    if (tableEl && tableEl.__vue__) {
      const vm = tableEl.__vue__;
      if (vm.weekTableData && vm.weekTableData.length > 0) {
        console.log("✅ 从 Vue 组件实例获取到 " + vm.weekTableData.length + " 周数据");
        return vm.weekTableData;
      }
    }

    // Method 2: Walk the DOM tree to find a Vue instance with weekTableData
    const appEl = document.querySelector("#app") || document.querySelector("[data-app]") || document.body;
    function findVueData(el) {
      if (!el) return null;
      // Check __vue__ on the element itself
      if (el.__vue__) {
        const vm = el.__vue__;
        // Walk up the component tree
        let current = vm;
        while (current) {
          if (current.weekTableData && Array.isArray(current.weekTableData) && current.weekTableData.length > 0) {
            return current.weekTableData;
          }
          if (current.$data && current.$data.weekTableData && current.$data.weekTableData.length > 0) {
            return current.$data.weekTableData;
          }
          current = current.$parent;
        }
      }
      // Recursively search children
      for (const child of el.children) {
        const result = findVueData(child);
        if (result) return result;
      }
      return null;
    }

    const data = findVueData(appEl);
    if (data) {
      console.log("✅ 从 Vue 组件树获取到 " + data.length + " 周数据");
      return data;
    }

    // Method 3: Check if the data is stored in a global variable
    if (window.__HUST_SCHEDULE_DATA__) {
      console.log("✅ 从全局变量获取到数据");
      return window.__HUST_SCHEDULE_DATA__;
    }

    console.error(
      "❌ 无法获取课表数据。请确保：\n" +
      "  1. 已登录 HUB 系统\n" +
      "  2. 已切换到「总课表」标签\n" +
      "  3. 课表已经加载显示在页面上\n" +
      "\n💡 如果仍然失败，可以尝试：\n" +
      "  - 在 Network 面板找到 getStudentScheduleByXqh 请求\n" +
      '  - 复制响应 JSON，然后调用 hustToWadwaitaUp.convert(粘贴的数据)'
    );
    return null;
  }

  // ═══════════════════════════════════════════════════════════════
  //  输出方法 / Output methods
  // ═══════════════════════════════════════════════════════════════

  function download(jsonData) {
    const blob = new Blob(
      [JSON.stringify(jsonData, null, 2)],
      { type: "application/json" }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "wadwaitaup_courses.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    console.log("📥 已下载 wadwaitaup_courses.json（" + jsonData.length + " 门课程）");
  }

  function copy(jsonData) {
    const text = JSON.stringify(jsonData, null, 2);
    navigator.clipboard.writeText(text).then(
      function () {
        console.log("📋 已复制 " + jsonData.length + " 门课程到剪贴板！直接粘贴到 WadwaitaUp 导入框即可。");
      },
      function () {
        console.warn("⚠️ 复制失败，请手动复制下面的 JSON：");
        console.log(text);
      }
    );
  }

  function print(jsonData) {
    console.log("📅 共 " + jsonData.length + " 门课程：");
    console.log(JSON.stringify(jsonData, null, 2));
  }

  // ═══════════════════════════════════════════════════════════════
  //  公开 API / Public API
  // ═══════════════════════════════════════════════════════════════

  const api = {
    convert: convert,
    extract: extractData,
    compactWeeks: compactWeeks,

    download: function (opts) {
      const data = extractData();
      if (!data) return;
      const json = convert(data, opts);
      if (json.length === 0) return;
      console.log("✅ 转换完成：" + json.length + " 门课程");
      download(json);
      return json;
    },

    copy: function (opts) {
      const data = extractData();
      if (!data) return;
      const json = convert(data, opts);
      if (json.length === 0) return;
      console.log("✅ 转换完成：" + json.length + " 门课程");
      copy(json);
      return json;
    },

    print: function (opts) {
      const data = extractData();
      if (!data) return;
      const json = convert(data, opts);
      if (json.length === 0) return;
      console.log("✅ 转换完成：" + json.length + " 门课程");
      print(json);
      return json;
    },

    // Direct conversion from raw data (useful if you copy from Network panel)
    fromRaw: function (rawData, opts) {
      const json = convert(rawData, opts);
      if (json.length === 0) return;
      console.log("✅ 转换完成：" + json.length + " 门课程");
      console.log(JSON.stringify(json, null, 2));
      return json;
    },
  };

  // ── 挂载到全局 / Expose globally ──────────────────────────────
  window.hustToWadwaitaUp = api;

  // ── 自动检测并提示 ────────────────────────────────────────────
  const data = extractData();
  if (data) {
    console.log(
      "🎓 HUST HUB 课表转换器已就绪！\n" +
      "  共检测到 " + data.length + " 周数据。\n\n" +
      "  运行以下命令导出：\n" +
      "    hustToWadwaitaUp.download()   — 下载 JSON 文件\n" +
      "    hustToWadwaitaUp.copy()       — 复制到剪贴板\n" +
      "    hustToWadwaitaUp.print()      — 打印到控制台\n"
    );
  } else {
    console.log(
      "🎓 HUST HUB 课表转换器已加载。\n" +
      "  请切换到「总课表」标签并等待课表加载完成，然后运行：\n" +
      "    hustToWadwaitaUp.download()"
    );
  }
})();
