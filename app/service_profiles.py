"""Service profile configuration for headless modes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceProfile:
    name: str
    bind_host: str
    token_required: bool
    max_workers: int
    discovery_enabled: bool
    container_ready: bool = False


SERVICE_PROFILES = {
    "localhost": ServiceProfile("localhost", "127.0.0.1", False, 1, False),
    "lan-shared": ServiceProfile("lan-shared", "0.0.0.0", True, 2, True),
    "render-node": ServiceProfile("render-node", "0.0.0.0", True, 1, True, True),
}


def get_service_profile(name: str) -> ServiceProfile:
    try:
        return SERVICE_PROFILES[name]
    except KeyError as exc:
        available = ", ".join(sorted(SERVICE_PROFILES))
        raise ValueError(f"Unknown service profile `{name}`. Available: {available}") from exc
