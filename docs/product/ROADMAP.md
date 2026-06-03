# Project Roadmap

This document outlines the milestones, priorities, and long-term plans for `silukman_video_enhancer`.

---

## Development Phases

```
┌────────────────────────────────────────────────────────┐
│              Phase 1: Core Engine & CLI                │
│         - Video demux/mux pipeline via FFmpeg          │
│         - Basic ONNX models (Real-ESRGAN, Denoise)     │
│         - Audio preservation & sync                    │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│             Phase 2: Temporal & Quality                │
│         - Multi-frame temporal consistency checks      │
│         - Advanced denoise and deblur models           │
│         - Batch processing capabilities in CLI         │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│      Phase 3: Python Desktop UI & Local Distribution   │
│         - Desktop interface (PySide6 / Qt)             │
│         - Real-time side-by-side preview panel         │
│         - Self-contained offline installer builds       │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│     Phase 4: Production Release & Advanced Opt         │
│         - Release-grade offline installer packages     │
│         - Local LAN nodes rendering coordinator        │
│         - Subtitle OCR & offline RIFE interpolation   │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│     Phase 5: Advanced Media & Runtime Expansion        │
│         - Vulkan/WebGPU, OpenVINO & QNN support        │
│         - 10-bit HDR, 3D LUT, and SDR/HDR tone-mapping │
│         - Distillation, pruning & package formats      │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│            Phase 6: Headless API & Operations          │
│         - Standalone REST API server with OpenAPI      │
│         - Auth, rate limiting & local access control   │
│         - Durable queue, workers & LAN node discovery  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│       Phase 7: Ecosystem Governance & Lifecycle        │
│         - Plugin SDK, sandboxing & permission models   │
│         - Reusable recipes & automation profiles       │
│         - Backup, audit logs & offline update manager  │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│          Phase 8: Desktop UX & Batch Processing        │
│         - Multi-file desktop queue and batch worker     │
│         - Persistent desktop settings and recent files  │
│         - Per-file retry, ETA, and output actions       │
└────────────────────────────────────────────────────────┘
```

---

## Detailed Milestones

### Phase 1: Core Engine & CLI [Completed]
*   [Completed] Build pipeline to stream video frames to/from FFmpeg subprocesses.
*   [Completed] Connect ONNX Runtime with execution providers (CPU, CUDA, DirectML, CoreML).
*   [Completed] Auto-tuning Hardware Benchmarker (startup warmup profiling script).
*   [Completed] Model registry SHA256 integrity verification.
*   [Completed] Decoupled Streaming Audio-Video Muxer pipeline.
*   [Completed] Perceptual Audio Restoration Pipeline (FFmpeg FFT denoiser integration).
*   [Completed] Automated Bitrate Calibration (short-duration spatial complexity scans).
*   [Completed] Implement a single-model upscaler (e.g., Real-ESRGAN-x2 / x4).
*   [Completed] Non-blocking CLI Progress Monitor Dashboard.
*   [Completed] Automatic Frame Padding & Cropping (reflective margins for ONNX compatibility).
*   [Completed] Metadata Preservation pipeline (subtitles, chapters, and camera tags).
*   [Completed] Create standard CLI controls (`--input`, `--output`, `--scale`, `--device`).
*   [Completed] Dynamic Resource Governor (throttling `--quiet` mode to prevent system overheating).

### Phase 2: Temporal Consistency & Advanced Filtering [Completed]
*   [Completed] Implement basic temporal consistency checks and Scene Cut Detection to reduce frame flickering.
*   [Completed] Intelligent Frame Skip (temporal de-duplication based on frame SSIM delta).
*   [Completed] Custom ONNX Model Hot-Swapping (auto-scan for drop-in community models).
*   [Completed] Face Restoration Pipeline (GFPGAN/CodeFormer ONNX integration).
*   [Completed] Dynamic Spatial-Temporal Super-Resolution scaling.
*   [Completed] Multi-destination Video Encoding (selective time range processing & stream copy).
*   [Completed] Async GPU Double Buffering & Thread-Pool Post-Processing.
*   [Completed] Automated VRAM/RAM Limit Detection & Auto-Tiling Factor config.
*   [Completed] Integrate a Pause and Resume Checkpoint System with **ZSTD/LZ4 Lossless Caching** to save disk space.
*   [Completed] Multi-Model Chaining interface for sequential pipelines.
*   [Completed] Region of Interest (ROI) selective processing options.
*   [Completed] Multi-GPU & Distributed Local Pipeline support.
*   [Completed] Add denoise models (e.g., SwinIR-Lightweight) and compression artifact cleanup.
*   [Completed] Enable batch command operations (processing folder input files).
*   [Completed] Add support for FP16 quantization to increase inference speeds.

### Phase 3: Python Desktop UI & Packaging [Completed]
*   [Completed] Interactive HTML Comparison Report Export.
*   [Completed] Visual Comparator GUI Tool (preview single-frame splits).
*   [Completed] Local WebUI Host Dashboard (FastAPI/Gradio visual dashboard).
*   [Completed] Local LAN Render Farm (distributed processing node network).
*   [Completed] Offline Model Encryption (IP Copy-Protection for models).
*   [Completed] Smart Power Governor & Low-Battery Management (auto-pause on low laptop battery).
*   [Completed] Intelligent Hardware Thermal Throttling Monitor (auto-insertion of delay on high temperature).
*   [Completed] Automated Subtitle OCR and Translation.
*   [Completed] Visual Artifact Anomaly Detector (corrupted frame checks).
*   [Completed] Desktop Notification System (toasts on job finish).
*   [Completed] Intelligent Scene-based Model Selection (dynamic switching of models based on scene classification).
*   [Completed] Local Frame Interpolation (RIFE) for FPS boosting and high-quality Slow-Motion.
*   [Completed] Build a user-friendly Python desktop GUI with PySide6/Qt.
*   [Completed] Develop a media player showing side-by-side visual comparisons (Original vs. Enhanced).
*   [Completed] Setup PyInstaller workflows to output offline `.exe`, `.dmg`, and `.deb` installers.

### Phase 4: Production Release & Advanced Optimization [Completed]
*   [Completed] Build a release-grade installer pipeline for Windows, macOS, and Linux (.exe, .dmg, .deb).
*   [Completed] Add first-run model setup and offline model import workflows.
*   [Completed] Add production QA automation for packaged builds.
*   [Completed] Add desktop job cancellation, pause/resume controls, and notification integration.
*   [Completed] Add WebUI job submission and queue management.
*   [Completed] Define and implement a stable LAN render node protocol.
*   [Completed] Add render farm result merge and failure recovery.
*   [Completed] Add a benchmark dataset runner for PSNR, SSIM, VMAF, and visual artifact scoring.
*   [Completed] Wire RIFE/AI frame interpolation into the main enhancement runner as an optional output stage.
*   [Completed] Integrate real OCR and translation engines for subtitle workflows.
*   [Completed] INT8 Model Quantization support for CPU/NPU execution providers.
*   [Completed] Distributed LAN Transcoding and adaptive frame merging.
*   [Completed] Local-first Encrypted Sync for user configuration presets.
*   [Completed] Visual Video Timeline Crop Preview for transition monitoring.

### Phase 5: Advanced Media & Runtime Expansion [Completed]
*   [Completed] Vulkan API & WebGPU execution provider support for broad GPU compatibility.
*   [Completed] OpenVINO and QNN execution provider support for Intel and Qualcomm NPU acceleration.
*   [Completed] 3D LUT lookup tables (.cube) support for advanced local color grading.
*   [Completed] HDR, 10-bit, and wide-gamut color pipeline support for BT.2020/PQ/HLG workflows.
*   [Completed] SDR/HDR tone-mapping presets for controlled color-space conversion.
*   [Completed] Professional codec and delivery presets for AV1, ProRes, DNxHR, HEVC 10-bit, and archival mezzanine exports.
*   [Completed] Hardware encoder auto-profiling for NVENC, QSV, AMF, and VideoToolbox.
*   [Completed] High-resolution tiled render planning for 8K/16K output workflows.
*   [Completed] Model distillation and pruning script helper tools for custom user models.
*   [Completed] Advanced model metadata validation for custom ONNX compatibility, tensor shapes, opsets, and scale factors.
*   [Completed] Versioned local model package format for optimized ONNX bundles and sidecar metadata.

### Phase 6: Headless API & Operations [Completed]
*   [Completed] Standalone REST API server mode for pipeline orchestration.
*   [Completed] OpenAPI schema export and local client tooling for CLI/script integrations.
*   [Completed] REST API authentication, rate limits, and local network access controls for shared workstations.
*   [Completed] Durable job queue storage for headless restart recovery.
*   [Completed] Headless worker pool with configurable concurrency, device affinity, and queue priorities.
*   [Completed] Retry, timeout, and backoff policies for failed API and render-node jobs.
*   [Completed] Graceful shutdown and drain mode for long-running render services.
*   [Completed] LAN node discovery and capability advertisement for local render services.
*   [Completed] Health, readiness, and diagnostics endpoints for local service supervision.
*   [Completed] Live job log streaming and progress event replay for disconnected clients.
*   [Completed] Disk quota and temporary workspace cleanup controls for headless deployments.
*   [Completed] Service profile configuration for localhost-only, LAN-shared, and render-node modes.
*   [Completed] Local observability dashboard for render telemetry, hardware history, job logs, and quality trend tracking.
*   [Completed] Containerized headless deployment profile for Docker/Podman render nodes.

### Phase 7: Ecosystem Governance & Lifecycle [Completed]
*   [Completed] Plugin/extension SDK for custom model stages, FFmpeg filters, and export hooks.
*   [Completed] Plugin sandboxing and permission model for safe local extensions.
*   [Completed] Workflow automation profiles for reusable enhancement recipes and scheduled local jobs.
*   [Completed] Export artifact manifest generation for reproducible outputs, including settings, model hashes, metrics, and source media fingerprints.
*   [Completed] Configuration backup, restore, and migration tooling for presets, plugin settings, and server profiles.
*   [Completed] Local audit log for API requests, plugin actions, job lifecycle events, and permission changes.
*   [Completed] Cross-platform preset compatibility matrix tests for codecs, color formats, execution providers, and package targets.
*   [Completed] Offline update verification and model rollback manager to cryptographically sign, verify, and rollback offline updates.
*   [Completed] Local model signature verification and quarantine manager to inspect imported ONNX graphs against a whitelist of safe operators.
*   [Completed] Local hardware performance and runtime telemetry collector to bundle anonymized profile data for local debugging support.
*   [Completed] Database defragmentation and cache compaction utility to optimize local SQLite/JSON databases and prune temporary job workspaces.
*   [Completed] Offline SDK documentation and developer guide generator to build self-contained local API references from source code docstrings.

### Phase 8: Desktop UX & Batch Processing [Completed]
*   [Completed] Multi-file drag-and-drop support in the desktop UI.
*   [Completed] File queue table in the desktop UI with per-file status columns.
*   [Completed] Batch worker that processes a list of enhancement jobs sequentially with per-file progress emission and cancellation support.
*   [Completed] Auto output path derivation for batch jobs.
*   [Completed] Add/Remove file controls in the desktop queue.
*   [Completed] Per-file progress bar in the queue table.
*   [Completed] Cancel batch run support with current-job interruption.
*   [Completed] Settings persistence.
*   [Completed] Recent files list.
*   [Completed] ETA display.
*   [Completed] Post-job action buttons.
*   [Completed] Per-file error retry.
*   [Completed] Queue reordering.
*   [Completed] Output format selector.

### Phase 9: CI/CD & Cross-Platform Release Workflow [Completed]
*   [Completed] GitHub Actions CI workflow for Python 3.9, 3.10, and 3.11 across Ubuntu, macOS, and Windows.
*   [Completed] Windows release workflow for signed one-file PyInstaller executables with FFmpeg, ONNX Runtime, and PySide6 bundling.
*   [Completed] macOS release workflow for signed and notarized DMG generation with FFmpeg, ONNX Runtime, and PySide6 bundling.
*   [Completed] Linux release workflow for `.deb` and AppImage outputs.
*   [Completed] Code signing for Windows release artifacts.
*   [Completed] Code signing and notarization hardening for macOS release artifacts.
*   [Completed] Automated version tagging.
*   [Completed] GitHub Releases artifact upload.
*   [Completed] Build matrix smoke tests for packaged artifacts.
*   [Completed] Dependency caching in CI.

### Phase 10: GitHub Repository Presence [Completed]
*   [Completed] GitHub repository About metadata and discoverability topics.
*   [Completed] README social preview asset.
*   [Completed] Pinned README release, downloads, platform, and package badges.
*   [Completed] GitHub Releases draft publication workflow.
*   [Completed] Release tag convention and SemVer policy.
*   [Completed] GitHub Packages publish workflow.
*   [Completed] Release asset naming convention.
*   [Completed] GitHub issue templates and Discussions metadata.
*   [Completed] Security policy.
