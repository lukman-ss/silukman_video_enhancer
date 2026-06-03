# Performance Tuning & Hardware Optimization Guide

This document provides recommendations for configuring the execution parameters of `silukman_video_enhancer` to match various hardware environments.

---

## 1. Core Parameters Overview

To optimize execution speed and prevent hardware lockups, focus on tuning three primary configurations:
*   `scale`: Model upscaling factor (2x vs 4x).
*   `async_workers`: Thread pool size for async CPU-based image pre/post-processing.
*   `tiling_factor` (implicitly managed or set via presets): Subdivision size of high-resolution frames.

---

## 2. Hardware Profiles & Configurations

### Profile A: Low-Resource Laptops (Intel/AMD CPU only, <8GB RAM)
*   **Target**: Prevent system freezes and memory starvation.
*   **Recommended Settings**:
    *   `device`: `cpu`
    *   `scale`: `2`
    *   `async_workers`: `1` (disables async overhead)
    *   `fp16`: `false` (FP16 is often slower on standard consumer CPUs)
    *   `quiet`: `true` (enables resource pacing to prevent overheating)

### Profile B: Entry-level GPUs (GTX 1650, RTX 3050 Laptop, 4GB VRAM)
*   **Target**: Leverage GPU acceleration without triggering Out-of-Memory (OOM) failures.
*   **Recommended Settings**:
    *   `device`: `cuda` or `directml`
    *   `scale`: `2`
    *   `async_workers`: `2`
    *   `fp16`: `true` (saves up to 50% VRAM)
    *   `tiling_factor` (Auto-Tiling): Ensure active to split large dimensions.

### Profile C: High-End Workstations (RTX 3090/4090, 24GB VRAM)
*   **Target**: Maximize throughput using parallel workers.
*   **Recommended Settings**:
    *   `device`: `cuda`
    *   `scale`: `4`
    *   `async_workers`: `4` (fully saturates post-processing cores)
    *   `fp16`: `true`
    *   `worker_devices`: `(0, 1)` (if multi-GPU setups are available, to run round-robin distribution)

### Profile D: Apple Silicon (M1/M2/M3 Mac, Unified Memory)
*   **Target**: Utilize native CoreML accelerators and unified RAM.
*   **Recommended Settings**:
    *   `device`: `coreml`
    *   `async_workers`: `3`
    *   `fp16`: `true`

---

## 3. General Optimization Tips

1.  **Warm-Up Profiling**: Always run with the `--benchmark` flag during first-time setups. This permits the auto-tuning benchmarker to profile and cache the optimal ONNX provider configuration.
2.  **Avoid Thread Overcommit**: Never set `async_workers` higher than the number of physical CPU cores, as context switching will degrade rendering performance.
