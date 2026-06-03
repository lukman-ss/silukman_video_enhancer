"""Durable job queue storage for headless recovery."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.config import EnhancementConfig
from app.jobs import EnhancementJob, JobQueue


def save_job_queue(queue: JobQueue, path: Path) -> Path:
    """Persist queue state to disk as JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [job.to_payload() for job in queue.list()]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_job_queue(path: Path) -> JobQueue:
    """Load queue state from disk, preserving recoverable jobs."""

    queue = JobQueue()
    if not path.exists():
        return queue
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload:
        config = _config_from_payload(item["config"])
        job = queue.submit(config)
        status = "queued" if item.get("status") == "running" else item.get("status", "queued")
        message = "recovered after restart" if item.get("status") == "running" else item.get("message", "")
        queue.update(
            job.id,
            status=status,
            progress=int(item.get("progress", 0)),
            message=message,
        )
    return queue


def _config_from_payload(payload: dict) -> EnhancementConfig:
    return EnhancementConfig(
        input_path=Path(payload["input_path"]),
        output_path=Path(payload["output_path"]),
        model=payload.get("model", "realesrgan"),
        scale=int(payload.get("scale", 2)),
        device=payload.get("device", "auto"),
        crf=int(payload.get("crf", 18)),
        denoise=payload.get("denoise", "False") == "True",
        color_correct=payload.get("color_correct", "False") == "True",
    )
