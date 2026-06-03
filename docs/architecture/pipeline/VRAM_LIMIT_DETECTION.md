# VRAM Limit Detection & Auto-Tiling

This document details the automated VRAM/RAM limit detection algorithms and frame tiling math used to prevent Out-Of-Memory (OOM) errors in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

Deep learning video processors running at large output resolutions (such as 4K or 8K) can exceed GPU VRAM constraints very quickly. 

To prevent runtime failures, the system incorporates an automated memory-management layer that:
*   Queries available system RAM and graphics VRAM on startup.
*   Calculates memory-safe tile dimensions for large resolution assets.
*   Performs overlap margin planning and feathered reconstruction blending.

---

## 2. Memory Limit Detection

On execution startup, the resource governor queries hardware capabilities:
*   **Windows**: Queries DirectML device adapter capabilities or DXGI APIs.
*   **macOS**: Uses system memory APIs to inspect unified RAM capacity.
*   **Linux/CUDA**: Queries NVIDIA NVML or CUDA memory management metrics.

If available memory is below target limits, the pipeline automatically forces tiling configurations.

---

## 3. Tiling Split & Blend Math

For frames exceeding memory budgets, the runner splits the raw frame array:

```text
    1920 x 1080 Frame
┌───────────┬───────────┐
│  Tile 0   │  Tile 1   │  ◄── Overlapping margins (e.g. 16px padding)
├───────────┼───────────┤
│  Tile 2   │  Tile 3   │
└───────────┴───────────┘
```

1.  **Tile Division**: The frame is divided into a grid of overlapping patches. 
2.  **Inference**: Each patch is run through the ONNX execution provider independently.
3.  **Feathered Reconstruction**: To prevent visible grid seam lines, the overlapping borders are blended using a linear gradient mask:
    $$W(x) = 1.0 - \frac{x}{\text{overlap\_margin}}$$
    This blends adjacent tile pixels smoothly.

---

## 4. Verification

The automated tiling, VRAM querying, and linear blending functions are verified in:

```bash
python3 -m unittest tests.test_phase2_task2
python3 -m unittest tests.test_phase5_completion
```
Tests assert that high-resolution frame tiling produces mathematically identical dimensions and that memory bounds are derived correctly.
