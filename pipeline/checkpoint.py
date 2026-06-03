"""Pause/resume checkpointing with lightweight lossless frame cache hooks."""

from __future__ import annotations

import json
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckpointState:
    input_path: str
    output_path: str
    last_processed_frame_index: int
    settings_hash: str


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.frames_dir = root / "frames"
        self.state_path = root / "state.json"

    def initialize(self) -> None:
        self.frames_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self, state: CheckpointState) -> None:
        self.initialize()
        self.state_path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")

    def load_state(self) -> CheckpointState | None:
        if not self.state_path.exists():
            return None
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        return CheckpointState(**payload)

    def save_frame(self, frame_index: int, frame: bytes) -> Path:
        self.initialize()
        path = self.frames_dir / f"{frame_index:012d}.zlib"
        path.write_bytes(zlib.compress(frame))
        return path

    def load_frame(self, frame_index: int) -> bytes:
        path = self.frames_dir / f"{frame_index:012d}.zlib"
        return zlib.decompress(path.read_bytes())
