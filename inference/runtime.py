"""ONNX Runtime provider selection and frame upscaling."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from inference.quantization import plan_quantization


class ONNXRuntimeUnavailableError(RuntimeError):
    """Raised when ONNX Runtime is needed but not installed."""


class ModelLoadError(RuntimeError):
    """Raised when a selected ONNX model cannot be loaded."""


@dataclass(frozen=True)
class ProviderSelection:
    requested_device: str
    providers: List[str]
    available_providers: List[str]


DEVICE_PROVIDER_PRIORITY = {
    "cpu": ["CPUExecutionProvider"],
    "cuda": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    "coreml": ["CoreMLExecutionProvider", "CPUExecutionProvider"],
    "directml": ["DmlExecutionProvider", "CPUExecutionProvider"],
    "vulkan": ["VulkanExecutionProvider", "CPUExecutionProvider"],
    "webgpu": ["WebGPUExecutionProvider", "CPUExecutionProvider"],
    "openvino": ["OpenVINOExecutionProvider", "CPUExecutionProvider"],
    "qnn": ["QNNExecutionProvider", "CPUExecutionProvider"],
    "auto": [
        "CUDAExecutionProvider",
        "CoreMLExecutionProvider",
        "DmlExecutionProvider",
        "OpenVINOExecutionProvider",
        "QNNExecutionProvider",
        "VulkanExecutionProvider",
        "WebGPUExecutionProvider",
        "CPUExecutionProvider",
    ],
}


def select_execution_providers(
    requested_device: str,
    available_providers: Sequence[str],
) -> ProviderSelection:
    preferred = DEVICE_PROVIDER_PRIORITY[requested_device]
    selected = [provider for provider in preferred if provider in available_providers]
    if not selected and "CPUExecutionProvider" in available_providers:
        selected = ["CPUExecutionProvider"]
    if not selected:
        raise ONNXRuntimeUnavailableError(
            "No compatible ONNX Runtime execution providers are available."
        )
    return ProviderSelection(
        requested_device=requested_device,
        providers=selected,
        available_providers=list(available_providers),
    )


def available_execution_providers() -> List[str]:
    runtime = _import_onnxruntime()
    return list(runtime.get_available_providers())


class ONNXFrameUpscaler:
    """Generic RGB frame upscaler for single-input ONNX super-resolution models."""

    def __init__(
        self,
        model_path: Path,
        requested_device: str,
        provider_override: Sequence[str] | None = None,
        enable_fp16: bool = False,
        enable_int8: bool = False,
    ) -> None:
        if not model_path.exists():
            raise ModelLoadError(f"Model file does not exist: {model_path}")
        runtime = _import_onnxruntime()
        providers = (
            list(provider_override)
            if provider_override is not None
            else select_execution_providers(
                requested_device,
                runtime.get_available_providers(),
            ).providers
        )
        self.session = runtime.InferenceSession(str(model_path), providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.quantization = plan_quantization(enable_fp16, enable_int8, list(providers))

    def upscale(self, frame: bytes, width: int, height: int) -> bytes:
        numpy = _import_numpy()
        array = numpy.frombuffer(frame, dtype=numpy.uint8).reshape((height, width, 3))
        dtype = numpy.float16 if self.quantization.enabled else numpy.float32
        tensor = array.astype(dtype) / 255.0
        tensor = numpy.transpose(tensor, (2, 0, 1))[None, ...]
        output = self.session.run(None, {self.input_name: tensor})[0]
        if output.ndim == 4:
            output = output[0]
        if output.shape[0] in (1, 3):
            output = numpy.transpose(output, (1, 2, 0))
        output = numpy.clip(output * 255.0, 0, 255).astype(numpy.uint8)
        return output.tobytes()


def _import_onnxruntime():
    try:
        return importlib.import_module("onnxruntime")
    except ImportError as exc:
        raise ONNXRuntimeUnavailableError(
            "onnxruntime is not installed. Install the `onnx` extra or use the "
            "built-in FFmpeg baseline upscaler."
        ) from exc


def _import_numpy():
    try:
        return importlib.import_module("numpy")
    except ImportError as exc:
        raise ONNXRuntimeUnavailableError(
            "numpy is required for ONNX frame conversion."
        ) from exc
