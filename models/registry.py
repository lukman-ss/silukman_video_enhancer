"""Local model registry and integrity checks."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class ModelSpec:
    name: str
    file_name: str
    scale: int
    sha256: Optional[str] = None


MODEL_REGISTRY: Dict[str, ModelSpec] = {
    "realesrgan": ModelSpec(
        name="realesrgan",
        file_name="realesrgan-x2.onnx",
        scale=2,
    ),
    "srcnn": ModelSpec(
        name="srcnn",
        file_name="srcnn-x2.onnx",
        scale=2,
    ),
    "swinir": ModelSpec(
        name="swinir",
        file_name="swinir-lightweight-x2.onnx",
        scale=2,
    ),
}


def model_cache_dir() -> Path:
    root = os.environ.get("SILUKMAN_MODEL_DIR")
    if root:
        return Path(root).expanduser()
    return Path.home() / ".cache" / "silukman_video_enhancer" / "models"


def resolve_model_path(model_name: str) -> Path:
    return model_cache_dir() / get_model_spec(model_name).file_name


def get_model_spec(model_name: str) -> ModelSpec:
    try:
        return MODEL_REGISTRY[model_name]
    except KeyError as exc:
        available = ", ".join(sorted(MODEL_REGISTRY))
        raise ValueError(f"Unknown model `{model_name}`. Available: {available}") from exc


def verify_model_file(model_path: Path, expected_sha256: Optional[str]) -> bool:
    if expected_sha256 is None:
        return model_path.exists()
    return _sha256(model_path) == expected_sha256


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
