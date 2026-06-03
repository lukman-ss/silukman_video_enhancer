"""Execution provider expansion planning."""

from __future__ import annotations

from dataclasses import dataclass


EXPERIMENTAL_PROVIDERS = {
    "vulkan": "VulkanExecutionProvider",
    "webgpu": "WebGPUExecutionProvider",
    "openvino": "OpenVINOExecutionProvider",
    "qnn": "QNNExecutionProvider",
}


@dataclass(frozen=True)
class ProviderAdapterPlan:
    device: str
    provider: str
    available: bool
    fallback_provider: str = "CPUExecutionProvider"

    @property
    def providers(self) -> list[str]:
        if self.available:
            return [self.provider, self.fallback_provider]
        return [self.fallback_provider]


def plan_experimental_provider(
    device: str,
    available_providers: list[str],
) -> ProviderAdapterPlan:
    """Plan Vulkan/WebGPU provider usage with CPU fallback."""

    key = device.lower()
    if key not in EXPERIMENTAL_PROVIDERS:
        raise ValueError(f"Unsupported experimental provider device: {device}")
    provider = EXPERIMENTAL_PROVIDERS[key]
    return ProviderAdapterPlan(
        device=key,
        provider=provider,
        available=provider in available_providers,
    )


def plan_accelerator_provider(
    device: str,
    available_providers: list[str],
) -> ProviderAdapterPlan:
    """Plan experimental GPU/NPU provider usage with CPU fallback."""

    return plan_experimental_provider(device, available_providers)
