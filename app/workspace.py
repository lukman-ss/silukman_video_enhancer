"""Disk quota and temporary workspace cleanup controls."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CleanupPlan:
    files: tuple[Path, ...]
    bytes_to_free: int


def plan_workspace_cleanup(
    workspace: Path,
    quota_bytes: int,
    active_paths: set[Path] | None = None,
    now: float | None = None,
    max_age_seconds: float | None = None,
) -> CleanupPlan:
    """Plan deletion of old inactive files until quota is satisfied."""

    active = {path.resolve() for path in (active_paths or set())}
    current_time = now if now is not None else time.time()
    files = [path for path in workspace.rglob("*") if path.is_file()]
    total = sum(path.stat().st_size for path in files)
    candidates = []
    for path in files:
        if path.resolve() in active:
            continue
        age = current_time - path.stat().st_mtime
        if max_age_seconds is None or age >= max_age_seconds:
            candidates.append(path)
    candidates.sort(key=lambda path: path.stat().st_mtime)
    selected = []
    freed = 0
    for path in candidates:
        if total - freed <= quota_bytes:
            break
        selected.append(path)
        freed += path.stat().st_size
    return CleanupPlan(files=tuple(selected), bytes_to_free=freed)


def apply_cleanup(plan: CleanupPlan) -> int:
    removed = 0
    for path in plan.files:
        if path.exists():
            removed += path.stat().st_size
            path.unlink()
    return removed
