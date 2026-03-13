"""
Course importer utilities.

Supports:
  - iCalendar (.ics) text  – parse_ics(text)
  - JSON array             – parse_json_courses(text)

Both return (list[Course], list[str]) where the second element holds
human-readable warning messages for any items that could not be parsed.
"""

import json
import re
import uuid
from datetime import datetime

from models import Course
from utils import is_valid_hhmm

# ── weekday name → 1-7 mapping ──────────────────────────────────

_WEEKDAY_MAP: dict[str, int] = {
    # Chinese
    "周一": 1, "星期一": 1, "一": 1,
    "周二": 2, "星期二": 2, "二": 2,
    "周三": 3, "星期三": 3, "三": 3,
    "周四": 4, "星期四": 4, "四": 4,
    "周五": 5, "星期五": 5, "五": 5,
    "周六": 6, "星期六": 6, "六": 6,
    "周日": 7, "周天": 7, "星期日": 7, "星期天": 7, "七": 7,
    # English abbreviations used in RRULE BYDAY
    "MO": 1, "TU": 2, "WE": 3, "TH": 4, "FR": 5, "SA": 6, "SU": 7,
}

# JSON format template shown to users
JSON_TEMPLATE = """\
[
  {
    "name": "高等数学",
    "day": 1,
    "start": "08:00",
    "end": "09:40",
    "location": "东1-101",
    "teacher": "张老师",
    "weeks": "1-16"
  },
  {
    "name": "大学物理",
    "day": 3,
    "start": "10:00",
    "end": "11:40",
    "location": "西12-201",
    "teacher": "李老师",
    "weeks": "1-16"
  }
]"""


# ── iCalendar parser ─────────────────────────────────────────────

def _unfold(text: str) -> str:
    """Remove iCalendar line-folding (continuation lines)."""
    return re.sub(r'\r?\n[ \t]', '', text)


def _parse_ics_dt(value: str) -> datetime | None:
    """Parse a DTSTART/DTEND value like 20240901T080000[Z] to datetime."""
    clean = value.replace('Z', '').replace('z', '')
    for fmt, length in [
        ('%Y%m%dT%H%M%S', 15),
        ('%Y%m%dT%H%M', 13),
        ('%Y%m%d', 8),
    ]:
        try:
            return datetime.strptime(clean[:length], fmt)
        except ValueError:
            pass
    return None


def parse_ics(text: str) -> tuple[list[Course], list[str]]:
    """
    Parse iCalendar text and return (courses, warnings).

    Each unique (name, weekday, start-time) combination produces exactly one
    Course object – weekly recurring events are deduplicated automatically.
    """
    text = _unfold(text)
    events = re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', text,
                        re.DOTALL | re.IGNORECASE)

    courses: list[Course] = []
    warnings: list[str] = []
    seen: set[tuple] = set()

    for event_text in events:
        props: dict[str, str] = {}
        for line in event_text.splitlines():
            line = line.strip()
            if not line or ':' not in line:
                continue
            key_part, _, value = line.partition(':')
            key_base = key_part.split(';')[0].upper().strip()
            props[key_base] = value.strip()

        summary = props.get('SUMMARY', '').strip()
        if not summary:
            continue

        dtstart_raw = props.get('DTSTART', '')
        if not dtstart_raw:
            warnings.append(f"课程「{summary}」缺少 DTSTART，已跳过")
            continue

        dt_start = _parse_ics_dt(dtstart_raw)
        if dt_start is None:
            warnings.append(f"课程「{summary}」时间无法解析：{dtstart_raw}，已跳过")
            continue

        day = dt_start.weekday() + 1   # 1 = Mon, 7 = Sun
        start = dt_start.strftime('%H:%M')

        dtend_raw = props.get('DTEND', '')
        if dtend_raw:
            dt_end = _parse_ics_dt(dtend_raw)
            end = dt_end.strftime('%H:%M') if dt_end else start
        else:
            end = start

        location = props.get('LOCATION', '').strip()
        description = props.get('DESCRIPTION', '').strip()
        description = description.replace('\\n', '\n').replace('\\,', ',')

        teacher = ''
        weeks = '1-20'
        if description:
            m = re.search(
                r'(?:老师|教师|Teacher|讲师)[：:]\s*([^\n;，,]+)',
                description, re.IGNORECASE,
            )
            if m:
                teacher = m.group(1).strip()
            m = re.search(
                r'(?:周次|Weeks?)[：:]\s*([^\n;，,]+)',
                description, re.IGNORECASE,
            )
            if m:
                weeks = m.group(1).strip()

        key = (summary, day, start)
        if key in seen:
            continue
        seen.add(key)

        courses.append(Course(
            id=str(uuid.uuid4()),
            name=summary,
            day=day,
            start=start,
            end=end,
            location=location,
            teacher=teacher,
            weeks=weeks,
        ))

    return courses, warnings


# ── JSON parser ──────────────────────────────────────────────────

def parse_json_courses(text: str) -> tuple[list[Course], list[str]]:
    """
    Parse a JSON array of course dicts and return (courses, warnings).

    Each item must have at minimum "name", "day", "start", "end".
    "day" may be an integer 1-7 (Mon=1) or a Chinese/English weekday name.
    """
    warnings: list[str] = []

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [f"JSON 解析失败：{exc}"]

    if not isinstance(data, list):
        return [], ["JSON 格式错误：根节点应为数组 [...]"]

    courses: list[Course] = []

    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            warnings.append(f"第 {idx} 项不是对象，已跳过")
            continue

        name = str(item.get('name', '')).strip()
        if not name:
            warnings.append(f"第 {idx} 项缺少 name，已跳过")
            continue

        # Parse day (int or string)
        day_raw = item.get('day', 1)
        if isinstance(day_raw, str):
            day = _WEEKDAY_MAP.get(day_raw.strip()) or _WEEKDAY_MAP.get(day_raw.strip().upper())
            if day is None:
                warnings.append(f"第 {idx} 项 day 值「{day_raw}」无法识别，已跳过")
                continue
        else:
            day = int(day_raw)
            if not 1 <= day <= 7:
                warnings.append(f"第 {idx} 项 day 值 {day} 超出范围 1-7，已跳过")
                continue

        start = str(item.get('start', '08:00')).strip()
        end = str(item.get('end', '09:40')).strip()

        if not is_valid_hhmm(start):
            warnings.append(f"第 {idx} 项 start 时间格式错误：{start}（应为 HH:MM），已跳过")
            continue
        if not is_valid_hhmm(end):
            warnings.append(f"第 {idx} 项 end 时间格式错误：{end}（应为 HH:MM），已跳过")
            continue

        courses.append(Course(
            id=str(uuid.uuid4()),
            name=name,
            day=day,
            start=start,
            end=end,
            location=str(item.get('location', '')).strip(),
            teacher=str(item.get('teacher', '')).strip(),
            weeks=str(item.get('weeks', '1-20')).strip(),
        ))

    return courses, warnings
