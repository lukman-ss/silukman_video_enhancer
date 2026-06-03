"""Startup warmup benchmark helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List

from inference.runtime import ONNXFrameUpscaler


@dataclass(frozen=True)
class BenchmarkResult:
    provider: str
    frames: int
    elapsed_seconds: float

    @property
    def fps(self) -> float:
        if self.elapsed_seconds <= 0:
            return 0.0
        return self.frames / self.elapsed_seconds


def run_warmup_benchmark(
    providers: Iterable[str],
    warmup: Callable[[str], None],
    frames: int = 10,
) -> List[BenchmarkResult]:
    """Run a short provider warmup benchmark and return fastest-sortable results."""

    results = []
    for provider in providers:
        started = time.perf_counter()
        for _ in range(frames):
            warmup(provider)
        elapsed = time.perf_counter() - started
        results.append(
            BenchmarkResult(
                provider=provider,
                frames=frames,
                elapsed_seconds=elapsed,
            )
        )
    return sorted(results, key=lambda result: result.fps, reverse=True)


def run_onnx_provider_benchmark(
    model_path: Path,
    providers: Iterable[str],
    width: int,
    height: int,
    frames: int = 10,
) -> List[BenchmarkResult]:
    """Run real ONNX warmup inference against each available provider."""

    dummy_frame = bytes(width * height * 3)

    def warmup(provider: str) -> None:
        upscaler = ONNXFrameUpscaler(
            model_path,
            requested_device="cpu",
            provider_override=[provider],
        )
        upscaler.upscale(dummy_frame, width, height)

    return run_warmup_benchmark(providers, warmup, frames=frames)
