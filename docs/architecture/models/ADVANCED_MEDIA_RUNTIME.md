# Advanced Media & Runtime

This document explains the Phase 5 advanced media and runtime features. It complements [MODELS_AND_INFERENCE.md](MODELS_AND_INFERENCE.md), [VIDEO_PIPELINE.md](VIDEO_PIPELINE.md), and [ROADMAP.md](ROADMAP.md).

---

## Scope

Phase 5 focuses on local media-engine and runtime expansion:

*   Broader ONNX Runtime provider planning.
*   Advanced color and HDR workflows.
*   Professional delivery preset planning.
*   Hardware encoder profiling.
*   High-resolution tile planning.
*   Local model optimization, validation, and packaging.

It does not include REST services, plugin governance, automation scheduling, or operational lifecycle tools. Those belong to Phase 6 and Phase 7.

---

## Runtime Provider Expansion

The runtime layer supports provider planning beyond the baseline CPU/CUDA/CoreML/DirectML path:

*   Vulkan and WebGPU provider names are accepted for experimental planning.
*   OpenVINO and QNN provider planning supports Intel and Qualcomm acceleration paths.
*   Provider selection must always retain a safe CPU fallback when an accelerator is unavailable.

Provider planning should be treated as capability-aware configuration, not a guarantee that every provider exists on every machine.

---

## Color and HDR Pipeline

The media pipeline includes planning helpers for:

*   `.cube` 3D LUT parsing and FFmpeg `lut3d` filter generation.
*   HDR output metadata for BT.2020, PQ, and HLG workflows.
*   10-bit pixel format planning for compatible delivery paths.
*   SDR-to-HDR, HDR-to-SDR, and HDR passthrough tone-map filters.

The pipeline should preserve metadata when requested and avoid implicit destructive color conversions.

---

## Professional Delivery Presets

Delivery presets generate FFmpeg argument sets for common advanced outputs:

*   AV1.
*   HEVC 10-bit.
*   ProRes.
*   DNxHR.
*   Archival FFV1.

Presets are command planners. They should produce validated argument lists and leave execution to pipeline or CLI code.

---

## Encoder Profiling

Hardware encoder profiling detects available FFmpeg encoders and selects a platform-safe profile for:

*   NVENC.
*   Intel QSV.
*   AMD AMF.
*   Apple VideoToolbox.

The profiler records availability and quality hints so the CLI/UI can choose a practical default without hard-coding one platform.

---

## High-Resolution Tiling

For 8K and 16K targets, tiled rendering plans estimate:

*   Tile size.
*   Overlap margin.
*   Tile grid layout.
*   Estimated memory per tile.

Planning must remain conservative because high-resolution frames can exceed consumer GPU memory quickly.

---

## Model Toolchain

The local model toolchain includes:

*   Distillation and pruning command planning.
*   Optional local optimization command execution.
*   SHA256 metadata for optimized output models.
*   Custom ONNX sidecar metadata validation.
*   Versioned model package creation and import.

Model packages should include enough metadata for registry selection, integrity checks, and compatibility validation.

---

## Verification

Phase 5 behavior is covered by `tests/test_phase5_completion.py`. Run:

```bash
python3 -m unittest tests.test_phase5_completion
```
