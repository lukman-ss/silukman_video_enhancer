"""Background workers used by the Python desktop UI."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Callable, List

from app.config import EnhancementConfig
from pipeline.runner import run_enhancement


class PipelineNotImplementedError(RuntimeError):
    """Raised until desktop execution is wired to the full pipeline."""


class BatchCancelledError(RuntimeError):
    """Raised when a desktop batch run is cancelled cooperatively."""


DesktopProgressEmitter = Callable[[int, str], None]


def run_desktop_job(
    config: EnhancementConfig,
    emit_progress: DesktopProgressEmitter,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    """Run the real enhancement pipeline with desktop-friendly progress events."""

    config.validate(require_existing_input=True)

    def forward_progress(current: int, total: int | None, message: str) -> None:
        if should_cancel is not None and should_cancel():
            raise BatchCancelledError("desktop batch cancelled")
        if total and total > 0:
            percent = min(100, max(0, round((current / total) * 100)))
        else:
            percent = 0 if current <= 0 else min(100, current)
        emit_progress(percent, message)

    emit_progress(0, f"Starting: {config.summary()}")
    output_path = run_enhancement(config, forward_progress)
    emit_progress(100, f"Enhanced video written to: {output_path}")
    return output_path


def run_placeholder_job(config: EnhancementConfig, emit_progress: DesktopProgressEmitter) -> Path:
    """Backward-compatible alias for older tests and imports."""

    return run_desktop_job(config, emit_progress)


BatchFileProgressEmitter = Callable[[int, int, int, str], None]
# (file_index, file_total, percent, message)


def run_batch_jobs(
    configs: List[EnhancementConfig],
    emit: BatchFileProgressEmitter,
    stop_flag: Callable[[], bool] | None = None,
) -> List[Path]:
    """Process a list of EnhancementConfig sequentially.

    Calls ``emit(file_index, file_total, percent, message)`` for each event.
    Processing stops early if ``stop_flag`` returns True.
    """
    results: List[Path] = []
    total = len(configs)
    for idx, config in enumerate(configs):
        if stop_flag is not None and stop_flag():
            emit(idx, total, 0, f"[{idx + 1}/{total}] Cancelled.")
            break

        def forward(percent: int, message: str, _idx: int = idx) -> None:
            emit(_idx, total, percent, message)

        try:
            output = run_desktop_job(config, forward, should_cancel=stop_flag)
            results.append(output)
            emit(idx, total, 100, f"[{idx + 1}/{total}] Done: {output.name}")
        except BatchCancelledError:
            emit(idx, total, 0, f"[{idx + 1}/{total}] Cancelled.")
            break
        except Exception as exc:  # pragma: no cover - defensive boundary
            emit(idx, total, 0, f"[{idx + 1}/{total}] Error: {exc}")
    return results


class BatchCancelToken:
    """Thread-safe cancellation flag for desktop batch workers."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()
