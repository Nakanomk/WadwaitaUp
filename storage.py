import json
import uuid
from pathlib import Path
from typing import List

from models import Course, Schedule, DEFAULT_CLASS_PERIODS


class ScheduleStorage:
    """Stores multiple schedules in data/schedules.json."""

    def __init__(self, path: str = "data/schedules.json",
                 old_courses_path: str = "data/courses.json",
                 old_settings_path: str = "data/settings.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._init_from_legacy(old_courses_path, old_settings_path)

    def _init_from_legacy(self, old_courses_path: str, old_settings_path: str):
        """Create initial schedules.json, migrating old courses.json if present."""
        courses: List[Course] = []
        term_start_date = ""
        total_weeks = 20

        old_path = Path(old_courses_path)
        if old_path.exists():
            try:
                raw = json.loads(old_path.read_text(encoding="utf-8"))
                courses = [Course.from_dict(item) for item in raw]
            except Exception:
                courses = []

        old_settings = Path(old_settings_path)
        if old_settings.exists():
            try:
                s = json.loads(old_settings.read_text(encoding="utf-8"))
                term_start_date = s.get("term_start_date", "")
                total_weeks = int(s.get("total_weeks", 20))
            except Exception:
                pass

        default = Schedule(
            id=str(uuid.uuid4()),
            name="默认课表",
            term_start_date=term_start_date,
            total_weeks=total_weeks,
            courses=courses,
        )
        self._write_raw([default.to_dict()])

    def _write_raw(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> List[Schedule]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return [Schedule.from_dict(item) for item in raw]
        except Exception:
            default = Schedule(id=str(uuid.uuid4()), name="默认课表")
            return [default]

    def save(self, schedules: List[Schedule]):
        self._write_raw([s.to_dict() for s in schedules])


class SettingsStorage:
    DEFAULT_SETTINGS = {
        "current_schedule_id": None,
        "color_scheme": "auto",   # "auto" | "light" | "dark"
        "class_periods": DEFAULT_CLASS_PERIODS,
        "onboarding_done": False,
    }

    def __init__(self, path: str = "data/settings.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(dict(self.DEFAULT_SETTINGS))
        else:
            self._migrate()

    def _migrate(self):
        """Remove legacy keys and add any missing default keys."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            changed = False
            # Remove legacy term keys (now stored per-schedule)
            for legacy_key in ("term_start_date", "total_weeks"):
                if legacy_key in raw:
                    del raw[legacy_key]
                    changed = True
            # Add missing default keys
            for k, v in self.DEFAULT_SETTINGS.items():
                if k not in raw:
                    raw[k] = v
                    changed = True
            if changed:
                self.save(raw)
        except Exception:
            self.save(dict(self.DEFAULT_SETTINGS))

    def load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for k, v in self.DEFAULT_SETTINGS.items():
                if k not in raw:
                    raw[k] = v
            return raw
        except Exception:
            return dict(self.DEFAULT_SETTINGS)

    def save(self, settings: dict):
        self.path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )