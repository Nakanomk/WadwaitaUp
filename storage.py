import json
from pathlib import Path
from typing import List
from models import Course


class CourseStorage:
    def __init__(self, path: str = "data/courses.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_raw([])

    def _write_raw(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> List[Course]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return [Course.from_dict(item) for item in raw]
        except Exception:
            return []

    def save(self, courses: List[Course]):
        self._write_raw([c.to_dict() for c in courses])


class SettingsStorage:
    def __init__(self, path: str = "data/settings.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save({
                "term_start_date": "",   # YYYY-MM-DD
                "total_weeks": 20
            })

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"term_start_date": "", "total_weeks": 20}

    def save(self, settings: dict):
        self.path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )