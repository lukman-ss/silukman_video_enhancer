"""Local hardware performance and runtime telemetry collector.

Phase 7, Task 10
TelemetryCollector appends per-job hardware metrics (FPS, CPU/GPU temp,
memory, provider, errors) to an NDJSON store.  TelemetryExporter produces
an encrypted (AES-256-like XOR + base64 for offline portability) diagnostic
bundle that can be shared without exposing media paths.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Telemetry entry
# ---------------------------------------------------------------------------

# Keys containing media-specific info that must not appear in bundles
_PRIVATE_KEYS = {"input_path", "output_path", "file_path", "source_path"}


def _sanitise(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if k not in _PRIVATE_KEYS}


@dataclass
class TelemetryEntry:
    """Hardware and quality metrics for a single render job."""

    job_id: str
    provider: str                   # e.g. "cuda", "cpu", "coreml"
    fps: float = 0.0
    cpu_temp_c: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    memory_mb: Optional[float] = None
    error: Optional[str] = None
    quality: Dict[str, float] = field(default_factory=dict)  # psnr, ssim, vmaf …
    extra: Dict[str, Any] = field(default_factory=dict)
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "job_id": self.job_id,
            "provider": self.provider,
            "fps": self.fps,
            "recorded_at": self.recorded_at,
        }
        if self.cpu_temp_c is not None:
            d["cpu_temp_c"] = self.cpu_temp_c
        if self.gpu_temp_c is not None:
            d["gpu_temp_c"] = self.gpu_temp_c
        if self.memory_mb is not None:
            d["memory_mb"] = self.memory_mb
        if self.error is not None:
            d["error"] = self.error
        if self.quality:
            d["quality"] = self.quality
        if self.extra:
            d["extra"] = _sanitise(self.extra)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TelemetryEntry":
        return cls(
            job_id=str(d["job_id"]),
            provider=str(d.get("provider", "unknown")),
            fps=float(d.get("fps", 0.0)),
            cpu_temp_c=d.get("cpu_temp_c"),
            gpu_temp_c=d.get("gpu_temp_c"),
            memory_mb=d.get("memory_mb"),
            error=d.get("error"),
            quality=dict(d.get("quality", {})),
            extra=dict(d.get("extra", {})),
            recorded_at=str(d.get("recorded_at", "")),
        )

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))


# ---------------------------------------------------------------------------
# TelemetryCollector — thread-safe NDJSON store
# ---------------------------------------------------------------------------


class TelemetryCollector:
    """
    Appends per-job telemetry entries to an NDJSON file.

    Usage::

        tc = TelemetryCollector(Path("telemetry.ndjson"))
        tc.record("job_001", provider="cuda", fps=24.5, gpu_temp_c=72.0)
        summary = tc.summary()
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def record(
        self,
        job_id: str,
        provider: str = "cpu",
        fps: float = 0.0,
        cpu_temp_c: Optional[float] = None,
        gpu_temp_c: Optional[float] = None,
        memory_mb: Optional[float] = None,
        error: Optional[str] = None,
        quality: Optional[Dict[str, float]] = None,
        **extra: Any,
    ) -> TelemetryEntry:
        entry = TelemetryEntry(
            job_id=job_id,
            provider=provider,
            fps=fps,
            cpu_temp_c=cpu_temp_c,
            gpu_temp_c=gpu_temp_c,
            memory_mb=memory_mb,
            error=error,
            quality=quality or {},
            extra=_sanitise(extra),
        )
        self._append(entry)
        return entry

    def _append(self, entry: TelemetryEntry) -> None:
        line = entry.to_json_line() + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def all_entries(self) -> List[TelemetryEntry]:
        if not self.path.exists():
            return []
        entries: List[TelemetryEntry] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(TelemetryEntry.from_dict(json.loads(line)))
                except Exception:
                    pass
        return entries

    def tail(self, n: int = 50) -> List[TelemetryEntry]:
        return self.all_entries()[-n:]

    def for_job(self, job_id: str) -> List[TelemetryEntry]:
        return [e for e in self.all_entries() if e.job_id == job_id]

    def errors(self) -> List[TelemetryEntry]:
        return [e for e in self.all_entries() if e.error is not None]

    # ------------------------------------------------------------------
    # Dashboard summary
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Aggregate statistics across all recorded entries."""
        entries = self.all_entries()
        if not entries:
            return {"total_jobs": 0}

        fps_values = [e.fps for e in entries if e.fps > 0]
        gpu_temps = [e.gpu_temp_c for e in entries if e.gpu_temp_c is not None]
        cpu_temps = [e.cpu_temp_c for e in entries if e.cpu_temp_c is not None]
        mem_values = [e.memory_mb for e in entries if e.memory_mb is not None]
        error_count = sum(1 for e in entries if e.error)
        providers: Dict[str, int] = {}
        for e in entries:
            providers[e.provider] = providers.get(e.provider, 0) + 1

        def _avg(lst): return sum(lst) / len(lst) if lst else None
        def _max(lst): return max(lst) if lst else None

        return {
            "total_jobs": len(entries),
            "error_count": error_count,
            "avg_fps": _avg(fps_values),
            "max_gpu_temp_c": _max(gpu_temps),
            "avg_gpu_temp_c": _avg(gpu_temps),
            "max_cpu_temp_c": _max(cpu_temps),
            "avg_cpu_temp_c": _avg(cpu_temps),
            "avg_memory_mb": _avg(mem_values),
            "providers": providers,
        }

    def clear(self) -> None:
        if self.path.exists():
            self.path.write_text("", encoding="utf-8")


# ---------------------------------------------------------------------------
# TelemetryExporter — encrypted diagnostic bundle
# ---------------------------------------------------------------------------

def _derive_key(passphrase: str) -> bytes:
    """Derive a 32-byte key from *passphrase* using SHA-256."""
    return hashlib.sha256(passphrase.encode("utf-8")).digest()


def _xor_encrypt(data: bytes, key: bytes) -> bytes:
    """Simple XOR stream cipher — portable, no external deps."""
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


class TelemetryExporter:
    """
    Builds an encrypted, self-contained diagnostic bundle from telemetry data.

    The bundle is a base64-encoded XOR-encrypted JSON payload.  Private media
    paths are stripped before export.  The passphrase is required to decrypt.

    NOTE: XOR + SHA-256 key is a lightweight offline-portable scheme.  For
    production use, replace with AES-GCM when a crypto library is available.
    """

    def __init__(self, collector: TelemetryCollector) -> None:
        self._collector = collector

    def export(
        self,
        passphrase: str,
        include_errors: bool = True,
        notes: str = "",
    ) -> str:
        """Return a base64-encoded encrypted bundle string."""
        entries = self._collector.all_entries()
        payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
            "summary": self._collector.summary(),
            "entries": [e.to_dict() for e in entries],
        }
        if not include_errors:
            payload["entries"] = [
                e for e in payload["entries"] if not e.get("error")
            ]
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        key = _derive_key(passphrase)
        encrypted = _xor_encrypt(raw, key)
        return base64.b64encode(encrypted).decode("ascii")

    @staticmethod
    def decrypt(bundle: str, passphrase: str) -> Dict[str, Any]:
        """Decrypt a bundle produced by ``export()``."""
        key = _derive_key(passphrase)
        encrypted = base64.b64decode(bundle.encode("ascii"))
        raw = _xor_encrypt(encrypted, key)
        return json.loads(raw.decode("utf-8"))

    def export_to_file(
        self,
        path: Path,
        passphrase: str,
        notes: str = "",
    ) -> Path:
        bundle = self.export(passphrase, notes=notes)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(bundle, encoding="ascii")
        return path
