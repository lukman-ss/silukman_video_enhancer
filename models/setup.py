"""First-run and offline model setup helpers."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from models.discovery import build_runtime_registry
from models.registry import _sha256, model_cache_dir, verify_model_file


@dataclass(frozen=True)
class ImportedModel:
    name: str
    path: Path
    sha256: str
    registered: bool


@dataclass(frozen=True)
class ModelSetupStatus:
    cache_dir: Path
    missing_models: tuple[str, ...]
    imported_models: tuple[ImportedModel, ...]

    @property
    def ready(self) -> bool:
        return not self.missing_models


def inspect_model_setup(root: Path | None = None) -> ModelSetupStatus:
    """Inspect required and imported models for first-run setup UI."""

    cache = root or model_cache_dir()
    registry = build_runtime_registry(cache)
    missing = []
    imported = []
    for name, spec in sorted(registry.items()):
        path = cache / spec.file_name
        if verify_model_file(path, spec.sha256):
            imported.append(
                ImportedModel(
                    name=name,
                    path=path,
                    sha256=_sha256(path),
                    registered=name in {"realesrgan", "srcnn", "swinir"},
                )
            )
        else:
            missing.append(name)
    return ModelSetupStatus(
        cache_dir=cache,
        missing_models=tuple(missing),
        imported_models=tuple(imported),
    )


def import_offline_model(
    source_path: Path,
    name: str | None = None,
    expected_sha256: str | None = None,
    root: Path | None = None,
) -> ImportedModel:
    """Copy a local ONNX model into the cache and write import metadata."""

    if not source_path.exists() or source_path.is_dir():
        raise ValueError(f"Model file does not exist: {source_path}")
    if source_path.suffix.lower() != ".onnx":
        raise ValueError("Offline model import requires a .onnx file.")
    actual_sha256 = _sha256(source_path)
    if expected_sha256 and actual_sha256 != expected_sha256:
        raise ValueError("Model SHA256 does not match expected checksum.")

    cache = root or model_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    model_name = name or source_path.stem
    destination = cache / source_path.name
    if source_path.resolve() != destination.resolve():
        shutil.copyfile(source_path, destination)

    imported = ImportedModel(
        name=model_name,
        path=destination,
        sha256=actual_sha256,
        registered=False,
    )
    _write_import_metadata(cache, imported)
    return imported


def _write_import_metadata(cache: Path, imported: ImportedModel) -> None:
    metadata_path = cache / "imported_models.json"
    if metadata_path.exists():
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        payload = []
    payload = [item for item in payload if item.get("name") != imported.name]
    payload.append(
        {
            **asdict(imported),
            "path": str(imported.path),
        }
    )
    metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
