"""LAN node discovery and capability advertisements."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class NodeAdvertisement:
    name: str
    host: str
    port: int
    providers: tuple[str, ...]
    max_workers: int


def encode_advertisement(advertisement: NodeAdvertisement) -> bytes:
    return json.dumps(asdict(advertisement), sort_keys=True).encode("utf-8")


def decode_advertisement(payload: bytes) -> NodeAdvertisement:
    data = json.loads(payload.decode("utf-8"))
    return NodeAdvertisement(
        name=data["name"],
        host=data["host"],
        port=int(data["port"]),
        providers=tuple(data.get("providers", ())),
        max_workers=int(data.get("max_workers", 1)),
    )


def compatible_nodes(
    advertisements: list[NodeAdvertisement],
    required_provider: str | None = None,
) -> list[NodeAdvertisement]:
    if required_provider is None:
        return advertisements
    return [
        advertisement
        for advertisement in advertisements
        if required_provider in advertisement.providers
    ]
