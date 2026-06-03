"""Graceful shutdown and drain mode controls."""

from __future__ import annotations

from dataclasses import dataclass

from app.job_store import save_job_queue
from app.jobs import JobQueue
from pathlib import Path


@dataclass
class ServiceState:
    accepting_jobs: bool = True
    draining: bool = False

    def enter_drain_mode(self) -> None:
        self.accepting_jobs = False
        self.draining = True

    def can_accept_jobs(self) -> bool:
        return self.accepting_jobs and not self.draining


def graceful_shutdown(queue: JobQueue, state_path: Path, service: ServiceState) -> Path:
    """Enter drain mode and persist current queue state."""

    service.enter_drain_mode()
    return save_job_queue(queue, state_path)
