"""Local audit log for API requests, plugin actions, job lifecycle events, and permission changes.

Phase 7, Task 6
AuditLog writes timestamped, structured entries to a newline-delimited JSON
file.  Each entry captures event_type, actor/source, optional job/plugin
identifiers, and a sanitised detail dict — never raw media paths or content.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Event type catalogue
# ---------------------------------------------------------------------------

EVENT_API_REQUEST = "api.request"
EVENT_PLUGIN_ACTION = "plugin.action"
EVENT_JOB_QUEUED = "job.queued"
EVENT_JOB_STARTED = "job.started"
EVENT_JOB_COMPLETED = "job.completed"
EVENT_JOB_FAILED = "job.failed"
EVENT_PERMISSION_GRANTED = "permission.granted"
EVENT_PERMISSION_DENIED = "permission.denied"

ALL_EVENT_TYPES = {
    EVENT_API_REQUEST,
    EVENT_PLUGIN_ACTION,
    EVENT_JOB_QUEUED,
    EVENT_JOB_STARTED,
    EVENT_JOB_COMPLETED,
    EVENT_JOB_FAILED,
    EVENT_PERMISSION_GRANTED,
    EVENT_PERMISSION_DENIED,
}

# Keys that must never appear in audit detail payloads (privacy guard).
_SENSITIVE_KEYS = {
    "input_path",
    "output_path",
    "source_path",
    "file_path",
    "password",
    "token",
    "secret",
    "api_key",
}


def _sanitise(detail: Dict[str, Any]) -> Dict[str, Any]:
    """Strip sensitive keys from an entry detail dict."""
    return {k: v for k, v in detail.items() if k not in _SENSITIVE_KEYS}


# ---------------------------------------------------------------------------
# AuditEntry
# ---------------------------------------------------------------------------


@dataclass
class AuditEntry:
    event_type: str
    actor: str                          # e.g. "api", "plugin:my_plugin", "scheduler"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    job_id: Optional[str] = None
    plugin_id: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_type not in ALL_EVENT_TYPES:
            raise ValueError(
                f"Unknown event_type '{self.event_type}'. "
                f"Valid types: {sorted(ALL_EVENT_TYPES)}."
            )
        # Sanitise in-place
        self.detail = _sanitise(self.detail)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
        }
        if self.job_id is not None:
            d["job_id"] = self.job_id
        if self.plugin_id is not None:
            d["plugin_id"] = self.plugin_id
        if self.detail:
            d["detail"] = self.detail
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEntry":
        return cls(
            event_type=str(data["event_type"]),
            actor=str(data["actor"]),
            timestamp=str(data.get("timestamp", "")),
            job_id=data.get("job_id"),
            plugin_id=data.get("plugin_id"),
            detail=dict(data.get("detail", {})),
        )

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))


# ---------------------------------------------------------------------------
# AuditLog — thread-safe NDJSON writer
# ---------------------------------------------------------------------------


class AuditLog:
    """
    Append-only, thread-safe audit log backed by a newline-delimited JSON file.

    Usage::

        log = AuditLog(Path("audit.ndjson"))
        log.record(EVENT_API_REQUEST, actor="api", detail={"endpoint": "/jobs"})
        entries = log.tail(20)
    """

    def __init__(self, path: Path, max_bytes: int = 10 * 1024 * 1024) -> None:
        """
        Args:
            path: File path for the NDJSON log.
            max_bytes: Rotate (truncate oldest) when file exceeds this size.
                       Set to 0 to disable rotation.
        """
        self.path = Path(path)
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def record(
        self,
        event_type: str,
        actor: str,
        job_id: Optional[str] = None,
        plugin_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        """Create and persist an AuditEntry. Returns the written entry."""
        entry = AuditEntry(
            event_type=event_type,
            actor=actor,
            job_id=job_id,
            plugin_id=plugin_id,
            detail=detail or {},
        )
        self._append(entry)
        return entry

    def _append(self, entry: AuditEntry) -> None:
        line = entry.to_json_line() + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line)
            if self.max_bytes > 0:
                self._maybe_rotate()

    def _maybe_rotate(self) -> None:
        """Drop the oldest half of the log if file exceeds max_bytes."""
        try:
            if self.path.stat().st_size <= self.max_bytes:
                return
            lines = self.path.read_text(encoding="utf-8").splitlines(keepends=True)
            keep = lines[len(lines) // 2 :]
            self.path.write_text("".join(keep), encoding="utf-8")
        except OSError:
            pass  # best-effort

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def tail(self, n: int = 100) -> List[AuditEntry]:
        """Return the last *n* entries from the log."""
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        entries: List[AuditEntry] = []
        for line in lines[-n:]:
            line = line.strip()
            if line:
                try:
                    entries.append(AuditEntry.from_dict(json.loads(line)))
                except Exception:
                    pass
        return entries

    def all_entries(self) -> List[AuditEntry]:
        """Return every entry in the log."""
        return self.tail(n=10 ** 9)

    def filter(
        self,
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        job_id: Optional[str] = None,
        plugin_id: Optional[str] = None,
    ) -> List[AuditEntry]:
        """Return entries matching the supplied criteria (all optional)."""
        results = []
        for entry in self.all_entries():
            if event_type and entry.event_type != event_type:
                continue
            if actor and entry.actor != actor:
                continue
            if job_id and entry.job_id != job_id:
                continue
            if plugin_id and entry.plugin_id != plugin_id:
                continue
            results.append(entry)
        return results

    def clear(self) -> None:
        """Erase all log entries (destructive — for tests / maintenance only)."""
        if self.path.exists():
            self.path.write_text("", encoding="utf-8")

    # ------------------------------------------------------------------
    # Convenience factory helpers
    # ------------------------------------------------------------------

    def log_api(self, endpoint: str, method: str = "GET", status: int = 200) -> AuditEntry:
        return self.record(
            EVENT_API_REQUEST,
            actor="api",
            detail={"endpoint": endpoint, "method": method, "status": status},
        )

    def log_plugin(self, plugin_id: str, action: str) -> AuditEntry:
        return self.record(
            EVENT_PLUGIN_ACTION,
            actor=f"plugin:{plugin_id}",
            plugin_id=plugin_id,
            detail={"action": action},
        )

    def log_job(self, event_type: str, job_id: str, actor: str = "scheduler") -> AuditEntry:
        return self.record(event_type, actor=actor, job_id=job_id)

    def log_permission(self, granted: bool, plugin_id: str, permission: str) -> AuditEntry:
        etype = EVENT_PERMISSION_GRANTED if granted else EVENT_PERMISSION_DENIED
        return self.record(
            etype,
            actor=f"sandbox:{plugin_id}",
            plugin_id=plugin_id,
            detail={"permission": permission},
        )
