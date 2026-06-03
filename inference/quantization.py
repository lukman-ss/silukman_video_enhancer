"""FP16 quantization planning helpers."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path


FP16_CAPABLE_PROVIDERS = {
    "CUDAExecutionProvider",
    "CoreMLExecutionProvider",
    "DmlExecutionProvider",
}

INT8_CAPABLE_PROVIDERS = {
    "CPUExecutionProvider",
    "DmlExecutionProvider",
}


@dataclass(frozen=True)
class QuantizationPlan:
    enabled: bool
    precision: str
    reason: str


def plan_fp16_quantization(requested: bool, providers: list[str]) -> QuantizationPlan:
    if not requested:
        return QuantizationPlan(False, "fp32", "fp16 not requested")
    if any(provider in FP16_CAPABLE_PROVIDERS for provider in providers):
        return QuantizationPlan(True, "fp16", "accelerated provider supports fp16")
    return QuantizationPlan(False, "fp32", "no selected provider supports fp16")


def plan_int8_quantization(requested: bool, providers: list[str]) -> QuantizationPlan:
    if not requested:
        return QuantizationPlan(False, "fp32", "int8 not requested")
    if any(provider in INT8_CAPABLE_PROVIDERS for provider in providers):
        return QuantizationPlan(True, "int8", "selected provider supports int8")
    return QuantizationPlan(False, "fp32", "no selected provider supports int8")


def plan_quantization(
    enable_fp16: bool,
    enable_int8: bool,
    providers: list[str],
) -> QuantizationPlan:
    int8 = plan_int8_quantization(enable_int8, providers)
    if int8.enabled:
        return int8
    return plan_fp16_quantization(enable_fp16, providers)


def quantize_onnx_int8(model_path: Path, output_path: Path) -> Path:
    """Quantize an ONNX model to INT8 using onnxruntime when installed."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    quantize_dynamic = _import_quantize_dynamic()
    quantize_dynamic(str(model_path), str(output_path), weight_type=_quant_type_qint8())
    return output_path


def _import_quantize_dynamic():
    module = importlib.import_module("onnxruntime.quantization")
    return module.quantize_dynamic


def _quant_type_qint8():
    module = importlib.import_module("onnxruntime.quantization")
    return module.QuantType.QInt8
