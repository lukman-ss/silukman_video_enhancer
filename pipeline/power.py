"""Smart power governor and thermal throttling helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatteryState:
    percent: float
    plugged_in: bool


def should_pause_for_battery(state: BatteryState, threshold: float = 20.0) -> bool:
    return (not state.plugged_in) and state.percent <= threshold


@dataclass(frozen=True)
class ThermalState:
    temperature_c: float


def throttle_delay_seconds(state: ThermalState, threshold_c: float = 85.0) -> float:
    if state.temperature_c < threshold_c:
        return 0.0
    return min(1.0, (state.temperature_c - threshold_c + 1.0) * 0.1)
