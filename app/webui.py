"""Local WebUI dashboard host."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app.config import EnhancementConfig
from app.jobs import JobQueue


@dataclass(frozen=True)
class WebUIConfig:
    host: str = "127.0.0.1"
    port: int = 7860

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def dashboard_status(config: WebUIConfig) -> dict[str, str]:
    return {"status": "ready", "url": config.url}


class DashboardState:
    """Thread-safe dashboard state shared by the local WebUI server."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._payload: dict[str, Any] = {
            "status": "idle",
            "progress": 0,
            "message": "",
            "config": {},
        }

    def update(self, **fields: Any) -> None:
        with self._lock:
            self._payload.update(fields)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._payload)


class LocalDashboardServer:
    """Small offline dashboard server for job status and progress."""

    def __init__(
        self,
        config: WebUIConfig,
        state: DashboardState | None = None,
        jobs: JobQueue | None = None,
    ) -> None:
        self.config = config
        self.state = state or DashboardState()
        self.jobs = jobs or JobQueue()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        handler = self._make_handler(self.state, self.jobs)
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
    def _make_handler(state: DashboardState, jobs: JobQueue):
        class DashboardHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib API
                if self.path in {"/", "/index.html"}:
                    self._write_html()
                elif self.path == "/api/status":
                    self._write_json(state.snapshot())
                elif self.path == "/api/jobs":
                    self._write_json({"jobs": [job.to_payload() for job in jobs.list()]})
                else:
                    self.send_error(404)

            def do_POST(self) -> None:  # noqa: N802 - stdlib API
                if self.path == "/api/jobs":
                    payload = self._read_json()
                    job = jobs.submit(_config_from_payload(payload))
                    self._write_json(job.to_payload(), status=201)
                elif self.path.startswith("/api/jobs/") and self.path.endswith("/cancel"):
                    job_id = self.path.split("/")[3]
                    self._write_json(jobs.cancel(job_id).to_payload())
                elif self.path.startswith("/api/jobs/") and self.path.endswith("/pause"):
                    job_id = self.path.split("/")[3]
                    self._write_json(jobs.pause(job_id).to_payload())
                elif self.path.startswith("/api/jobs/") and self.path.endswith("/resume"):
                    job_id = self.path.split("/")[3]
                    self._write_json(jobs.resume(job_id).to_payload())
                else:
                    self.send_error(404)

            def log_message(self, format: str, *args) -> None:  # noqa: A002
                return

            def _write_html(self) -> None:
                body = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>silukman dashboard</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; color: #1f2937; }
    progress { width: 100%; height: 1.5rem; }
    pre { background: #f3f4f6; padding: 1rem; overflow: auto; }
  </style>
</head>
<body>
  <h1>silukman dashboard</h1>
  <progress id="progress" max="100" value="0"></progress>
  <p id="message"></p>
  <pre id="payload">{}</pre>
  <h2>Jobs</h2>
  <pre id="jobs">[]</pre>
  <script>
    async function refresh() {
      const response = await fetch("/api/status");
      const payload = await response.json();
      const jobsResponse = await fetch("/api/jobs");
      const jobs = await jobsResponse.json();
      document.getElementById("progress").value = payload.progress || 0;
      document.getElementById("message").textContent = payload.message || payload.status;
      document.getElementById("payload").textContent = JSON.stringify(payload, null, 2);
      document.getElementById("jobs").textContent = JSON.stringify(jobs.jobs, null, 2);
    }
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    return {}
                return json.loads(self.rfile.read(length).decode("utf-8"))

            def _write_json(self, payload: dict[str, Any], status: int = 200) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

        return DashboardHandler


def _config_from_payload(payload: dict[str, Any]) -> EnhancementConfig:
    return EnhancementConfig(
        input_path=Path(payload["input_path"]),
        output_path=Path(payload["output_path"]),
        model=payload.get("model", "realesrgan"),
        scale=int(payload.get("scale", 2)),
        device=payload.get("device", "auto"),
        crf=int(payload.get("crf", 18)),
        denoise=bool(payload.get("denoise", False)),
        color_correct=bool(payload.get("color_correct", False)),
    )
