from datetime import datetime, date


WEEKDAY_CN = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}


def today_weekday_1_7():
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
    except Exception:
        return False


def sort_courses(courses):
    return sorted(courses, key=lambda c: (c.day, hhmm_to_minutes(c.start)))


def get_today_courses(courses):
    wd = today_weekday_1_7()
    items = [c for c in courses if c.day == wd]
    return sorted(items, key=lambda c: hhmm_to_minutes(c.start))


def get_next_course(courses):
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


def humanize_delta_minutes(delta: int) -> str:
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


def calc_current_week(term_start_date_str: str):
    """
    term_start_date_str: YYYY-MM-DD
    return: int | None
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
    except Exception:
        return None


# ── Week / conflict helpers ──────────────────────────────────────

_MAX_WEEKS = 30   # upper bound for odd/even week expansion


def parse_weeks(weeks_str: str) -> set:
    """Parse a weeks string into a set of week numbers.

    Supported formats:
      "1-16"        → weeks 1..16
      "1,3,5"       → specific weeks
      "1-8,10-16"   → combined ranges
      "单" / "奇"   → odd weeks (1,3,5,…)
      "双" / "偶"   → even weeks (2,4,6,…)
      ""            → no restriction (returns empty set)
    """
    if not weeks_str or not weeks_str.strip():
        return set()

    ws = weeks_str.strip()

    if ws in ("单", "奇"):
        return set(range(1, _MAX_WEEKS + 1, 2))
    if ws in ("双", "偶"):
        return set(range(2, _MAX_WEEKS + 1, 2))

    result: set = set()
    for part in ws.replace("，", ",").split(","):
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
    return result


def is_course_active_this_week(course, current_week) -> bool:
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


def detect_conflicts(courses: list) -> list:
    """Return a list of (course_a, course_b) pairs with overlapping time on the same day."""
    conflicts = []
    by_day: dict = {}
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


def get_active_periods(settings: dict, check_date=None) -> list:
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
