from dataclasses import dataclass, field, asdict
from datetime import date
from typing import List

# Default class periods – HUST (华中科技大学) summer schedule
DEFAULT_CLASS_PERIODS = [
    {"period": 1,  "start": "08:00", "end": "08:45"},
    {"period": 2,  "start": "08:55", "end": "09:40"},
    {"period": 3,  "start": "10:10", "end": "10:55"},
    {"period": 4,  "start": "11:05", "end": "11:50"},
    {"period": 5,  "start": "14:30", "end": "15:15"},
    {"period": 6,  "start": "15:20", "end": "16:05"},
    {"period": 7,  "start": "16:25", "end": "17:10"},
    {"period": 8,  "start": "17:15", "end": "18:00"},
    {"period": 9,  "start": "19:00", "end": "19:45"},
    {"period": 10, "start": "19:50", "end": "20:35"},
    {"period": 11, "start": "20:45", "end": "21:30"},
    {"period": 12, "start": "21:35", "end": "22:20"},
]

# ── 华中科技大学 (HUST) standard class periods ──────────────────────
# 夏令时 (Summer schedule, roughly March–October)
HUST_SUMMER_PERIODS = [
    {"period": 1,  "start": "08:00", "end": "08:45"},
    {"period": 2,  "start": "08:55", "end": "09:40"},
    {"period": 3,  "start": "10:10", "end": "10:55"},
    {"period": 4,  "start": "11:05", "end": "11:50"},
    {"period": 5,  "start": "14:30", "end": "15:15"},
    {"period": 6,  "start": "15:20", "end": "16:05"},
    {"period": 7,  "start": "16:25", "end": "17:10"},
    {"period": 8,  "start": "17:15", "end": "18:00"},
    {"period": 9,  "start": "19:00", "end": "19:45"},
    {"period": 10, "start": "19:50", "end": "20:35"},
    {"period": 11, "start": "20:45", "end": "21:30"},
    {"period": 12, "start": "21:35", "end": "22:20"},
]

# 冬令时 (Winter schedule, roughly November–February)
HUST_WINTER_PERIODS = [
    {"period": 1,  "start": "08:00", "end": "08:45"},
    {"period": 2,  "start": "08:55", "end": "09:40"},
    {"period": 3,  "start": "10:10", "end": "10:55"},
    {"period": 4,  "start": "11:05", "end": "11:50"},
    {"period": 5,  "start": "14:00", "end": "14:45"},
    {"period": 6,  "start": "14:50", "end": "15:35"},
    {"period": 7,  "start": "15:55", "end": "16:40"},
    {"period": 8,  "start": "16:45", "end": "17:30"},
    {"period": 9,  "start": "18:30", "end": "19:15"},
    {"period": 10, "start": "19:20", "end": "20:05"},
    {"period": 11, "start": "20:15", "end": "21:00"},
    {"period": 12, "start": "21:05", "end": "21:50"},
]


@dataclass
class ClassPeriod:
    period: int
    start: str   # "HH:MM"
    end: str     # "HH:MM"

    def label(self) -> str:
        return f"第 {self.period} 节 {self.start}–{self.end}"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ClassPeriod":
        return ClassPeriod(period=int(d["period"]), start=d["start"], end=d["end"])


@dataclass
class Course:
    id: str
    name: str
    day: int          # 1=Mon ... 7=Sun
    start: str        # "HH:MM"
    end: str          # "HH:MM"
    location: str = ""
    teacher: str = ""
    weeks: str = "1-20"

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d: dict):
        return Course(
            id=d["id"],
            name=d["name"],
            day=int(d["day"]),
            start=d["start"],
            end=d["end"],
            location=d.get("location", ""),
            teacher=d.get("teacher", ""),
            weeks=d.get("weeks", "1-20"),
        )


@dataclass
class TimeScheme:
    """A named set of class periods with an optional date range for auto-switching."""

    name: str
    date_from: str = ""   # "MM-DD", or "" for no start restriction
    date_to: str = ""     # "MM-DD", or "" for no end restriction
    periods: List[ClassPeriod] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "periods": [p.to_dict() for p in self.periods],
        }

    @staticmethod
    def from_dict(d: dict) -> "TimeScheme":
        return TimeScheme(
            name=d.get("name", ""),
            date_from=d.get("date_from", ""),
            date_to=d.get("date_to", ""),
            periods=[ClassPeriod.from_dict(p) for p in d.get("periods", [])],
        )

    def is_active_on(self, check_date: date) -> bool:
        """Return True if this scheme is active on check_date.

        Both *date_from* and *date_to* must be non-empty for date-range checking.
        If either field is empty the scheme is treated as always-active (no
        date restriction), which is the expected behaviour for catch-all or
        fallback schemes.
        """
        if not self.date_from or not self.date_to:
            return True  # No date range → always active
        try:
            df_m, df_d = (int(x) for x in self.date_from.split("-"))
            dt_m, dt_d = (int(x) for x in self.date_to.split("-"))
            md = (check_date.month, check_date.day)
            fm = (df_m, df_d)
            tm = (dt_m, dt_d)
            if fm <= tm:
                return fm <= md <= tm
            else:
                # Wraps year boundary (e.g., Nov-01 to Feb-28)
                return md >= fm or md <= tm
        except Exception:
            return False


@dataclass
class Schedule:
    id: str
    name: str
    term_start_date: str = ""
    total_weeks: int = 20
    courses: List[Course] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "term_start_date": self.term_start_date,
            "total_weeks": self.total_weeks,
            "courses": [c.to_dict() for c in self.courses],
        }

    @staticmethod
    def from_dict(d: dict) -> "Schedule":
        return Schedule(
            id=d["id"],
            name=d["name"],
            term_start_date=d.get("term_start_date", ""),
            total_weeks=d.get("total_weeks", 20),
            courses=[Course.from_dict(c) for c in d.get("courses", [])],
        )