from dataclasses import dataclass, asdict


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