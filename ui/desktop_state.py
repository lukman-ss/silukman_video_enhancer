"""Desktop settings and recent-file persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class DesktopSettings:
    model: str = "realesrgan"
    scale: int = 2
    device: str = "auto"
    crf: int = 18
    denoise: bool = False
    color_correct: bool = False
    recent_files: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DesktopSettings":
        return cls(
            model=str(payload.get("model", "realesrgan")),
            scale=int(payload.get("scale", 2)),
            device=str(payload.get("device", "auto")),
            crf=int(payload.get("crf", 18)),
            denoise=bool(payload.get("denoise", False)),
            color_correct=bool(payload.get("color_correct", False)),
            recent_files=list(payload.get("recent_files", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DesktopSettingsStore:
    """JSON-backed settings store for the desktop app."""

    def __init__(self, path: Path, max_recent: int = 10) -> None:
        self.path = Path(path)
        self.max_recent = max_recent

    def load(self) -> DesktopSettings:
        if not self.path.exists():
            return DesktopSettings()
        try:
            return DesktopSettings.from_dict(json.loads(self.path.read_text("utf-8")))
        except Exception:
            return DesktopSettings()

    def save(self, settings: DesktopSettings) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
        return self.path

    def remember_files(self, paths: List[Path]) -> DesktopSettings:
        settings = self.load()
        recent: List[str] = []
        for path in [str(Path(p)) for p in paths] + settings.recent_files:
            if path not in recent:
                recent.append(path)
        settings.recent_files = recent[: self.max_recent]
        self.save(settings)
        return settings
