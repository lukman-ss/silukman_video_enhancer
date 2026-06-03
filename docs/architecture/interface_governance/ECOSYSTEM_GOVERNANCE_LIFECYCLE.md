# Ecosystem Governance & Lifecycle

This document explains the Phase 7 ecosystem governance and lifecycle features. It complements [ARCHITECTURE.md](ARCHITECTURE.md), [MODELS_AND_INFERENCE.md](MODELS_AND_INFERENCE.md), [VERIFICATION_GUIDE.md](VERIFICATION_GUIDE.md), and [ROADMAP.md](ROADMAP.md).

---

## Scope

Phase 7 defines long-term features for the local-first application's extensibility, security, automation, maintenance, and compliance:

*   Plugin/extension SDK for custom stages, FFmpeg filters, and export hooks.
*   Plugin sandboxing and permission management.
*   Workflow automation profiles and job scheduling.
*   Reproducibility manifests for export verification.
*   Configuration migration and backup utilities.
*   Local security audits and access tracking.
*   Cross-platform preset validation.
*   Offline update signature verification and rollback managers.
*   ONNX node signature validation and quarantine environments.
*   Encrypted telemetry collector for offline debugging.
*   Database defragmentation and temporary cache compaction.
*   Self-contained developer guide and SDK document generator.

Phase 7 is currently **[Completed]**. Plugin SDK hooks, sandboxed plugin execution, scheduled workflow profile submission, render manifests, config backup/restore, audit logging, compatibility matrix reports, signed offline update verification, model quarantine, runtime telemetry, maintenance compaction, and offline SDK docs are implemented.

---

## Plugin SDK and Sandboxing

To allow users to extend the pipeline safely:
*   **Plugin SDK**: Exposes hooks for custom pre-processing/post-processing model stages, custom FFmpeg audio/video filters, and execution events.
*   **Sandboxing**: Enforces declared permissions in plugin manifests (e.g. read/write directories, execute FFmpeg, import model, network access).
*   **Isolation**: Ensures that third-party plugin scripts cannot execute unauthorized system calls without explicit user consent.

---

## Workflow Automation and Reproducibility

*   **Automation Profiles**: Allows saving recipes (e.g., specific combinations of upscalers, LUTs, bitrates, and audio filters) and scheduling them for deferred execution on the local machine.
*   **Reproducibility Manifest**: Every completed render writes a sidecar JSON metadata manifest containing the model hashes, settings, metrics, and source fingerprints to guarantee reproducible outputs.

---

## Configuration & Audit Management

*   **Backup & Migration**: Tools to package all user settings, presets, plugin states, and server profiles to a single portable file that can be migrated between versions.
*   **Local Audit Log**: Keeps a secure local log of job lifecycle changes, API authentication requests, and plugin operations for multi-user shared workstation configurations.

---

## Security & Maintenance Controls

*   **Offline Update & Rollback**: Verifies cryptographic signatures of manually downloaded update bundles and restores previous stable application states if updates fail.
*   **ONNX Operator Quarantine**: Automatically inspects imported custom community models for non-whitelisted layers or unsafe execution graphs.
*   **Telemetry and Compaction**: Collects anonymized execution and crash stats in a local bundle, while automatically scheduling SQLite database vaccuming and frame cache pruning to maintain storage limits.

---

## Developer Tools

*   **SDK Doc Generator**: An offline CLI generator that reads pipeline docstrings to generate self-contained HTML documentation for local extension developers.
*   **Cross-platform Matrix Tests**: Runs comprehensive automated test cases to validate that every codec and execution provider configuration functions identically across Windows, macOS, and Linux.

---

## Verification

Phase 7 behavior is covered by active unit tests for plugin runtime/sandboxing, workflow scheduling, render manifests, config backup/restore, audit logging, compatibility reports, signed update verification, model quarantine, telemetry, maintenance compaction, and SDK doc generation.

```bash
python3 -m unittest
```
