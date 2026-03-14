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


def parse_weeks(weeks_str: str) -> set:
    """
    Parse a week-range string like "1-16", "1,3,5-10", "1-8,10,12-16"
    and return the set of week numbers contained.
    Returns an empty set if the string is empty or cannot be parsed.
    """
    result: set = set()
    if not weeks_str:
        return result
    for part in weeks_str.replace('\uff0c', ',').split(','):
        part = part.strip()
        if '-' in part:
            try:
                a, b = part.split('-', 1)
                result.update(range(int(a.strip()), int(b.strip()) + 1))
            except ValueError:
                pass
        else:
            try:
                result.add(int(part))
            except ValueError:
                pass
    return result