from dataclasses import dataclass, field, asdict
from typing import List

# Default class periods for a typical Chinese university schedule
DEFAULT_CLASS_PERIODS = [
    {"period": 1,  "start": "08:00", "end": "08:45"},
    {"period": 2,  "start": "08:55", "end": "09:40"},
    {"period": 3,  "start": "10:00", "end": "10:45"},
    {"period": 4,  "start": "10:55", "end": "11:40"},
    {"period": 5,  "start": "14:00", "end": "14:45"},
    {"period": 6,  "start": "14:55", "end": "15:40"},
    {"period": 7,  "start": "16:00", "end": "16:45"},
    {"period": 8,  "start": "16:55", "end": "17:40"},
    {"period": 9,  "start": "19:00", "end": "19:45"},
    {"period": 10, "start": "19:55", "end": "20:40"},
    {"period": 11, "start": "20:50", "end": "21:35"},
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