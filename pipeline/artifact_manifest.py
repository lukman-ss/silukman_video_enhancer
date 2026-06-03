"""Export artifact manifest generation for reproducible outputs.

Phase 7, Task 4
After a render completes, ``ArtifactManifest`` captures all information
needed to reproduce the output: EnhancementConfig settings, model hashes,
quality metrics, and source/output media fingerprints.  Manifests are
serialised to JSON and can optionally be saved alongside the rendered file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import EnhancementConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Return the lowercase hex SHA-256 digest of *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Sub-records
# ---------------------------------------------------------------------------


@dataclass
class MediaFingerprint:
    """SHA-256 digest plus basic metadata for a media file."""

    path: str
    sha256: str
    size_bytes: int

    @classmethod
    def from_file(cls, path: Path) -> "MediaFingerprint":
        stat = path.stat()
        return cls(
            path=str(path),
            sha256=_sha256_file(path),
            size_bytes=stat.st_size,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "size_bytes": self.size_bytes}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaFingerprint":
        return cls(
            path=str(data["path"]),
            sha256=str(data["sha256"]),
            size_bytes=int(data["size_bytes"]),
        )


@dataclass
class ModelRecord:
    """Identifies a model file used during the render."""

    name: str
    path: str
    sha256: str

    @classmethod
    def from_file(cls, name: str, path: Path) -> "ModelRecord":
        return cls(name=name, path=str(path), sha256=_sha256_file(path))

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "path": self.path, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelRecord":
        return cls(
            name=str(data["name"]),
            path=str(data["path"]),
            sha256=str(data["sha256"]),
        )


# ---------------------------------------------------------------------------
# ArtifactManifest
# ---------------------------------------------------------------------------


@dataclass
class ArtifactManifest:
    """Complete reproducibility record for a finished render job."""

    # Render identity
    job_id: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Settings snapshot (flat dict of EnhancementConfig-compatible params)
    settings: Dict[str, Any] = field(default_factory=dict)

    # Model records used during this render
    models: List[ModelRecord] = field(default_factory=list)

    # Quality metrics produced after render (PSNR, SSIM, VMAF, etc.)
    metrics: Dict[str, Any] = field(default_factory=dict)

    # Source media fingerprint
    source: Optional[MediaFingerprint] = None

    # Output media fingerprint
    output: Optional[MediaFingerprint] = None

    # Free-form notes
    notes: str = ""

    # ------------------------------------------------------------------
    # Convenience builders
    # ------------------------------------------------------------------

    def add_model_from_file(self, name: str, path: Path) -> "ArtifactManifest":
        """Hash *path* and append a ModelRecord. Returns self for chaining."""
        self.models.append(ModelRecord.from_file(name, path))
        return self

    def set_source_from_file(self, path: Path) -> "ArtifactManifest":
        self.source = MediaFingerprint.from_file(path)
        return self

    def set_output_from_file(self, path: Path) -> "ArtifactManifest":
        self.output = MediaFingerprint.from_file(path)
        return self

    def add_model_stub(self, name: str, sha256: str, path: str = "") -> "ArtifactManifest":
        """Add a model record without hashing (for testing / remote paths)."""
        self.models.append(ModelRecord(name=name, path=path, sha256=sha256))
        return self

    def set_source_stub(
        self, path: str, sha256: str, size_bytes: int = 0
    ) -> "ArtifactManifest":
        self.source = MediaFingerprint(path=path, sha256=sha256, size_bytes=size_bytes)
        return self

    def set_output_stub(
        self, path: str, sha256: str, size_bytes: int = 0
    ) -> "ArtifactManifest":
        self.output = MediaFingerprint(path=path, sha256=sha256, size_bytes=size_bytes)
        return self

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "job_id": self.job_id,
            "created_at": self.created_at,
            "settings": self.settings,
            "models": [m.to_dict() for m in self.models],
            "metrics": self.metrics,
            "notes": self.notes,
        }
        if self.source is not None:
            d["source"] = self.source.to_dict()
        if self.output is not None:
            d["output"] = self.output.to_dict()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactManifest":
        source = (
            MediaFingerprint.from_dict(data["source"]) if "source" in data else None
        )
        output = (
            MediaFingerprint.from_dict(data["output"]) if "output" in data else None
        )
        return cls(
            job_id=str(data["job_id"]),
            created_at=str(data.get("created_at", "")),
            settings=dict(data.get("settings", {})),
            models=[ModelRecord.from_dict(m) for m in data.get("models", [])],
            metrics=dict(data.get("metrics", {})),
            source=source,
            output=output,
            notes=str(data.get("notes", "")),
        )

    @classmethod
    def from_json(cls, text: str) -> "ArtifactManifest":
        return cls.from_dict(json.loads(text))

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def save_next_to(self, output_path: Path) -> Path:
        """Write manifest as <output_stem>.manifest.json beside the render output."""
        manifest_path = output_path.with_suffix("").with_suffix(".manifest.json")
        manifest_path.write_text(self.to_json(), encoding="utf-8")
        return manifest_path

    def save_to(self, path: Path) -> Path:
        """Write manifest to an explicit *path*."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def load_from(cls, path: Path) -> "ArtifactManifest":
        return cls.from_json(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Integrity
    # ------------------------------------------------------------------

    def manifest_digest(self) -> str:
        """SHA-256 of the canonical JSON representation (for tamper detection)."""
        return _sha256_bytes(self.to_json().encode("utf-8"))


def write_render_manifest(
    config: EnhancementConfig,
    *,
    job_id: str = "local-render",
    metrics: Dict[str, Any] | None = None,
    models: List[ModelRecord] | None = None,
    notes: str = "",
) -> Path:
    """Write a reproducibility manifest next to a completed render output."""

    manifest = ArtifactManifest(
        job_id=job_id,
        settings={
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(config).items()
        },
        metrics=metrics or {},
        models=models or [],
        notes=notes,
    )
    if config.input_path.exists():
        manifest.set_source_from_file(config.input_path)
    if config.output_path.exists():
        manifest.set_output_from_file(config.output_path)
    return manifest.save_next_to(config.output_path)
