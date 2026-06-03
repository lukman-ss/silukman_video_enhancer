# Temporal Consistency & Scene Cut Detection

This document explains the technical implementation of temporal analysis, frame skip, and scene transition boundary checks in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

Frame-by-frame AI enhancement can suffer from high-frequency temporal flickering, which is visually distracting. 

To improve temporal stability, the pipeline includes a **Temporal Analyzer** that:
*   Measures Structural Similarity (SSIM) delta values between consecutive frames.
*   Performs duplicate frame skipping to optimize throughput.
*   Detects scene transitions (scene cuts) to reset temporal buffers.

---

## 2. Frame Consistency & Skip Workflow

For each raw input frame:

```text
Raw Frame N
     │
     ▼ [Temporal Analyzer]
Compare SSIM delta with Frame N-1
  ├──► SSIM Delta < Threshold (Near-Duplicate) ──► Skip Inference ──► Reuse output N-1
  └──► SSIM Delta > Threshold (Normal Frame)   ──► Run ONNX Inference ──► Output Frame N
```

1.  **Duplicate Detection**: If a frame is nearly identical to the previous frame (e.g. static scenes, slides, or duplicate frames), the analyzer skips ONNX runtime execution and copies the previous processed output, saving up to 90% GPU usage.
2.  **Scene Cut Detection**: If the difference between consecutive frames is extremely high, the analyzer identifies a scene cut. The temporal buffer is immediately reset to prevent visual ghosting across cuts.

---

## 3. Configuration Flags

*   `--temporal`: Enables temporal consistency checks.
*   `--scene-threshold`: Sensitivity factor for scene transition resets.

---

## 4. Verification

The `TemporalAnalyzer` and its scene cut detection algorithms are covered by:

```bash
python3 -m unittest tests.test_phase2_task2
```
Tests ensure that identical frame sequences trigger correct skips and that scene boundary cuts reset internal memory buffers.
