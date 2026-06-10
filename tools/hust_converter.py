#!/usr/bin/env python3
"""
HUST HUB 课表转换器 — Python CLI 版本
======================================

将 HUST HUB 系统「总课表」的 API 响应数据转换为 WadwaitaUp JSON 格式。

使用方法 / Usage:
  1. 登录 https://hubs.hust.edu.cn/basicInformation/scheduleInformation/index
  2. 切换到「总课表」标签，选择学期，等待课表加载
  3. 按 F12 → Network 面板 → 找到 getStudentScheduleByXqh 请求
  4. 右键 → Copy → Copy response → 保存为 hust_raw.json
  5. 运行: python tools/hust_converter.py hust_raw.json -o courses.json

  或者直接从剪贴板粘贴 JSON 到标准输入:
    python tools/hust_converter.py - < courses.json

选项 / Options:
  --summer      使用夏令时节次时间 (默认)
  --winter      使用冬令时节次时间
  --periods     输出节次编号而非具体时间 (start_period/end_period)
  -o FILE       输出到文件 (默认打印到标准输出)
"""

import json
import sys
from pathlib import Path

# ── 星期映射 ────────────────────────────────────────────────────
DAY_KEYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

# ── 节次时间映射 ────────────────────────────────────────────────
HUST_SUMMER_TIMES = {
    1:  ("08:00", "08:45"),  2:  ("08:55", "09:40"),
    3:  ("10:10", "10:55"),  4:  ("11:05", "11:50"),
    5:  ("14:30", "15:15"),  6:  ("15:20", "16:05"),
    7:  ("16:25", "17:10"),  8:  ("17:15", "18:00"),
    9:  ("19:00", "19:45"),  10: ("19:50", "20:35"),
    11: ("20:45", "21:30"),  12: ("21:35", "22:20"),
}

HUST_WINTER_TIMES = {
    1:  ("08:00", "08:45"),  2:  ("08:55", "09:40"),
    3:  ("10:10", "10:55"),  4:  ("11:05", "11:50"),
    5:  ("14:00", "14:45"),  6:  ("14:50", "15:35"),
    7:  ("15:55", "16:40"),  8:  ("16:45", "17:30"),
    9:  ("18:30", "19:15"),  10: ("19:20", "20:05"),
    11: ("20:15", "21:00"),  12: ("21:05", "21:50"),
}


def parse_period(jc: str) -> tuple[int, int]:
    """Parse a period string like "1-2" or "3" into (start, end)."""
    if not jc:
        return (0, 0)
    parts = str(jc).strip().split("-")
    start = int(parts[0])
    end = int(parts[-1])
    return (start, end)


def compact_weeks(weeks: list[int]) -> str:
    """Compact a sorted list of week numbers into a readable string.

    >>> compact_weeks([1, 2, 3, 5, 6, 7])
    '1-3,5-7'
    """
    if not weeks:
        return ""
    weeks = sorted(set(weeks))
    ranges: list[str] = []
    start = end = weeks[0]

    for w in weeks[1:]:
        if w == end + 1:
            end = w
        else:
            ranges.append(str(start) if start == end else f"{start}-{end}")
            start = end = w
    ranges.append(str(start) if start == end else f"{start}-{end}")
    return ",".join(ranges)


def convert(week_table_data: list, *,
            use_winter: bool = False,
            use_periods: bool = False,
            default_weeks: str = "1-20") -> list[dict]:
    """Convert HUST HUB raw API response to WadwaitaUp JSON format.

    Args:
        week_table_data: Raw response from getStudentScheduleByXqh API.
        use_winter: Use winter period times instead of summer.
        use_periods: Output start_period/end_period instead of times.
        default_weeks: Fallback weeks string.

    Returns:
        List of WadwaitaUp-compatible course dicts.
    """
    if not isinstance(week_table_data, list) or not week_table_data:
        raise ValueError("week_table_data 必须是非空数组")

    times = HUST_WINTER_TIMES if use_winter else HUST_SUMMER_TIMES
    course_map: dict = {}  # key: (name, day, period_range) → course dict

    for week_row in week_table_data:
        week_num = int(week_row.get("ZC", 0))
        if week_num <= 0:
            continue

        for day_idx, day_key in enumerate(DAY_KEYS):
            day_num = day_idx + 1  # 1=Mon … 7=Sun
            courses = week_row.get(day_key)

            if not isinstance(courses, list) or not courses:
                continue

            for item in courses:
                name = (item.get("KCMC") or "").strip()
                if not name:
                    continue

                start_period, end_period = parse_period(item.get("JC", ""))
                if start_period <= 0:
                    continue

                period_key = f"{start_period}-{end_period}"
                location = (item.get("JSMC") or "").strip()

                key = (name, day_num, period_key)

                if key not in course_map:
                    entry: dict = {
                        "name": name,
                        "day": day_num,
                        "location": location,
                        "teacher": "",
                        "weeks_set": set(),
                    }

                    if not use_periods:
                        start_time = times.get(start_period, (None, None))[0]
                        end_time = times.get(end_period, (None, None))[1]
                        if start_time and end_time:
                            entry["start"] = start_time
                            entry["end"] = end_time
                        else:
                            entry["start_period"] = start_period
                            entry["end_period"] = end_period
                    else:
                        entry["start_period"] = start_period
                        entry["end_period"] = end_period

                    course_map[key] = entry

                course_map[key]["weeks_set"].add(week_num)

    # ── Build final output ───────────────────────────────────
    result: list[dict] = []
    for (_name, _day, _pk), course in course_map.items():
        weeks_set = course.pop("weeks_set")
        weeks_str = compact_weeks(sorted(weeks_set)) or default_weeks

        entry = {k: v for k, v in course.items()}
        entry["weeks"] = weeks_str
        result.append(entry)

    # Sort by day then start time/period
    def sort_key(c):
        sp = c.get("start_period", 0)
        st = c.get("start", "00:00")
        return (c["day"], sp if sp else st)

    result.sort(key=sort_key)
    return result


def main():
    args = sys.argv[1:]

    use_winter = "--winter" in args
    use_periods = "--periods" in args
    output_file = None

    # Parse -o flag
    for i, arg in enumerate(args):
        if arg == "-o" and i + 1 < len(args):
            output_file = args[i + 1]
            break

    # Find input source
    input_source = None
    for arg in args:
        if arg in ("--summer", "--winter", "--periods"):
            continue
        if arg == "-o":
            continue
        if arg in ("-h", "--help"):
            print(__doc__)
            return
        input_source = arg
        break

    if input_source is None:
        print(__doc__)
        sys.exit(1)

    # Read input
    if input_source == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(input_source).read_text(encoding="utf-8")

    data = json.loads(raw)
    courses = convert(data, use_winter=use_winter, use_periods=use_periods)

    output = json.dumps(courses, ensure_ascii=False, indent=2)

    if output_file:
        Path(output_file).write_text(output, encoding="utf-8")
        print(f"✅ 已导出 {len(courses)} 门课程到 {output_file}")
    else:
        print(output)

    # Summary
    print(f"\n📅 共 {len(courses)} 门课程", file=sys.stderr)
    for c in courses:
        time_info = f"{c.get('start', '')}-{c.get('end', '')}" if "start" in c else f"第{c['start_period']}-{c['end_period']}节"
        print(f"  {c['name']:　<10s}  周{c['day']} {time_info}  第{c['weeks']}周  {c.get('location', '')}", file=sys.stderr)


if __name__ == "__main__":
    main()
