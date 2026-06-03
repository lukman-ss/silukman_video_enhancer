# Headless API & Operations

This document explains the Phase 6 headless service features. It complements [ARCHITECTURE.md](ARCHITECTURE.md), [CLI_WORKFLOW.md](CLI_WORKFLOW.md), [LAN_RENDER_FARM.md](LAN_RENDER_FARM.md), and [ROADMAP.md](ROADMAP.md).

---

## Scope

Phase 6 turns the local enhancer into a service-oriented runtime while keeping the project local-first:

*   REST API server mode.
*   OpenAPI schema and local client tooling.
*   Authentication, rate limits, and host access controls.
*   Durable job queue recovery.
*   Worker pool assignment and retry policies.
*   Graceful service shutdown.
*   LAN discovery for local render nodes.
*   Health, readiness, and diagnostics endpoints.
*   Live event replay for clients.
*   Workspace cleanup and disk quota planning.
*   Service profiles for localhost, LAN-shared, and render-node modes.
*   Observability payloads and container profile generation.

Phase 6 does not add mandatory cloud execution. Services bind locally or to the LAN according to explicit configuration.

---

## API Server

The REST API exposes local job orchestration endpoints for:

*   Listing jobs.
*   Submitting jobs.
*   Inspecting one job.
*   Cancelling jobs.
*   Health checks.
*   Readiness checks.
*   Diagnostics.
*   OpenAPI schema export.

The API server uses the same shared job queue abstractions as the desktop UI and WebUI flows, keeping orchestration behavior consistent across interfaces.

---

## Security Controls

Headless mode supports local operational controls:

*   Bearer token authentication.
*   Allowed client host checks.
*   Per-client rate limiting.
*   Bind-address profiles for localhost-only and LAN-shared operation.

The default posture should remain conservative: expose only localhost unless the user explicitly opts into LAN sharing.

---

## Durable Queue Recovery

Durable queue storage persists job state to disk. On restart:

*   Completed and cancelled jobs remain historical records.
*   Running jobs are recovered as queued candidates.
*   Recovery messages make restart behavior explicit to users.

This avoids silently losing long-running headless job state.

---

## Worker Pool and Retry Policy

Worker pool planning supports:

*   Maximum concurrency.
*   Device/provider affinity labels.
*   Queue priorities.

Retry policies define:

*   Maximum attempts.
*   Backoff timing.
*   Terminal failure behavior.

These policies are especially important for render nodes and batch/headless runs where no user is watching the process continuously.

---

## Shutdown and Drain Mode

Graceful shutdown enters drain mode before exit:

*   New jobs are rejected.
*   Active work can finish or checkpoint.
*   Queue state is persisted.

Drain mode protects long-running render work from service restarts and package updates.

---

## LAN Discovery

Local render services can advertise:

*   Node name.
*   Host and port.
*   Available execution providers.
*   Capacity.

The coordinator can filter compatible nodes by provider capability without requiring manual host entry for every node.

---

## Diagnostics and Observability

Diagnostics report:

*   Service health.
*   Queue readiness.
*   FFmpeg availability.
*   Model cache readiness.
*   Missing models.
*   Recent failure summaries.

Observability payloads record per-job runtime telemetry such as FPS, provider, temperature, memory, errors, and quality metrics.

---

## Workspace Controls

Headless deployments need predictable storage behavior. Workspace planning supports:

*   Temporary workspace cleanup.
*   Disk quota enforcement.
*   Active artifact protection.
*   Expired workspace removal.

Cleanup must never delete active render artifacts.

---

## Container Profile

Container profile generation creates FFmpeg-ready Docker/Podman service definitions for render nodes. Container mode is intended for local or LAN headless deployment, not mandatory cloud execution.

---

## Verification

Phase 6 behavior is covered by `tests/test_phase6_completion.py`. Run:

```bash
python3 -m unittest tests.test_phase6_completion
```
