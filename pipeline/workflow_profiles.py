"""Workflow automation profiles for reusable enhancement recipes and scheduled local jobs.

Phase 7, Task 3
A WorkflowProfile stores a named set of EnhancementConfig parameters
(serialised as a plain dict), optional cron-style schedule metadata, and
launch-mode hints (cli / webui / desktop).  Profiles are persisted as JSON
files inside a configurable recipes directory and can be enumerated, loaded,
and queued for execution.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import EnhancementConfig
from app.jobs import JobQueue

# ---------------------------------------------------------------------------
# Schedule specification
# ---------------------------------------------------------------------------

# Simple cron-like string validator: 5 whitespace-separated fields.
_CRON_RE = re.compile(
    r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$"
)

VALID_LAUNCH_MODES = {"cli", "webui", "desktop"}


def validate_cron(expression: str) -> bool:
    """Return True if *expression* matches the 5-field cron pattern."""
    return bool(_CRON_RE.match(expression.strip()))


@dataclass
class ScheduleSpec:
    """Optional schedule metadata attached to a workflow profile."""

    # 5-field cron expression, e.g. "0 2 * * *" (every day at 02:00)
    cron: str
    enabled: bool = True
    # Human-readable label for UI display
    label: str = ""

    def __post_init__(self) -> None:
        if not validate_cron(self.cron):
            raise ValueError(
                f"Invalid cron expression: '{self.cron}'. "
                "Expected 5 whitespace-separated fields."
            )

    def to_dict(self) -> Dict[str, Any]:
        return {"cron": self.cron, "enabled": self.enabled, "label": self.label}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleSpec":
        return cls(
            cron=str(data["cron"]),
            enabled=bool(data.get("enabled", True)),
            label=str(data.get("label", "")),
        )


# ---------------------------------------------------------------------------
# WorkflowProfile
# ---------------------------------------------------------------------------


@dataclass
class WorkflowProfile:
    """A named, serialisable enhancement recipe with optional schedule."""

    name: str
    # Flat dict of EnhancementConfig-compatible parameters.
    params: Dict[str, Any] = field(default_factory=dict)
    # Allowed launch modes for this profile.
    launch_modes: List[str] = field(default_factory=lambda: ["cli"])
    # Optional schedule — None means manual launch only.
    schedule: Optional[ScheduleSpec] = None
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("WorkflowProfile name must not be empty.")
        unknown = set(self.launch_modes) - VALID_LAUNCH_MODES
        if unknown:
            raise ValueError(
                f"Unknown launch modes: {sorted(unknown)}. "
                f"Valid modes: {sorted(VALID_LAUNCH_MODES)}."
            )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "params": self.params,
            "launch_modes": self.launch_modes,
            "description": self.description,
            "tags": self.tags,
        }
        if self.schedule is not None:
            d["schedule"] = self.schedule.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowProfile":
        schedule = None
        if "schedule" in data:
            schedule = ScheduleSpec.from_dict(data["schedule"])
        return cls(
            name=str(data["name"]),
            params=dict(data.get("params", {})),
            launch_modes=list(data.get("launch_modes", ["cli"])),
            schedule=schedule,
            description=str(data.get("description", "")),
            tags=list(data.get("tags", [])),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "WorkflowProfile":
        return cls.from_dict(json.loads(text))

    # ------------------------------------------------------------------
    # Schedule helpers
    # ------------------------------------------------------------------

    @property
    def is_scheduled(self) -> bool:
        return self.schedule is not None and self.schedule.enabled

    def can_launch_from(self, mode: str) -> bool:
        return mode in self.launch_modes


# ---------------------------------------------------------------------------
# RecipeStore — persists profiles as JSON files in a directory
# ---------------------------------------------------------------------------


class RecipeStore:
    """Loads, saves, and lists WorkflowProfiles stored as JSON files."""

    SUFFIX = ".recipe.json"

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def _path_for(self, name: str) -> Path:
        # Sanitise name to a safe filename component.
        safe = re.sub(r"[^\w\-]", "_", name)
        return self.directory / f"{safe}{self.SUFFIX}"

    def save(self, profile: WorkflowProfile) -> Path:
        """Persist *profile* to disk. Returns the file path written."""
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path_for(profile.name)
        path.write_text(profile.to_json(), encoding="utf-8")
        return path

    def load(self, name: str) -> WorkflowProfile:
        """Load a profile by name from the store directory."""
        path = self._path_for(name)
        if not path.exists():
            raise FileNotFoundError(
                f"No recipe named '{name}' found in {self.directory}."
            )
        return WorkflowProfile.from_json(path.read_text(encoding="utf-8"))

    def delete(self, name: str) -> None:
        path = self._path_for(name)
        path.unlink(missing_ok=True)

    def list_all(self) -> List[WorkflowProfile]:
        """Return all profiles found in the store directory."""
        if not self.directory.exists():
            return []
        profiles: List[WorkflowProfile] = []
        for f in sorted(self.directory.glob(f"*{self.SUFFIX}")):
            try:
                profiles.append(WorkflowProfile.from_json(f.read_text(encoding="utf-8")))
            except Exception:
                pass  # skip corrupted files silently
        return profiles

    def list_scheduled(self) -> List[WorkflowProfile]:
        return [p for p in self.list_all() if p.is_scheduled]

    def __contains__(self, name: str) -> bool:
        return self._path_for(name).exists()


# ---------------------------------------------------------------------------
# LocalJobQueue — in-memory queue for locally scheduled profile execution
# ---------------------------------------------------------------------------


@dataclass
class QueuedJob:
    profile_name: str
    launch_mode: str
    status: str = "queued"  # queued | running | done | failed
    result: Optional[Any] = None


class LocalJobQueue:
    """Simple in-memory queue for WorkflowProfile execution requests."""

    def __init__(self) -> None:
        self._jobs: List[QueuedJob] = []

    def enqueue(self, profile_name: str, launch_mode: str = "cli") -> QueuedJob:
        job = QueuedJob(profile_name=profile_name, launch_mode=launch_mode)
        self._jobs.append(job)
        return job

    def pending(self) -> List[QueuedJob]:
        return [j for j in self._jobs if j.status == "queued"]

    def all_jobs(self) -> List[QueuedJob]:
        return list(self._jobs)

    def mark_running(self, job: QueuedJob) -> None:
        job.status = "running"

    def mark_done(self, job: QueuedJob, result: Any = None) -> None:
        job.status = "done"
        job.result = result

    def mark_failed(self, job: QueuedJob, error: Any = None) -> None:
        job.status = "failed"
        job.result = error

    def clear(self) -> None:
        self._jobs.clear()

    def __len__(self) -> int:
        return len(self._jobs)


# ---------------------------------------------------------------------------
# Scheduled workflow execution
# ---------------------------------------------------------------------------


def _cron_value_matches(field: str, value: int) -> bool:
    """Return True when a single cron field matches *value*."""

    field = field.strip()
    if field == "*":
        return True
    for part in field.split(","):
        if part.startswith("*/"):
            step = int(part[2:])
            if step <= 0:
                return False
            if value % step == 0:
                return True
            continue
        if "-" in part:
            start, end = (int(piece) for piece in part.split("-", 1))
            if start <= value <= end:
                return True
            continue
        if part and int(part) == value:
            return True
    return False


def cron_matches(expression: str, when: datetime) -> bool:
    """Match a 5-field cron expression against a local datetime."""

    if not validate_cron(expression):
        return False
    minute, hour, day, month, weekday = expression.split()
    cron_weekday = (when.weekday() + 1) % 7
    return (
        _cron_value_matches(minute, when.minute)
        and _cron_value_matches(hour, when.hour)
        and _cron_value_matches(day, when.day)
        and _cron_value_matches(month, when.month)
        and _cron_value_matches(weekday, cron_weekday)
    )


def enhancement_config_from_profile(profile: WorkflowProfile) -> EnhancementConfig:
    """Build an EnhancementConfig from a workflow profile's stored params."""

    params = dict(profile.params)
    if "input_path" not in params or "output_path" not in params:
        raise ValueError(
            f"Workflow profile '{profile.name}' must include input_path and output_path."
        )
    params["input_path"] = Path(params["input_path"])
    params["output_path"] = Path(params["output_path"])
    if params.get("checkpoint_dir") is not None:
        params["checkpoint_dir"] = Path(params["checkpoint_dir"])
    for key in ("model_chain", "destinations", "worker_devices", "restoration_ops"):
        if key in params and isinstance(params[key], list):
            params[key] = tuple(params[key])
    if "roi" in params and isinstance(params["roi"], list):
        params["roi"] = tuple(params["roi"])
    return EnhancementConfig(**params)


class WorkflowScheduler:
    """Enqueues enabled workflow profiles when their cron schedule is due."""

    def __init__(self, store: RecipeStore) -> None:
        self.store = store
        self._last_enqueued: dict[str, str] = {}

    def due_profiles(self, when: datetime | None = None) -> List[WorkflowProfile]:
        current = when or datetime.now()
        return [
            profile
            for profile in self.store.list_scheduled()
            if profile.schedule is not None and cron_matches(profile.schedule.cron, current)
        ]

    def enqueue_due_local(
        self,
        queue: LocalJobQueue,
        when: datetime | None = None,
        launch_mode: str = "cli",
    ) -> List[QueuedJob]:
        """Enqueue due profiles into the lightweight local queue once per minute."""

        current = when or datetime.now()
        stamp = current.strftime("%Y-%m-%dT%H:%M")
        queued: List[QueuedJob] = []
        for profile in self.due_profiles(current):
            key = f"{profile.name}:{stamp}:{launch_mode}"
            if key in self._last_enqueued or not profile.can_launch_from(launch_mode):
                continue
            queued.append(queue.enqueue(profile.name, launch_mode))
            self._last_enqueued[key] = stamp
        return queued

    def submit_due_jobs(
        self,
        queue: JobQueue,
        when: datetime | None = None,
        launch_mode: str = "cli",
    ):
        """Submit due workflow profiles to the shared enhancement job queue."""

        current = when or datetime.now()
        stamp = current.strftime("%Y-%m-%dT%H:%M")
        submitted = []
        for profile in self.due_profiles(current):
            key = f"{profile.name}:{stamp}:{launch_mode}:jobqueue"
            if key in self._last_enqueued or not profile.can_launch_from(launch_mode):
                continue
            submitted.append(queue.submit(enhancement_config_from_profile(profile)))
            self._last_enqueued[key] = stamp
        return submitted
