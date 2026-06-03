"""Versioned local model package format."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from models.registry import _sha256, model_cache_dir


PACKAGE_MANIFEST = "silukman_model_package.json"


@dataclass(frozen=True)
class ModelPackageManifest:
    name: str
    version: str
    model_file: str
    sha256: str
    metadata_file: str | None = None


def create_model_package(
    name: str,
    version: str,
    model_path: Path,
    package_dir: Path,
    metadata_path: Path | None = None,
) -> ModelPackageManifest:
    """Create a local versioned model bundle directory."""

    if not model_path.exists():
        raise ValueError(f"Model file does not exist: {model_path}")
    package_dir.mkdir(parents=True, exist_ok=True)
    model_dest = package_dir / model_path.name
    shutil.copyfile(model_path, model_dest)
    metadata_file = None
    if metadata_path is not None:
        metadata_dest = package_dir / metadata_path.name
        shutil.copyfile(metadata_path, metadata_dest)
        metadata_file = metadata_dest.name
    manifest = ModelPackageManifest(
        name=name,
        version=version,
        model_file=model_dest.name,
        sha256=_sha256(model_dest),
        metadata_file=metadata_file,
    )
    (package_dir / PACKAGE_MANIFEST).write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def import_model_package(
    package_dir: Path,
    root: Path | None = None,
    minimum_version: str | None = None,
) -> Path:
    """Import a versioned model package into the local cache."""

    manifest = read_model_package_manifest(package_dir)
    if minimum_version and manifest.version < minimum_version:
        raise ValueError(f"Model package version {manifest.version} is below {minimum_version}.")
    model_path = package_dir / manifest.model_file
    if _sha256(model_path) != manifest.sha256:
        raise ValueError("Model package checksum does not match manifest.")
    cache = root or model_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / manifest.model_file
    shutil.copyfile(model_path, destination)
    if manifest.metadata_file:
        shutil.copyfile(package_dir / manifest.metadata_file, cache / manifest.metadata_file)
    return destination


def read_model_package_manifest(package_dir: Path) -> ModelPackageManifest:
    manifest_path = package_dir / PACKAGE_MANIFEST
    if not manifest_path.exists():
        raise ValueError(f"Model package manifest does not exist: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return ModelPackageManifest(
        name=payload["name"],
        version=payload["version"],
        model_file=payload["model_file"],
        sha256=payload["sha256"],
        metadata_file=payload.get("metadata_file"),
    )
