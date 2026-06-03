# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] - 2026-06-02

### Added
*   **Face Restoration Pipeline**: Added heuristic face detection and crop/merge ROI routing within `FaceRestorer` processing.
*   **Dynamic Spatial-Temporal Scaling**: Implemented active upscaler scale adaptation per-frame via `spatiotemporal` planning and dynamic bilinear/nearest-neighbor resizing.
*   **Async GPU Double Buffering**: Integrated `DoubleBuffer` in the runner main loop to stage frame inputs asynchronously.
*   **Multi-GPU Round-Robin Pipeline**: Added `DistributedFrameProcessor` to partition and run frame workloads across multiple configured worker devices.
*   **Unit Tests**: Added integration tests for face restoration crop/merge, dynamic scale adapt, and multi-gpu round-robin processor.
*   **Checklist Status**: Completed and verified all Phase 2 checklist goals in `IMPLEMENTATION_CHECKLIST.md`.

### Fixed
*   **Linter/Import Error**: Fixed a `NameError` in `pipeline/upscaler.py` by properly importing `Sequence` from `typing`.

---

## [0.1.0] - 2026-05-29

### Added
*   **Core Video Pipeline**: Generator-based consumer-producer pipeline using raw RGB24 frames streamed through non-blocking FFmpeg subprocesses.
*   **ONNX Inference Engine**: Standalone ONNX Runtime driver with support for CUDA, DirectML, and CoreML execution providers.
*   **Metadata & Audio Preservation**: Automatic extraction and lossy/lossless audio copying back into enhanced containers.
*   **Resource Governor**: Throttling controls (`--quiet` / `--background` modes) to prevent thermal degradation.
*   **Model Management**: Cache directory structure and SHA256 integrity validator.
*   **CLI Interface**: Multi-model options, CRF quality factor selection, and batch directory enhancement pipelines.
*   **License & Contribution Rules**: Initialized `LICENSE` (MIT) and `CONTRIBUTING.md`.
