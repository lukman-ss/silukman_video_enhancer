"""Tests for REST API server, rate limiting, service controls, event logging, and observability telemetry."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.api import (
    RateLimiter,
    RestApiClient,
    RestApiConfig,
    RestApiServer,
    api_diagnostics,
    api_readiness,
    openapi_schema,
)
from app.config import EnhancementConfig
from app.discovery import NodeAdvertisement, compatible_nodes, decode_advertisement, encode_advertisement
from app.events import EventLog
from app.job_store import load_job_queue, save_job_queue
from app.jobs import JobQueue
from app.observability import TelemetryRecord, TelemetryStore
from app.service_control import ServiceState, graceful_shutdown
from app.service_profiles import get_service_profile
from app.worker_pool import RetryPolicy, WorkerPoolConfig, WorkerProfile, assign_worker_jobs, run_with_retry
from app.workspace import apply_cleanup, plan_workspace_cleanup
from pipeline.audit_log import AuditLog, EVENT_API_REQUEST, EVENT_JOB_QUEUED
from pipeline.telemetry_collector import TelemetryCollector
from tools.container_profile import ContainerProfile, render_containerfile


class ApiSchemaAndSecurityTests(unittest.TestCase):
    def test_openapi_schema_documents_jobs_and_health(self) -> None:
        schema = openapi_schema(RestApiConfig(port=9000))

        self.assertIn("/jobs", schema["paths"])
        self.assertIn("/health", schema["paths"])
        self.assertEqual(schema["servers"][0]["url"], "http://127.0.0.1:9000")

    def test_rate_limiter_rejects_after_limit(self) -> None:
        limiter = RateLimiter(2)

        self.assertTrue(limiter.allow("127.0.0.1", now=1))
        self.assertTrue(limiter.allow("127.0.0.1", now=2))
        self.assertFalse(limiter.allow("127.0.0.1", now=3))


class DurableQueueTests(unittest.TestCase):
    def test_job_queue_persists_and_recovers_running_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = JobQueue()
            job = queue.submit(EnhancementConfig(Path("in.mp4"), Path("out.mp4")))
            queue.update(job.id, status="running", progress=25)
            path = save_job_queue(queue, Path(temp_dir) / "jobs.json")

            recovered = load_job_queue(path)
            recovered_job = recovered.list()[0]

            self.assertEqual(recovered_job.status, "queued")
            self.assertEqual(recovered_job.progress, 25)
            self.assertEqual(recovered_job.message, "recovered after restart")


class DiagnosticsTests(unittest.TestCase):
    @mock.patch("app.api.inspect_model_setup")
    @mock.patch("app.api.require_binary", return_value="/usr/bin/ffmpeg")
    def test_diagnostics_reports_ffmpeg_models_and_jobs(self, _ffmpeg, setup) -> None:
        queue = JobQueue()
        queue.submit(EnhancementConfig(Path("in.mp4"), Path("out.mp4")))
        setup.return_value = mock.Mock(ready=True, missing_models=())

        diagnostics = api_diagnostics(queue)
        readiness = api_readiness(queue)

        self.assertEqual(diagnostics["ffmpeg"]["status"], "available")
        self.assertEqual(diagnostics["jobs"]["total"], 1)
        self.assertEqual(readiness["queued_jobs"], 1)


class RestApiServerTests(unittest.TestCase):
    def test_rest_api_server_client_submit_get_cancel(self) -> None:
        server = RestApiServer(
            RestApiConfig(port=0, token="secret", rate_limit_per_minute=100),
            jobs=JobQueue(),
        )
        url = server.start()
        try:
            port = server._server.server_address[1]
            client = RestApiClient(f"http://127.0.0.1:{port}", token="secret")
            submitted = client.submit_job(EnhancementConfig(Path("in.mp4"), Path("out.mp4")))
            fetched = client.get_job(submitted["id"])
            cancelled = client.cancel_job(submitted["id"])
        finally:
            server.stop()

        self.assertEqual(fetched["id"], submitted["id"])
        self.assertEqual(cancelled["status"], "cancelled")

    def test_rest_api_and_queue_write_audit_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            audit = AuditLog(Path(temp_dir) / "audit.ndjson")
            server = RestApiServer(
                RestApiConfig(port=0, token="secret", rate_limit_per_minute=100),
                jobs=JobQueue(),
                audit_log=audit,
            )
            url = server.start()
            try:
                port = server._server.server_address[1]
                client = RestApiClient(f"http://127.0.0.1:{port}", token="secret")
                submitted = client.submit_job(EnhancementConfig(Path("secret-in.mp4"), Path("secret-out.mp4")))
            finally:
                server.stop()

            entries = audit.all_entries()
            self.assertTrue(any(entry.event_type == EVENT_API_REQUEST for entry in entries))
            self.assertTrue(any(entry.event_type == EVENT_JOB_QUEUED for entry in entries))
            self.assertTrue(any(entry.job_id == submitted["id"] for entry in entries))
            self.assertFalse(any("input_path" in entry.detail for entry in entries))

    def test_rest_api_records_job_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            telemetry = TelemetryCollector(Path(temp_dir) / "telemetry.ndjson")
            server = RestApiServer(
                RestApiConfig(port=0, token="secret", rate_limit_per_minute=100),
                jobs=JobQueue(),
                telemetry=telemetry,
            )
            server.start()
            try:
                port = server._server.server_address[1]
                client = RestApiClient(f"http://127.0.0.1:{port}", token="secret")
                submitted = client.submit_job(EnhancementConfig(Path("in.mp4"), Path("out.mp4")))
            finally:
                server.stop()

            entries = telemetry.for_job(submitted["id"])
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].extra["status"], "queued")
            self.assertNotIn("input_path", entries[0].extra)


class WorkerAndShutdownTests(unittest.TestCase):
    def test_worker_pool_assigns_by_concurrency(self) -> None:
        queue = JobQueue()
        queue.submit(EnhancementConfig(Path("a.mp4"), Path("a-out.mp4")))
        queue.submit(EnhancementConfig(Path("b.mp4"), Path("b-out.mp4")))
        assignments = assign_worker_jobs(
            queue,
            WorkerPoolConfig(
                max_concurrency=1,
                workers=(WorkerProfile("gpu", "cuda", priority=10),),
            ),
        )

        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0].worker.name, "gpu")

    @mock.patch("app.worker_pool.time.sleep")
    def test_retry_policy_retries_operation(self, _sleep) -> None:
        calls = {"count": 0}

        def operation():
            calls["count"] += 1
            if calls["count"] < 2:
                raise RuntimeError("try again")
            return "ok"

        self.assertEqual(run_with_retry(operation, RetryPolicy(max_attempts=2)), "ok")

    def test_graceful_shutdown_enters_drain_and_saves_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = JobQueue()
            queue.submit(EnhancementConfig(Path("in.mp4"), Path("out.mp4")))
            service = ServiceState()
            path = graceful_shutdown(queue, Path(temp_dir) / "jobs.json", service)

            self.assertFalse(service.can_accept_jobs())
            self.assertTrue(path.exists())


class DiscoveryAndEventTests(unittest.TestCase):
    def test_lan_advertisement_round_trip_and_filters(self) -> None:
        ad = NodeAdvertisement("node", "127.0.0.1", 9000, ("CUDAExecutionProvider",), 2)
        decoded = decode_advertisement(encode_advertisement(ad))

        self.assertEqual(decoded.name, "node")
        self.assertEqual(compatible_nodes([decoded], "CUDAExecutionProvider"), [decoded])

    def test_event_log_replays_after_id_and_formats_sse(self) -> None:
        log = EventLog()
        first = log.append("job-1", "progress", "10")
        second = log.append("job-1", "progress", "20")
        replay = log.replay_after(first.id)

        self.assertEqual(replay, [second])
        self.assertIn("event: progress", log.as_sse(replay))


class WorkspaceProfileObservabilityTests(unittest.TestCase):
    def test_workspace_cleanup_skips_active_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = root / "old.tmp"
            active = root / "active.tmp"
            old.write_bytes(b"x" * 10)
            active.write_bytes(b"x" * 10)
            plan = plan_workspace_cleanup(root, quota_bytes=5, active_paths={active})
            removed = apply_cleanup(plan)

            self.assertEqual(plan.files, (old,))
            self.assertEqual(removed, 10)
            self.assertTrue(active.exists())

    def test_service_profiles_define_modes(self) -> None:
        profile = get_service_profile("render-node")

        self.assertEqual(profile.bind_host, "0.0.0.0")
        self.assertTrue(profile.container_ready)

    def test_observability_dashboard_payload(self) -> None:
        store = TelemetryStore()
        store.append(TelemetryRecord("job-1", fps=24, provider="CPUExecutionProvider"))
        payload = store.dashboard_payload()

        self.assertEqual(payload["average_fps"], 24)
        self.assertEqual(payload["records"][0]["job_id"], "job-1")

    def test_container_profile_renders_ffmpeg_ready_containerfile(self) -> None:
        content = render_containerfile(ContainerProfile(service_port=9999))

        self.assertIn("ffmpeg", content)
        self.assertIn("EXPOSE 9999", content)


if __name__ == "__main__":
    unittest.main()
