"""Custom ONNX metadata validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OnnxModelMetadata:
    input_shape: tuple[int, ...]
    output_shape: tuple[int, ...]
    opset: int
    scale: int


@dataclass(frozen=True)
class ModelValidationResult:
    valid: bool
    errors: tuple[str, ...]
    metadata: OnnxModelMetadata | None = None


def validate_custom_onnx_model(
    model_path: Path,
    metadata_path: Path | None = None,
    allowed_scales: set[int] | None = None,
    minimum_opset: int = 11,
) -> ModelValidationResult:
    """Validate custom model metadata before import."""

    if model_path.suffix.lower() != ".onnx":
        return ModelValidationResult(False, ("model file must use .onnx extension",))
    if not model_path.exists():
        return ModelValidationResult(False, (f"model file does not exist: {model_path}",))

    metadata_file = metadata_path or model_path.with_suffix(".metadata.json")
    if not metadata_file.exists():
        return ModelValidationResult(False, (f"metadata file does not exist: {metadata_file}",))

    try:
        metadata = _load_metadata(metadata_file)
    except (KeyError, TypeError, ValueError) as exc:
        return ModelValidationResult(False, (f"invalid metadata: {exc}",))

    errors = []
    scales = allowed_scales or {1, 2, 4}
    if metadata.scale not in scales:
        errors.append(f"unsupported scale {metadata.scale}; expected one of {sorted(scales)}")
    if metadata.opset < minimum_opset:
        errors.append(f"opset {metadata.opset} is below minimum {minimum_opset}")
    if len(metadata.input_shape) != 4:
        errors.append("input shape must be NCHW with four dimensions")
    if len(metadata.output_shape) != 4:
        errors.append("output shape must be NCHW with four dimensions")
    if metadata.input_shape and metadata.input_shape[1] not in {1, 3}:
        errors.append("input channels must be 1 or 3")
    if metadata.output_shape and metadata.output_shape[1] not in {1, 3}:
        errors.append("output channels must be 1 or 3")

    return ModelValidationResult(
        valid=not errors,
        errors=tuple(errors),
        metadata=metadata,
    )


def _load_metadata(path: Path) -> OnnxModelMetadata:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return OnnxModelMetadata(
        input_shape=tuple(int(value) for value in payload["input_shape"]),
        output_shape=tuple(int(value) for value in payload["output_shape"]),
        opset=int(payload["opset"]),
        scale=int(payload["scale"]),
    )
