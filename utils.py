from datetime import datetime, date
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple


WEEKDAY_CN: Dict[int, str] = {
    1: "周一", 2: "周二", 3: "周三", 4: "周四",
    5: "周五", 6: "周六", 7: "周日",
}


def today_weekday_1_7() -> int:
    return datetime.now().weekday() + 1


def hhmm_to_minutes(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def is_valid_hhmm(s: str) -> bool:
    try:
        parts = s.split(":")
        if len(parts) != 2:
            return False
        h = int(parts[0])
        m = int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59 and len(parts[0]) in (1, 2) and len(parts[1]) == 2
    except (ValueError, AttributeError):
        return False


def sort_courses(courses: List) -> List:
    return sorted(courses, key=lambda c: (c.day, hhmm_to_minutes(c.start)))


def get_today_courses(courses: List) -> List:
    wd = today_weekday_1_7()
    items = [c for c in courses if c.day == wd]
    return sorted(items, key=lambda c: hhmm_to_minutes(c.start))


def get_next_course(courses: List) -> Tuple[Optional[Any], Optional[int]]:
    """Return (next_course, delta_minutes) or (None, None) if no courses."""
    if not courses:
        return None, None

    now = datetime.now()
    current_day = now.weekday() + 1
    current_min = now.hour * 60 + now.minute

    best = None
    best_delta = None

    for c in courses:
        c_start = hhmm_to_minutes(c.start)
        day_delta = c.day - current_day
        if day_delta < 0:
            day_delta += 7
        delta = day_delta * 24 * 60 + (c_start - current_min)
        if delta < 0:
            delta += 7 * 24 * 60

        if best_delta is None or delta < best_delta:
            best = c
            best_delta = delta

    return best, best_delta


def humanize_delta_minutes(delta: Optional[int]) -> str:
    if delta is None:
        return "暂无"
    if delta == 0:
        return "现在开始"
    if delta < 60:
        return f"{delta} 分钟后"
    h = delta // 60
    m = delta % 60
    if m == 0:
        return f"{h} 小时后"
    return f"{h} 小时 {m} 分钟后"


def calc_current_week(term_start_date_str: str) -> Optional[int]:
    """Return 1-based current week number, or None if date is unset/invalid.

    Returns 0 when today is before the term start date.
    """
    if not term_start_date_str:
        return None
    try:
        start = datetime.strptime(term_start_date_str, "%Y-%m-%d").date()
        today = date.today()
        diff_days = (today - start).days
        if diff_days < 0:
            return 0
        return diff_days // 7 + 1
    except (ValueError, TypeError):
        return None


# ── Week / conflict helpers ──────────────────────────────────────

_MAX_WEEKS = 30   # upper bound for odd/even week expansion


@lru_cache(maxsize=256)
def parse_weeks(weeks_str: str) -> frozenset:
    """Parse a weeks string into an immutable frozenset of week numbers.

    Supported formats:
      "1-16"        → weeks 1..16
      "1,3,5"       → specific weeks
      "1-8,10-16"   → combined ranges
      "单" / "奇"   → odd weeks (1,3,5,…)
      "双" / "偶"   → even weeks (2,4,6,…)
      ""            → no restriction (returns empty frozenset)

    Results are cached via :func:`functools.lru_cache` — the same weeks
    string is often parsed repeatedly across UI refreshes.
    """
    if not weeks_str or not weeks_str.strip():
        return frozenset()

    ws = weeks_str.strip()

    if ws in ("单", "奇"):
        return frozenset(range(1, _MAX_WEEKS + 1, 2))
    if ws in ("双", "偶"):
        return frozenset(range(2, _MAX_WEEKS + 1, 2))

    result: set[int] = set()
    for part in ws.replace("，", ",").replace('，', ',').split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                result.update(range(int(a.strip()), int(b.strip()) + 1))
            except ValueError:
                pass
        else:
            try:
                result.add(int(part))
            except ValueError:
                pass
    return frozenset(result)


def is_course_active_this_week(course, current_week: Optional[int]) -> bool:
    """Return True if *course* runs during *current_week* (1-based int).

    If *current_week* is None or ≤ 0 the function conservatively returns True
    (week is unknown, show all courses).
    """
    if current_week is None or current_week <= 0:
        return True
    weeks = parse_weeks(course.weeks)
    if not weeks:
        return True  # No restriction → always active
    return current_week in weeks


def detect_conflicts(courses: List) -> List[Tuple]:
    """Return a list of (course_a, course_b) pairs with overlapping time on the same day."""
    conflicts: List[Tuple] = []
    by_day: Dict[int, List] = {}
    for c in courses:
        by_day.setdefault(c.day, []).append(c)

    for day_courses in by_day.values():
        n = len(day_courses)
        for i in range(n):
            ca = day_courses[i]
            a_start = hhmm_to_minutes(ca.start)
            a_end   = hhmm_to_minutes(ca.end)
            for j in range(i + 1, n):
                cb = day_courses[j]
                b_start = hhmm_to_minutes(cb.start)
                b_end   = hhmm_to_minutes(cb.end)
                if a_start < b_end and b_start < a_end:
                    conflicts.append((ca, cb))
    return conflicts


def get_active_periods(settings: dict, check_date: Optional[date] = None) -> List:
    """Return the list of ClassPeriod objects for the time scheme active on *check_date*.

    Falls back to settings["class_periods"] if no time scheme matches.
    """
    from models import ClassPeriod, TimeScheme
    if check_date is None:
        check_date = date.today()

    for scheme_dict in settings.get("time_schemes", []):
        scheme = TimeScheme.from_dict(scheme_dict)
        if scheme.periods and scheme.is_active_on(check_date):
            return scheme.periods

    # Fallback: global class_periods
    return [ClassPeriod.from_dict(p) for p in settings.get("class_periods", [])]


def is_course_ended(course, current_week: Optional[int]) -> bool:
    """Return True if the course's week range has completely passed.

    A course is considered ended when *current_week* is strictly greater than
    every week number in the course's week restriction. Returns False when
    *current_week* is unknown (None / ≤ 0) or the course has no restriction.
    """
    if current_week is None or current_week <= 0:
        return False
    weeks = parse_weeks(course.weeks)
    if not weeks:
        return False   # No restriction → never ended
    return current_week > max(weeks)


# ── ICS export helpers ────────────────────────────────────────────

def _ics_escape(text: str) -> str:
    """Escape special characters for an iCalendar property value."""
    return (text
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n"))


def _weeks_are_contiguous(weeks: frozenset) -> bool:
    """Return True if *weeks* form a single contiguous range (e.g. 1..16)."""
    if not weeks:
        return False
    sorted_weeks = sorted(weeks)
    return sorted_weeks == list(range(sorted_weeks[0], sorted_weeks[-1] + 1))


def _weeks_are_alternating(weeks: frozenset) -> Optional[int]:
    """If *weeks* alternate at a constant interval, return the interval.

    Returns 2 for odd/even weeks, or None for non-alternating sets.
    """
    if not weeks or len(weeks) < 2:
        return None
    sorted_weeks = sorted(weeks)
    step = sorted_weeks[1] - sorted_weeks[0]
    if step < 2:
        return None
    for i in range(1, len(sorted_weeks) - 1):
        if sorted_weeks[i + 1] - sorted_weeks[i] != step:
            return None
    return step


def _build_rrule(weeks: frozenset, total_weeks: int, dtstart: datetime) -> Optional[str]:
    """Build an RRULE line for a given set of weeks, or None if not applicable.

    Uses FREQ=WEEKLY for contiguous ranges and INTERVAL for odd/even weeks.
    Falls back to None for complex patterns (the caller should generate
    individual VEVENTs instead).
    """
    if not weeks:
        return f"RRULE:FREQ=WEEKLY;COUNT={total_weeks}"

    sorted_weeks = sorted(weeks)

    if _weeks_are_contiguous(weeks):
        count = len(sorted_weeks)
        return f"RRULE:FREQ=WEEKLY;COUNT={count}"

    interval = _weeks_are_alternating(weeks)
    if interval is not None:
        count = len(sorted_weeks)
        return f"RRULE:FREQ=WEEKLY;INTERVAL={interval};COUNT={count}"

    # Complex pattern — fall back to individual VEVENTs (return None)
    return None


def export_schedule_to_ics(schedule, term_start_date_str: str) -> str:
    """Export *schedule* to iCalendar (.ics) format.

    Uses RRULE for courses with simple week patterns (contiguous ranges,
    odd/even weeks). Falls back to individual VEVENTs for complex patterns.

    Returns an empty string if *term_start_date_str* is not set or is invalid.
    """
    import uuid as _uuid
    from datetime import timedelta

    if not term_start_date_str:
        return ""

    try:
        term_start = datetime.strptime(term_start_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return ""

    # Monday of the week that contains term_start
    term_monday = term_start - timedelta(days=term_start.weekday())

    total_weeks = getattr(schedule, "total_weeks", 20) or 20

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WadwaitaUp//WadwaitaUp Course Planner//ZH",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(schedule.name)}",
    ]

    for course in schedule.courses:
        weeks = parse_weeks(course.weeks)
        if not weeks:
            weeks = frozenset(range(1, total_weeks + 1))

        try:
            start_h, start_m = map(int, course.start.split(":"))
            end_h, end_m = map(int, course.end.split(":"))
        except (ValueError, AttributeError):
            continue

        # Compute DTSTART for the first occurrence
        first_week = min(weeks) if weeks else 1
        week_offset = first_week - 1
        day_offset = course.day - 1  # 0=Mon … 6=Sun
        first_date = term_monday + timedelta(weeks=week_offset, days=day_offset)

        dtstart = datetime(first_date.year, first_date.month, first_date.day,
                           start_h, start_m, 0)

        summary     = _ics_escape(course.name)
        location    = _ics_escape(course.location) if course.location else ""
        description = _ics_escape(f"教师：{course.teacher}") if course.teacher else ""

        dtstart_str = dtstart.strftime("%Y%m%dT%H%M%S")
        dtend_str   = f"{dtstart.strftime('%Y%m%d')}T{end_h:02d}{end_m:02d}00"

        uid = _uuid.uuid4()

        # Try RRULE first (works for contiguous ranges and odd/even weeks)
        rrule = _build_rrule(weeks, total_weeks, dtstart)

        if rrule is not None:
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}@wadwaitaup",
                f"DTSTART:{dtstart_str}",
                f"DTEND:{dtend_str}",
                f"SUMMARY:{summary}",
                rrule,
            ]
            if location:
                lines.append(f"LOCATION:{location}")
            if description:
                lines.append(f"DESCRIPTION:{description}")
            lines.append("END:VEVENT")
        else:
            # Fall back to individual VEVENTs for complex week patterns
            for week_num in sorted(weeks):
                if week_num < 1 or week_num > total_weeks:
                    continue
                week_offset_v = week_num - 1
                event_date = term_monday + timedelta(weeks=week_offset_v, days=day_offset)

                ds = (f"{event_date.year:04d}{event_date.month:02d}"
                      f"{event_date.day:02d}T{start_h:02d}{start_m:02d}00")
                de = (f"{event_date.year:04d}{event_date.month:02d}"
                      f"{event_date.day:02d}T{end_h:02d}{end_m:02d}00")

                lines += [
                    "BEGIN:VEVENT",
                    f"UID:{_uuid.uuid4()}@wadwaitaup",
                    f"DTSTART:{ds}",
                    f"DTEND:{de}",
                    f"SUMMARY:{summary}",
                ]
                if location:
                    lines.append(f"LOCATION:{location}")
                if description:
                    lines.append(f"DESCRIPTION:{description}")
                lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
