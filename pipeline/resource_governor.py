"""Dynamic resource governor for quiet/background processing."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceGovernor:
    quiet: bool = False
    delay_seconds: float = 0.015

    def throttle(self) -> None:
        if self.quiet:
            time.sleep(self.delay_seconds)
