"""Containerized headless deployment profile helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ContainerProfile:
    base_image: str = "python:3.11-slim"
    service_port: int = 8765
    entrypoint: str = "python -m app.api"


def render_containerfile(profile: ContainerProfile = ContainerProfile()) -> str:
    return "\n".join(
        [
            f"FROM {profile.base_image}",
            "RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*",
            "WORKDIR /app",
            "COPY . /app",
            "RUN pip install -e .",
            f"EXPOSE {profile.service_port}",
            f'CMD ["sh", "-lc", "{profile.entrypoint}"]',
            "",
        ]
    )


def write_containerfile(output_path: Path, profile: ContainerProfile = ContainerProfile()) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_containerfile(profile), encoding="utf-8")
    return output_path
