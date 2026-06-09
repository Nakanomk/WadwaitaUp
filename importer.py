"""
Course importer utilities.

Supports:
  - iCalendar (.ics) text  – parse_ics(text)
  - JSON array             – parse_json_courses(text)

Both return (list[Course], list[str]) where the second element holds
human-readable warning messages for any items that could not be parsed.

iCalendar parser now supports RRULE (FREQ=WEEKLY) for recurring events,
which is the standard way most calendar systems export weekly courses.
"""

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from models import Course, ClassPeriod
from utils import is_valid_hhmm

# ── weekday name → 1-7 mapping ──────────────────────────────────

_WEEKDAY_MAP: Dict[str, int] = {
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
    "start_period": 3,
    "end_period": 4,
    "location": "西12-201",
    "teacher": "李老师",
    "weeks": "1-16"
  },
  {
    "name": "英语",
    "location": "北1-310",
    "teacher": "王老师",
    "weeks": "1-16",
    "sessions": [
      {"day": 2, "start": "10:10", "end": "11:50"},
      {"day": 4, "start_period": 5, "end_period": 6}
    ]
  }
]"""


# ── iCalendar parser ─────────────────────────────────────────────

def _unfold(text: str) -> str:
    """Remove iCalendar line-folding (continuation lines)."""
    return re.sub(r'\r?\n[ \t]', '', text)


def _parse_ics_dt(value: str) -> Optional[datetime]:
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


def _parse_rrule(rrule_str: str, dtstart: datetime) -> List[Tuple[int, int]]:
    """Parse an RRULE line and return a list of (year, week_number) pairs.

    Supports:
      - FREQ=WEEKLY
      - COUNT=N or UNTIL=YYYYMMDD
      - INTERVAL=N (e.g. INTERVAL=2 for bi-weekly)
      - BYDAY=MO,TU,… (returns the day-of-week info; caller must map to course day)

    Returns an empty list if the rule cannot be parsed.
    """
    result: List[Tuple[int, int]] = []

    # Extract key parameters
    freq_match = re.search(r'FREQ=(\w+)', rrule_str, re.IGNORECASE)
    if not freq_match or freq_match.group(1).upper() != 'WEEKLY':
        return result  # Only FREQ=WEEKLY is supported for courses

    interval_match = re.search(r'INTERVAL=(\d+)', rrule_str, re.IGNORECASE)
    interval = int(interval_match.group(1)) if interval_match else 1

    count_match = re.search(r'COUNT=(\d+)', rrule_str, re.IGNORECASE)
    count = int(count_match.group(1)) if count_match else None

    until_match = re.search(r'UNTIL=(\d{8})', rrule_str, re.IGNORECASE)
    until_dt: Optional[datetime] = None
    if until_match:
        until_dt = _parse_ics_dt(until_match.group(1))

    # Compute the Monday of the week containing DTSTART
    dtstart_date = dtstart.date()
    monday = dtstart_date - timedelta(days=dtstart_date.weekday())

    # Generate occurrences
    week_num = 0
    while True:
        if count is not None and week_num >= count:
            break

        occurrence_date = monday + timedelta(weeks=week_num * interval)

        if until_dt is not None:
            if occurrence_date > until_dt.date():
                break

        # Compute ISO week number for display (approximate: which week of the term)
        result.append((occurrence_date.year, occurrence_date.isocalendar()[1]))

        week_num += 1

    return result


def parse_ics(text: str) -> Tuple[List[Course], List[str]]:
    """Parse iCalendar text and return (courses, warnings).

    Each unique (name, weekday, start-time) combination produces exactly one
    Course object – weekly recurring events are deduplicated automatically.

    Supports RRULE:FREQ=WEEKLY for recurring events. When an RRULE with
    COUNT is present, the weeks field is set to the continuous range
    (e.g. "1-16" for COUNT=16). Individual VEVENTs without RRULE are
    still handled as before.
    """
    text = _unfold(text)
    events = re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', text,
                        re.DOTALL | re.IGNORECASE)

    courses: List[Course] = []
    warnings: List[str] = []
    seen: set[Tuple] = set()

    for event_text in events:
        props: Dict[str, str] = {}
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

        # ── RRULE support ─────────────────────────────────────────
        rrule_raw = props.get('RRULE', '')
        if rrule_raw and 'FREQ=WEEKLY' in rrule_raw.upper():
            count_m = re.search(r'COUNT=(\d+)', rrule_raw, re.IGNORECASE)
            if count_m:
                count = int(count_m.group(1))
                weeks = f"1-{count}"
            # For UNTIL-based RRULEs we keep the default weeks string
            # since we don't know the term start date at import time.

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


# ── helpers for session time/day parsing ────────────────────────

def _parse_session(session: Dict[str, Any], periods: Optional[List[ClassPeriod]]) \
        -> Optional[Tuple[int, str, str]]:
    """Parse day/start/end from a session dict (or a top-level item dict).

    Returns (day, start, end) on success, or None on failure.
    The caller is responsible for appending the appropriate warning via
    _parse_session_warning().
    """
    day_raw = session.get('day', 1)  # default 1 = Monday if key is absent
    if isinstance(day_raw, str):
        day_stripped = day_raw.strip()
        day = _WEEKDAY_MAP.get(day_stripped) or _WEEKDAY_MAP.get(day_stripped.upper())
        if day is None:
            return None
    else:
        try:
            day = int(day_raw)
        except (ValueError, TypeError):
            return None
        if not 1 <= day <= 7:
            return None

    start_period = session.get('start_period')
    if start_period is not None:
        if not periods:
            return None
        try:
            sp_idx = int(start_period) - 1
        except (ValueError, TypeError):
            return None
        if not (0 <= sp_idx < len(periods)):
            return None
        start = periods[sp_idx].start
    else:
        start = str(session.get('start', '08:00')).strip()
        if not is_valid_hhmm(start):
            return None

    end_period = session.get('end_period')
    if end_period is not None:
        if not periods:
            return None
        try:
            ep_idx = int(end_period) - 1
        except (ValueError, TypeError):
            return None
        if not (0 <= ep_idx < len(periods)):
            return None
        end = periods[ep_idx].end
    else:
        end = str(session.get('end', '09:40')).strip()
        if not is_valid_hhmm(end):
            return None

    return day, start, end


def _parse_session_warning(session: Dict[str, Any], periods: Optional[List[ClassPeriod]],
                           label: str) -> str:
    """Return a human-readable warning explaining why a session failed to parse."""
    day_raw = session.get('day', 1)
    if isinstance(day_raw, str):
        day_stripped = day_raw.strip()
        day = _WEEKDAY_MAP.get(day_stripped) or _WEEKDAY_MAP.get(day_stripped.upper())
        if day is None:
            return f"{label} day 值「{day_raw}」无法识别，已跳过"
    else:
        try:
            day = int(day_raw)
        except (ValueError, TypeError):
            return f"{label} day 值无法解析为数字，已跳过"
        if not 1 <= day <= 7:
            return f"{label} day 值 {day} 超出范围 1-7，已跳过"

    start_period = session.get('start_period')
    if start_period is not None:
        if not periods:
            return f"{label} 使用了 start_period，但未提供节次时间表，已跳过"
        try:
            sp_idx = int(start_period) - 1
        except (ValueError, TypeError):
            return f"{label} start_period 值无法解析：{start_period}，已跳过"
        if not (0 <= sp_idx < len(periods)):
            return (
                f"{label} start_period {start_period} 超出范围"
                f"（共 {len(periods)} 节），已跳过"
            )
    else:
        start = str(session.get('start', '08:00')).strip()
        if not is_valid_hhmm(start):
            return f"{label} start 时间格式错误：{start}（应为 HH:MM），已跳过"

    end_period = session.get('end_period')
    if end_period is not None:
        if not periods:
            return f"{label} 使用了 end_period，但未提供节次时间表，已跳过"
        try:
            ep_idx = int(end_period) - 1
        except (ValueError, TypeError):
            return f"{label} end_period 值无法解析：{end_period}，已跳过"
        if not (0 <= ep_idx < len(periods)):
            return (
                f"{label} end_period {end_period} 超出范围"
                f"（共 {len(periods)} 节），已跳过"
            )
    else:
        end = str(session.get('end', '09:40')).strip()
        if not is_valid_hhmm(end):
            return f"{label} end 时间格式错误：{end}（应为 HH:MM），已跳过"

    return f"{label} 解析失败，已跳过"


# ── JSON parser ──────────────────────────────────────────────────

def parse_json_courses(text: str, periods: Optional[List[ClassPeriod]] = None) \
        -> Tuple[List[Course], List[str]]:
    """Parse a JSON array of course dicts and return (courses, warnings).

    Each item must have at minimum "name" and either:
      a) Single-session format (legacy): "day", and either
         - "start"/"end" (HH:MM strings), or
         - "start_period"/"end_period" (1-based period numbers, requires *periods* arg).
      b) Multi-session format: a "sessions" list where each session dict has
         "day" and "start"/"end" or "start_period"/"end_period". The top-level
         "location", "teacher", and "weeks" fields are shared across all sessions.

    "day" may be an integer 1-7 (Mon=1) or a Chinese/English weekday name.
    *periods* is an optional list of ClassPeriod used to resolve period numbers.
    """
    warnings: List[str] = []

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [f"JSON 解析失败：{exc}"]

    if not isinstance(data, list):
        return [], ["JSON 格式错误：根节点应为数组 [...]"]

    courses: List[Course] = []

    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            warnings.append(f"第 {idx} 项不是对象，已跳过")
            continue

        name = str(item.get('name', '')).strip()
        if not name:
            warnings.append(f"第 {idx} 项缺少 name，已跳过")
            continue

        # Shared fields (used by all sessions)
        location = str(item.get('location', '')).strip()
        teacher = str(item.get('teacher', '')).strip()
        weeks = str(item.get('weeks', '1-20')).strip()

        # ── Multi-session format ──────────────────────────────────
        if 'sessions' in item:
            sessions_raw = item['sessions']
            if not isinstance(sessions_raw, list):
                warnings.append(f"第 {idx} 项 sessions 应为数组，已跳过")
                continue
            if not sessions_raw:
                warnings.append(f"第 {idx} 项 sessions 为空，已跳过")
                continue

            for s_idx, session in enumerate(sessions_raw, start=1):
                if not isinstance(session, dict):
                    warnings.append(f"第 {idx} 项第 {s_idx} 个 session 不是对象，已跳过")
                    continue

                label = f"第 {idx} 项第 {s_idx} 个 session"
                parsed = _parse_session(session, periods)
                if parsed is None:
                    warnings.append(_parse_session_warning(session, periods, label))
                    continue
                day, start, end = parsed
                # Per-session overrides for location/teacher/weeks
                courses.append(Course(
                    id=str(uuid.uuid4()),
                    name=name,
                    day=day,
                    start=start,
                    end=end,
                    location=str(session.get('location', location)).strip(),
                    teacher=str(session.get('teacher', teacher)).strip(),
                    weeks=str(session.get('weeks', weeks)).strip(),
                ))
            continue

        # ── Single-session format (legacy) ────────────────────────
        label = f"第 {idx} 项"
        parsed = _parse_session(item, periods)
        if parsed is None:
            warnings.append(_parse_session_warning(item, periods, label))
            continue
        day, start, end = parsed
        courses.append(Course(
            id=str(uuid.uuid4()),
            name=name,
            day=day,
            start=start,
            end=end,
            location=location,
            teacher=teacher,
            weeks=weeks,
        ))

    return courses, warnings
