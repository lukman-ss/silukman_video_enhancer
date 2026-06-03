"""Headless worker pool and retry policies."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.jobs import EnhancementJob, JobQueue


@dataclass(frozen=True)
class WorkerProfile:
    name: str
    device: str = "auto"
    priority: int = 0


@dataclass(frozen=True)
class WorkerPoolConfig:
    max_concurrency: int = 1
    workers: tuple[WorkerProfile, ...] = (WorkerProfile("default"),)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    timeout_seconds: float | None = None

    def delay_for_attempt(self, attempt: int) -> float:
        return self.base_delay_seconds * (2 ** max(0, attempt - 1))

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_attempts


@dataclass(frozen=True)
class WorkerAssignment:
    job: EnhancementJob
    worker: WorkerProfile


def assign_worker_jobs(queue: JobQueue, config: WorkerPoolConfig) -> list[WorkerAssignment]:
    """Assign queued jobs to workers by priority and concurrency limit."""

    queued = [job for job in queue.list() if job.status == "queued"]
    queued.sort(key=lambda job: job.config.device)
    workers = sorted(config.workers, key=lambda worker: worker.priority, reverse=True)
    assignments = []
    for job, worker in zip(queued[: config.max_concurrency], workers):
        assignments.append(WorkerAssignment(job=job, worker=worker))
    return assignments


def run_with_retry(operation, policy: RetryPolicy):
    """Run an operation with retry/backoff and optional timeout accounting."""

    started = time.monotonic()
    attempt = 1
    while True:
        try:
            return operation()
        except Exception:
            if not policy.should_retry(attempt):
                raise
            if policy.timeout_seconds is not None:
                elapsed = time.monotonic() - started
                if elapsed + policy.delay_for_attempt(attempt) > policy.timeout_seconds:
                    raise TimeoutError("retry policy timeout exceeded")
            time.sleep(policy.delay_for_attempt(attempt))
            attempt += 1
