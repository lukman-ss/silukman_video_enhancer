"""Local job queue state for WebUI and desktop integrations."""

from __future__ import annotations

import itertools
import threading
from dataclasses import asdict, dataclass
from typing import Literal

from app.config import EnhancementConfig
from app.notifications import Notification, send_notification
from pipeline.audit_log import AuditLog, EVENT_JOB_COMPLETED, EVENT_JOB_FAILED, EVENT_JOB_QUEUED, EVENT_JOB_STARTED


JobStatus = Literal["queued", "running", "paused", "completed", "failed", "cancelled"]


@dataclass(frozen=True)
class EnhancementJob:
    id: str
    config: EnhancementConfig
    status: JobStatus = "queued"
    progress: int = 0
    message: str = ""

    def to_payload(self) -> dict:
        payload = asdict(self)
        payload["config"] = {
            key: str(value)
            for key, value in asdict(self.config).items()
        }
        return payload


class JobQueue:
    """In-memory FIFO job queue with progress tracking."""

    def __init__(self, audit_log: AuditLog | None = None) -> None:
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._jobs: dict[str, EnhancementJob] = {}
        self._order: list[str] = []
        self.audit_log = audit_log

    def submit(self, config: EnhancementConfig) -> EnhancementJob:
        with self._lock:
            job = EnhancementJob(id=f"job-{next(self._ids)}", config=config)
            self._jobs[job.id] = job
            self._order.append(job.id)
            if self.audit_log is not None:
                self.audit_log.record(
                    EVENT_JOB_QUEUED,
                    actor="job-queue",
                    job_id=job.id,
                    detail={"model": config.model, "scale": config.scale},
                )
            return job

    def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        progress: int | None = None,
        message: str | None = None,
    ) -> EnhancementJob:
        with self._lock:
            job = self._require_job(job_id)
            updated = EnhancementJob(
                id=job.id,
                config=job.config,
                status=status or job.status,
                progress=job.progress if progress is None else min(100, max(0, progress)),
                message=job.message if message is None else message,
            )
            self._jobs[job_id] = updated
            if self.audit_log is not None and status == "running":
                self.audit_log.record(EVENT_JOB_STARTED, actor="job-queue", job_id=job_id)
            return updated

    def cancel(self, job_id: str) -> EnhancementJob:
        return self.update(job_id, status="cancelled", message="cancelled by user")

    def pause(self, job_id: str) -> EnhancementJob:
        return self.update(job_id, status="paused", message="paused by user")

    def resume(self, job_id: str) -> EnhancementJob:
        return self.update(job_id, status="queued", message="resumed from pause")

    def complete(self, job_id: str, message: str = "completed") -> EnhancementJob:
        job = self.update(job_id, status="completed", progress=100, message=message)
        if self.audit_log is not None:
            self.audit_log.record(
                EVENT_JOB_COMPLETED,
                actor="job-queue",
                job_id=job_id,
                detail={"message": message},
            )
        send_notification(Notification("Enhancement complete", message))
        return job

    def fail(self, job_id: str, message: str) -> EnhancementJob:
        job = self.update(job_id, status="failed", message=message)
        if self.audit_log is not None:
            self.audit_log.record(
                EVENT_JOB_FAILED,
                actor="job-queue",
                job_id=job_id,
                detail={"message": message},
            )
        send_notification(Notification("Enhancement failed", message))
        return job

    def next_queued(self) -> EnhancementJob | None:
        with self._lock:
            for job_id in self._order:
                job = self._jobs[job_id]
                if job.status == "queued":
                    return job
        return None

    def list(self) -> list[EnhancementJob]:
        with self._lock:
            return [self._jobs[job_id] for job_id in self._order]

    def _require_job(self, job_id: str) -> EnhancementJob:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise ValueError(f"Unknown job id: {job_id}") from exc
