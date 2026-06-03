"""LAN render node HTTP protocol."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass(frozen=True)
class RenderNodeCapabilities:
    name: str
    providers: tuple[str, ...]
    max_workers: int = 1


@dataclass(frozen=True)
class RenderNodeJob:
    id: str
    start_frame: int
    end_frame: int
    status: str = "queued"
    message: str = ""


class RenderNodeState:
    def __init__(self, capabilities: RenderNodeCapabilities) -> None:
        self.capabilities = capabilities
        self._lock = threading.Lock()
        self._jobs: dict[str, RenderNodeJob] = {}

    def health(self) -> dict[str, str]:
        return {"status": "ready", "name": self.capabilities.name}

    def submit(self, payload: dict[str, Any]) -> RenderNodeJob:
        job = RenderNodeJob(
            id=str(payload.get("job_id") or f"render-{len(self._jobs) + 1}"),
            start_frame=int(payload["start_frame"]),
            end_frame=int(payload["end_frame"]),
            status="queued",
            message="accepted",
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def cancel(self, job_id: str) -> RenderNodeJob:
        with self._lock:
            job = self._require_job(job_id)
            cancelled = RenderNodeJob(
                id=job.id,
                start_frame=job.start_frame,
                end_frame=job.end_frame,
                status="cancelled",
                message="cancelled",
            )
            self._jobs[job_id] = cancelled
            return cancelled

    def result(self, job_id: str) -> RenderNodeJob:
        with self._lock:
            return self._require_job(job_id)

    def _require_job(self, job_id: str) -> RenderNodeJob:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise ValueError(f"Unknown render job id: {job_id}") from exc


class RenderNodeServer:
    def __init__(self, host: str, port: int, state: RenderNodeState) -> None:
        self.host = host
        self.port = port
        self.state = state
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        handler = self._make_handler(self.state)
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return f"http://{self.host}:{self.port}"

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None

    @staticmethod
    def _make_handler(state: RenderNodeState):
        class RenderNodeHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._write_json(state.health())
                elif self.path == "/capabilities":
                    self._write_json(asdict(state.capabilities))
                elif self.path.startswith("/result/"):
                    self._write_json(asdict(state.result(self.path.split("/")[-1])))
                else:
                    self.send_error(404)

            def do_POST(self) -> None:  # noqa: N802
                if self.path == "/render":
                    self._write_json(asdict(state.submit(self._read_json())), status=202)
                elif self.path.startswith("/cancel/"):
                    self._write_json(asdict(state.cancel(self.path.split("/")[-1])))
                else:
                    self.send_error(404)

            def log_message(self, format: str, *args) -> None:  # noqa: A002
                return

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

        return RenderNodeHandler
