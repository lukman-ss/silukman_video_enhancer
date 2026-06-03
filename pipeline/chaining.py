"""Multi-model chaining helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List


FrameProcessor = Callable[[bytes], bytes]


@dataclass(frozen=True)
class ModelChainStep:
    name: str
    processor: FrameProcessor


class ModelChain:
    """Sequential in-memory frame processing chain."""

    def __init__(self, steps: Iterable[ModelChainStep]) -> None:
        self.steps: List[ModelChainStep] = list(steps)

    def process(self, frame: bytes) -> bytes:
        output = frame
        for step in self.steps:
            output = step.processor(output)
        return output

    @property
    def names(self) -> list[str]:
        return [step.name for step in self.steps]


def parse_model_chain(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]
