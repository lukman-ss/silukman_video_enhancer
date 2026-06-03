"""Multi-GPU and local distributed planning helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass(frozen=True)
class WorkerDevice:
    name: str
    provider: str


@dataclass(frozen=True)
class FrameAssignment:
    frame_index: int
    device: WorkerDevice


def parse_worker_devices(value: str) -> List[WorkerDevice]:
    devices = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        if ":" in item:
            name, provider = item.split(":", 1)
        else:
            name, provider = item, item
        devices.append(WorkerDevice(name=name, provider=provider))
    if not devices:
        raise ValueError("At least one worker device is required.")
    return devices


def assign_frames_to_devices(frame_indices: Iterable[int], devices: List[WorkerDevice]) -> List[FrameAssignment]:
    if not devices:
        raise ValueError("At least one worker device is required.")
    return [
        FrameAssignment(frame_index=index, device=devices[position % len(devices)])
        for position, index in enumerate(frame_indices)
    ]
