"""Standalone local REST API server for headless operation."""

from __future__ import annotations

import json
import time
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import request

from app.config import EnhancementConfig
from app.jobs import JobQueue
from models.setup import inspect_model_setup
from pipeline.audit_log import AuditLog
from pipeline.telemetry_collector import TelemetryCollector
from utils.ffmpeg import FFmpegNotFoundError, require_binary


@dataclass(frozen=True)
class RestApiConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    token: str | None = None
    rate_limit_per_minute: int = 60
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "::1")

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class RateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self.limit = limit_per_minute
        self._hits: dict[str, list[float]] = {}

    def allow(self, client: str, now: float | None = None) -> bool:
        current = now if now is not None else time.time()
        window_start = current - 60
        hits = [hit for hit in self._hits.get(client, []) if hit >= window_start]
        if len(hits) >= self.limit:
            self._hits[client] = hits
            return False
        hits.append(current)
        self._hits[client] = hits
        return True


class RestApiServer:
    def __init__(
        self,
        config: RestApiConfig,
        jobs: JobQueue | None = None,
        audit_log: AuditLog | None = None,
        telemetry: TelemetryCollector | None = None,
    ) -> None:
        self.config = config
        self.audit_log = audit_log
        self.telemetry = telemetry
        self.jobs = jobs or JobQueue(audit_log=audit_log)
        if audit_log is not None and getattr(self.jobs, "audit_log", None) is None:
            self.jobs.audit_log = audit_log
        self.rate_limiter = RateLimiter(config.rate_limit_per_minute)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        handler = self._make_handler(
            self.config,
            self.jobs,
            self.rate_limiter,
            self.audit_log,
            self.telemetry,
        )
        self._server = ThreadingHTTPServer((self.config.host, self.config.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.config.url

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None

    @staticmethod
    def _make_handler(
        config: RestApiConfig,
        jobs: JobQueue,
        limiter: RateLimiter,
        audit_log: AuditLog | None = None,
        telemetry: TelemetryCollector | None = None,
    ):
        class RestHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if not self._authorized():
                    return
                if self.path == "/health":
                    self._audit(status=200)
                    self._write_json(api_health())
                elif self.path == "/ready":
                    self._audit(status=200)
                    self._write_json(api_readiness(jobs))
                elif self.path == "/diagnostics":
                    self._audit(status=200)
                    self._write_json(api_diagnostics(jobs))
                elif self.path == "/openapi.json":
                    self._audit(status=200)
                    self._write_json(openapi_schema(config))
                elif self.path == "/jobs":
                    self._audit(status=200)
                    self._write_json({"jobs": [job.to_payload() for job in jobs.list()]})
                elif self.path.startswith("/jobs/"):
                    job_id = self.path.split("/")[2]
                    match = [job for job in jobs.list() if job.id == job_id]
                    status = 200 if match else 404
                    self._audit(status=status, job_id=job_id if match else None)
                    self._write_json(match[0].to_payload() if match else {"error": "not found"}, status=status)
                else:
                    self._audit(status=404)
                    self.send_error(404)

            def do_POST(self) -> None:  # noqa: N802
                if not self._authorized():
                    return
                if self.path == "/jobs":
                    job = jobs.submit(_config_from_payload(self._read_json()))
                    self._audit(status=201, job_id=job.id)
                    self._telemetry(job.id, job.config, "queued")
                    self._write_json(job.to_payload(), status=201)
                elif self.path.startswith("/jobs/") and self.path.endswith("/cancel"):
                    job_id = self.path.split("/")[2]
                    cancelled = jobs.cancel(job_id)
                    self._audit(status=200, job_id=job_id)
                    self._telemetry(job_id, cancelled.config, "cancelled")
                    self._write_json(cancelled.to_payload())
                else:
                    self._audit(status=404)
                    self.send_error(404)

            def log_message(self, format: str, *args) -> None:  # noqa: A002
                return

            def _authorized(self) -> bool:
                client = self.client_address[0]
                if config.allowed_hosts and client not in config.allowed_hosts:
                    self._audit(status=403)
                    self._write_json({"error": "host not allowed"}, status=403)
                    return False
                if not limiter.allow(client):
                    self._audit(status=429)
                    self._write_json({"error": "rate limit exceeded"}, status=429)
                    return False
                if config.token:
                    expected = f"Bearer {config.token}"
                    if self.headers.get("Authorization") != expected:
                        self._audit(status=401)
                        self._write_json({"error": "unauthorized"}, status=401)
                        return False
                return True

            def _audit(self, status: int, job_id: str | None = None) -> None:
                if audit_log is None:
                    return
                audit_log.log_api(
                    endpoint=self.path,
                    method=self.command,
                    status=status,
                )
                if job_id is not None:
                    audit_log.record(
                        "api.request",
                        actor="api",
                        job_id=job_id,
                        detail={"endpoint": self.path, "method": self.command, "status": status},
                    )

            def _telemetry(self, job_id: str, config_obj: EnhancementConfig, status: str) -> None:
                if telemetry is None:
                    return
                telemetry.record(
                    job_id,
                    provider=config_obj.device,
                    fps=0.0,
                    status=status,
                    input_path=str(config_obj.input_path),
                    output_path=str(config_obj.output_path),
                )

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    return {}
                return json.loads(self.rfile.read(length).decode("utf-8"))

            def _write_json(self, payload: dict[str, Any], status: int = 200) -> None:
                body = json.dumps(payload, sort_keys=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

        return RestHandler


def openapi_schema(config: RestApiConfig) -> dict[str, Any]:
    return {
        "openapi": "3.0.0",
        "info": {"title": "silukman video enhancer local API", "version": "0.1.0"},
        "servers": [{"url": config.url}],
        "paths": {
            "/jobs": {"get": {"summary": "List jobs"}, "post": {"summary": "Submit job"}},
            "/jobs/{job_id}": {"get": {"summary": "Inspect job"}},
            "/jobs/{job_id}/cancel": {"post": {"summary": "Cancel job"}},
            "/health": {"get": {"summary": "Health check"}},
            "/ready": {"get": {"summary": "Readiness check"}},
            "/diagnostics": {"get": {"summary": "Diagnostics"}},
        },
    }


class RestApiClient:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def submit_job(self, config: EnhancementConfig) -> dict[str, Any]:
        return self._post("/jobs", _payload_from_config(config))

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._get(f"/jobs/{job_id}")

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return self._post(f"/jobs/{job_id}/cancel", {})

    def _get(self, path: str) -> dict[str, Any]:
        req = request.Request(f"{self.base_url}{path}", headers=self._headers())
        with request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={**self._headers(), "Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))

    def _headers(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}


def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "rest-api"}


def api_readiness(jobs: JobQueue) -> dict[str, Any]:
    return {"ready": True, "queued_jobs": len([job for job in jobs.list() if job.status == "queued"])}


def api_diagnostics(jobs: JobQueue) -> dict[str, Any]:
    try:
        ffmpeg = require_binary("ffmpeg")
        ffmpeg_status = "available"
    except FFmpegNotFoundError:
        ffmpeg = ""
        ffmpeg_status = "missing"
    setup = inspect_model_setup()
    return {
        "ffmpeg": {"status": ffmpeg_status, "path": ffmpeg},
        "models": {"ready": setup.ready, "missing": list(setup.missing_models)},
        "jobs": {"total": len(jobs.list())},
    }


def _payload_from_config(config: EnhancementConfig) -> dict[str, Any]:
    return {
        "input_path": str(config.input_path),
        "output_path": str(config.output_path),
        "model": config.model,
        "scale": config.scale,
        "device": config.device,
        "crf": config.crf,
    }


def _config_from_payload(payload: dict[str, Any]) -> EnhancementConfig:
    return EnhancementConfig(
        input_path=Path(payload["input_path"]),
        output_path=Path(payload["output_path"]),
        model=payload.get("model", "realesrgan"),
        scale=int(payload.get("scale", 2)),
        device=payload.get("device", "auto"),
        crf=int(payload.get("crf", 18)),
    )
