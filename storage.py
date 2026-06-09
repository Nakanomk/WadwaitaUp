"""Persistent storage for schedules and settings.

All file writes use atomic rename (write to a temporary file first,
then rename) to prevent data loss if the process crashes mid-write.
"""

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List

from models import Course, Schedule, DEFAULT_CLASS_PERIODS


def _atomic_write(path: Path, data: str) -> None:
    """Atomically write *data* to *path* via a temporary file + rename.

    This guarantees that *path* always contains either the old complete
    content or the new complete content — never a half-written file.
    """
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".tmp",
        delete=False,
    )
    try:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, path)
    except Exception:
        # Clean up the temp file on failure, then re-raise
        try:
            tmp.close()
        except Exception:
            pass
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
        raise


class ScheduleStorage:
    """Stores multiple schedules in data/schedules.json."""

    def __init__(self, path: str = "data/schedules.json",
                 old_courses_path: str = "data/courses.json",
                 old_settings_path: str = "data/settings.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._init_from_legacy(old_courses_path, old_settings_path)

    def _init_from_legacy(self, old_courses_path: str, old_settings_path: str) -> None:
        """Create initial schedules.json, migrating old courses.json if present."""
        courses: List[Course] = []
        term_start_date = ""
        total_weeks = 20

        old_path = Path(old_courses_path)
        if old_path.exists():
            try:
                raw = json.loads(old_path.read_text(encoding="utf-8"))
                courses = [Course.from_dict(item) for item in raw]
            except (json.JSONDecodeError, KeyError, TypeError):
                courses = []

        old_settings = Path(old_settings_path)
        if old_settings.exists():
            try:
                s = json.loads(old_settings.read_text(encoding="utf-8"))
                term_start_date = s.get("term_start_date", "")
                total_weeks = int(s.get("total_weeks", 20))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        default = Schedule(
            id=str(uuid.uuid4()),
            name="默认课表",
            term_start_date=term_start_date,
            total_weeks=total_weeks,
            courses=courses,
        )
        self._write_raw([default.to_dict()])

    def _write_raw(self, data: List[Dict[str, Any]]) -> None:
        _atomic_write(
            self.path,
            json.dumps(data, ensure_ascii=False, indent=2),
        )

    def load(self) -> List[Schedule]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return [Schedule.from_dict(item) for item in raw]
        except (json.JSONDecodeError, KeyError, TypeError, FileNotFoundError):
            default = Schedule(id=str(uuid.uuid4()), name="默认课表")
            return [default]

    def save(self, schedules: List[Schedule]) -> None:
        self._write_raw([s.to_dict() for s in schedules])


class SettingsStorage:
    DEFAULT_SETTINGS: Dict[str, Any] = {
        "current_schedule_id": None,
        "color_scheme": "auto",   # "auto" | "light" | "dark"
        "class_periods": DEFAULT_CLASS_PERIODS,
        "time_schemes": [],       # list of TimeScheme dicts for auto period switching
        "onboarding_done": False,
    }

    def __init__(self, path: str = "data/settings.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(dict(self.DEFAULT_SETTINGS))
        else:
            self._migrate()

    def _migrate(self) -> None:
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
        except (json.JSONDecodeError, TypeError, FileNotFoundError):
            self.save(dict(self.DEFAULT_SETTINGS))

    def load(self) -> Dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for k, v in self.DEFAULT_SETTINGS.items():
                if k not in raw:
                    raw[k] = v
            return raw
        except (json.JSONDecodeError, TypeError, FileNotFoundError):
            return dict(self.DEFAULT_SETTINGS)

    def save(self, settings: Dict[str, Any]) -> None:
        _atomic_write(
            self.path,
            json.dumps(settings, ensure_ascii=False, indent=2),
        )
