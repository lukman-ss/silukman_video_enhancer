"""Model distillation and pruning workflow helpers."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from models.registry import _sha256


@dataclass(frozen=True)
class ModelOptimizationPlan:
    source_model: Path
    output_model: Path
    operation: str
    command: tuple[str, ...]
    target_sparsity: float | None = None
    teacher_model: Path | None = None


@dataclass(frozen=True)
class ModelOptimizationResult:
    output_model: Path
    sha256: str
    command: tuple[str, ...]


def plan_pruning(
    source_model: Path,
    output_model: Path,
    command: str | Iterable[str],
    target_sparsity: float = 0.5,
) -> ModelOptimizationPlan:
    """Plan a local ONNX pruning workflow."""

    if not 0 < target_sparsity < 1:
        raise ValueError("target_sparsity must be between 0 and 1.")
    return ModelOptimizationPlan(
        source_model=source_model,
        output_model=output_model,
        operation="prune",
        command=tuple(_split_command(command)),
        target_sparsity=target_sparsity,
    )


def plan_distillation(
    teacher_model: Path,
    source_model: Path,
    output_model: Path,
    command: str | Iterable[str],
) -> ModelOptimizationPlan:
    """Plan a local model distillation workflow."""

    return ModelOptimizationPlan(
        source_model=source_model,
        output_model=output_model,
        operation="distill",
        command=tuple(_split_command(command)),
        teacher_model=teacher_model,
    )


def run_model_optimization(plan: ModelOptimizationPlan) -> ModelOptimizationResult:
    """Run a planned optimization command and return output metadata."""

    if not plan.source_model.exists():
        raise ValueError(f"Source model does not exist: {plan.source_model}")
    if plan.teacher_model is not None and not plan.teacher_model.exists():
        raise ValueError(f"Teacher model does not exist: {plan.teacher_model}")
    plan.output_model.parent.mkdir(parents=True, exist_ok=True)
    command = _command_with_args(plan)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Model optimization failed: {result.stderr.strip()}")
    if not plan.output_model.exists():
        raise RuntimeError(f"Model optimization did not create: {plan.output_model}")
    return ModelOptimizationResult(
        output_model=plan.output_model,
        sha256=_sha256(plan.output_model),
        command=tuple(command),
    )


def _command_with_args(plan: ModelOptimizationPlan) -> list[str]:
    command = [
        *plan.command,
        "--operation",
        plan.operation,
        "--input",
        str(plan.source_model),
        "--output",
        str(plan.output_model),
    ]
    if plan.target_sparsity is not None:
        command.extend(["--target-sparsity", f"{plan.target_sparsity:g}"])
    if plan.teacher_model is not None:
        command.extend(["--teacher", str(plan.teacher_model)])
    return command


def _split_command(command: str | Iterable[str]) -> list[str]:
    if isinstance(command, str):
        parts = [part for part in command.split(" ") if part]
    else:
        parts = list(command)
    if not parts:
        raise ValueError("Optimization command must not be empty.")
    return parts
