"""Drop-in ONNX model discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from models.registry import MODEL_REGISTRY, ModelSpec, model_cache_dir


@dataclass(frozen=True)
class DiscoveredModel:
    name: str
    path: Path
    registered: bool


def discover_onnx_models(root: Path | None = None) -> List[DiscoveredModel]:
    """Scan the model cache for registered and community ONNX models."""

    search_root = root or model_cache_dir()
    if not search_root.exists():
        return []
    registered_by_file = {spec.file_name: spec.name for spec in MODEL_REGISTRY.values()}
    models = []
    for path in sorted(search_root.glob("*.onnx")):
        name = registered_by_file.get(path.name, path.stem)
        models.append(
            DiscoveredModel(
                name=name,
                path=path,
                registered=path.name in registered_by_file,
            )
        )
    return models


def build_runtime_registry(root: Path | None = None) -> dict[str, ModelSpec]:
    """Merge static registry models with drop-in community model specs."""

    registry = dict(MODEL_REGISTRY)
    for discovered in discover_onnx_models(root):
        if discovered.name not in registry:
            registry[discovered.name] = ModelSpec(
                name=discovered.name,
                file_name=discovered.path.name,
                scale=2,
            )
    return registry
