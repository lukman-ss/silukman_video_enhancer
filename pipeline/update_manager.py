"""Offline update verification and model rollback manager.

Phase 7, Task 8
UpdateVerifier checks cryptographic SHA-256 signatures of offline packages
before they are applied.  ModelRollbackManager tracks a version history of
model files so the previous stable model and app configs can be restored
if a new package fails verification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Package manifest (shipped alongside an offline update package)
# ---------------------------------------------------------------------------


@dataclass
class UpdatePackageManifest:
    """Describes an offline update package and its expected SHA-256 digest."""

    package_name: str
    version: str
    sha256: str          # expected digest of the package file
    target: str          # "app" | "model" | "config"
    notes: str = ""
    signature: str = ""
    signature_algorithm: str = "hmac-sha256"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_name": self.package_name,
            "version": self.version,
            "sha256": self.sha256,
            "target": self.target,
            "notes": self.notes,
            "signature": self.signature,
            "signature_algorithm": self.signature_algorithm,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UpdatePackageManifest":
        return cls(
            package_name=str(d["package_name"]),
            version=str(d["version"]),
            sha256=str(d["sha256"]),
            target=str(d["target"]),
            notes=str(d.get("notes", "")),
            signature=str(d.get("signature", "")),
            signature_algorithm=str(d.get("signature_algorithm", "hmac-sha256")),
        )

    @classmethod
    def from_json_file(cls, path: Path) -> "UpdatePackageManifest":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    package_name: str
    version: str
    passed: bool
    expected_sha256: str
    actual_sha256: str
    reason: str = ""
    signature_checked: bool = False

    @property
    def failed(self) -> bool:
        return not self.passed


# ---------------------------------------------------------------------------
# UpdateVerifier
# ---------------------------------------------------------------------------


class UpdateVerifier:
    """
    Verifies an offline update package against its published SHA-256 digest.

    Usage::

        verifier = UpdateVerifier()
        manifest = UpdatePackageManifest.from_json_file(Path("update.manifest.json"))
        result = verifier.verify(manifest, Path("update_package.zip"))
        if result.passed:
            # safe to install
            ...
    """

    @staticmethod
    def sign_bytes(data: bytes, secret_key: bytes | str) -> str:
        """Return an HMAC-SHA256 signature for offline package bytes."""

        key = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
        return hmac.new(key, data, hashlib.sha256).hexdigest()

    def verify(
        self,
        manifest: UpdatePackageManifest,
        package_path: Path,
        secret_key: bytes | str | None = None,
    ) -> VerificationResult:
        """Hash *package_path* and compare with *manifest.sha256*."""
        if not package_path.exists():
            return VerificationResult(
                package_name=manifest.package_name,
                version=manifest.version,
                passed=False,
                expected_sha256=manifest.sha256,
                actual_sha256="",
                reason=f"Package file not found: {package_path}",
                signature_checked=secret_key is not None,
            )
        data = package_path.read_bytes()
        return self.verify_bytes(manifest, data, secret_key=secret_key)

    def verify_bytes(
        self,
        manifest: UpdatePackageManifest,
        data: bytes,
        secret_key: bytes | str | None = None,
    ) -> VerificationResult:
        """Verify raw *data* bytes against digest and optional HMAC signature."""
        actual = _sha256_bytes(data)
        digest_ok = actual == manifest.sha256
        signature_ok = True
        signature_checked = secret_key is not None or bool(manifest.signature)
        if secret_key is not None:
            expected_signature = self.sign_bytes(data, secret_key)
            signature_ok = bool(manifest.signature) and hmac.compare_digest(
                expected_signature,
                manifest.signature,
            )
        elif manifest.signature:
            signature_ok = False
        passed = digest_ok and signature_ok
        reason = ""
        if not digest_ok:
            reason = "SHA-256 digest mismatch."
        elif not signature_ok:
            reason = "Package signature verification failed."
        return VerificationResult(
            package_name=manifest.package_name,
            version=manifest.version,
            passed=passed,
            expected_sha256=manifest.sha256,
            actual_sha256=actual,
            reason=reason,
            signature_checked=signature_checked,
        )

    def sign_manifest(
        self,
        manifest: UpdatePackageManifest,
        data: bytes,
        secret_key: bytes | str,
    ) -> UpdatePackageManifest:
        """Return a manifest copy with digest and HMAC signature populated."""

        signed = UpdatePackageManifest.from_dict(manifest.to_dict())
        signed.sha256 = _sha256_bytes(data)
        signed.signature = self.sign_bytes(data, secret_key)
        signed.signature_algorithm = "hmac-sha256"
        return signed


# ---------------------------------------------------------------------------
# Model version snapshot
# ---------------------------------------------------------------------------


@dataclass
class ModelSnapshot:
    """A single point-in-time copy of a model file stored in the rollback store."""

    model_name: str
    version: str
    sha256: str
    snapshot_path: str      # relative path inside the rollback store directory
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "version": self.version,
            "sha256": self.sha256,
            "snapshot_path": self.snapshot_path,
            "created_at": self.created_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ModelSnapshot":
        return cls(
            model_name=str(d["model_name"]),
            version=str(d["version"]),
            sha256=str(d["sha256"]),
            snapshot_path=str(d["snapshot_path"]),
            created_at=str(d.get("created_at", "")),
            notes=str(d.get("notes", "")),
        )


# ---------------------------------------------------------------------------
# ModelRollbackManager
# ---------------------------------------------------------------------------

_INDEX_NAME = "rollback_index.json"


class ModelRollbackManager:
    """
    Tracks model version history and provides one-step rollback.

    Snapshot storage layout::

        store_dir/
            rollback_index.json      ← list of ModelSnapshot dicts
            realesr/
                1.0.0_<sha>.onnx
                0.9.0_<sha>.onnx
            ...
    """

    def __init__(self, store_dir: Path) -> None:
        self.store_dir = Path(store_dir)
        self._snapshots: List[ModelSnapshot] = self._load_index()

    # ------------------------------------------------------------------
    # Index persistence
    # ------------------------------------------------------------------

    def _index_path(self) -> Path:
        return self.store_dir / _INDEX_NAME

    def _load_index(self) -> List[ModelSnapshot]:
        p = self._index_path()
        if not p.exists():
            return []
        try:
            return [ModelSnapshot.from_dict(d) for d in json.loads(p.read_text("utf-8"))]
        except Exception:
            return []

    def _save_index(self) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._index_path().write_text(
            json.dumps([s.to_dict() for s in self._snapshots], indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Creating snapshots
    # ------------------------------------------------------------------

    def snapshot(
        self,
        model_name: str,
        version: str,
        model_path: Path,
        notes: str = "",
    ) -> ModelSnapshot:
        """Copy *model_path* into the rollback store and record a snapshot."""
        sha = _sha256_file(model_path)
        rel = f"{model_name}/{version}_{sha[:8]}{model_path.suffix}"
        dest = self.store_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model_path, dest)
        snap = ModelSnapshot(
            model_name=model_name,
            version=version,
            sha256=sha,
            snapshot_path=rel,
            notes=notes,
        )
        self._snapshots.append(snap)
        self._save_index()
        return snap

    def snapshot_bytes(
        self,
        model_name: str,
        version: str,
        data: bytes,
        suffix: str = ".onnx",
        notes: str = "",
    ) -> ModelSnapshot:
        """Store raw *data* as a snapshot (useful in tests without real files)."""
        sha = _sha256_bytes(data)
        rel = f"{model_name}/{version}_{sha[:8]}{suffix}"
        dest = self.store_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        snap = ModelSnapshot(
            model_name=model_name,
            version=version,
            sha256=sha,
            snapshot_path=rel,
            notes=notes,
        )
        self._snapshots.append(snap)
        self._save_index()
        return snap

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def history(self, model_name: str) -> List[ModelSnapshot]:
        """Return all snapshots for *model_name*, oldest first."""
        return [s for s in self._snapshots if s.model_name == model_name]

    def latest(self, model_name: str) -> Optional[ModelSnapshot]:
        h = self.history(model_name)
        return h[-1] if h else None

    def previous(self, model_name: str) -> Optional[ModelSnapshot]:
        """Return the snapshot just before the latest one, if it exists."""
        h = self.history(model_name)
        return h[-2] if len(h) >= 2 else None

    def all_model_names(self) -> List[str]:
        seen: List[str] = []
        for s in self._snapshots:
            if s.model_name not in seen:
                seen.append(s.model_name)
        return seen

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def rollback(self, model_name: str, target_path: Path) -> ModelSnapshot:
        """
        Copy the previous stable snapshot of *model_name* to *target_path*.

        Raises ``RuntimeError`` when there is no previous version to roll back to.
        """
        snap = self.previous(model_name)
        if snap is None:
            raise RuntimeError(
                f"No previous snapshot available for model '{model_name}'. "
                "Cannot roll back."
            )
        src = self.store_dir / snap.snapshot_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target_path)
        return snap

    def rollback_bytes(self, model_name: str) -> bytes:
        """Return the raw bytes of the previous snapshot (for tests)."""
        snap = self.previous(model_name)
        if snap is None:
            raise RuntimeError(f"No previous snapshot for '{model_name}'.")
        return (self.store_dir / snap.snapshot_path).read_bytes()

    # ------------------------------------------------------------------
    # Housekeeping
    # ------------------------------------------------------------------

    def prune(self, model_name: str, keep: int = 3) -> int:
        """Delete all but the *keep* most-recent snapshots. Returns count removed."""
        history = self.history(model_name)
        to_remove = history[:-keep] if len(history) > keep else []
        for snap in to_remove:
            try:
                (self.store_dir / snap.snapshot_path).unlink(missing_ok=True)
            except OSError:
                pass
            self._snapshots.remove(snap)
        if to_remove:
            self._save_index()
        return len(to_remove)
