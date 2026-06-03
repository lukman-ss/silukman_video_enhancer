# RIFE Frame Interpolation & Slow-Motion

This document details the architecture, frame calculation rules, and execution paths for local RIFE temporal frame interpolation in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

Frame interpolation inserts intermediate frames between existing video frames to increase the frame rate (e.g., from 24/30 FPS to 60 FPS) or to generate high-quality slow-motion footage without stuttering.

To achieve this offline, the system integrates the **Real-Time Intermediate Flow Estimation (RIFE)** model inside the main enhancement runner.

---

## 2. Interpolation Architecture

The interpolation process runs as an optional post-processing stage after frame upscaling:

```text
Input Video Frame N
       │
       ▼ [AI Enhancement/Upscaling]
Enhanced Frame N  ──┐
                    ├─► [RIFE Model Inference] ─► Interpolated Frame N.5
Enhanced Frame N+1 ─┘
       │
       ▼ [FFmpeg Writer Thread]
Output Stream (Double Frame Rate)
```

---

## 3. Frame Calculation Rules

The coordinator decides whether to run RIFE interpolation based on the target FPS configuration:

*   **FPS Boosting**: If `target_fps` is higher than the input video's FPS, the runner invokes RIFE to double or multiply the frame rate:
    *   **Double (2x)**: Runs one RIFE inference pass per frame pair (Frame $N$, Frame $N+1$) to generate Frame $N.5$.
    *   **Fallback**: If RIFE runtime components are missing, the pipeline falls back to FFmpeg's minterpolate filter.
*   **Slow-Motion**: If the user requests a speed reduction (e.g., 0.5x speed), RIFE generates intermediate frames while the output container maintains the original input FPS, resulting in smooth slow-motion.

---

## 4. CLI Parameters

RIFE frame interpolation is controlled by the following CLI flags:

*   `--target-fps`: Sets the desired output frame rate.
*   `--slow-motion`: Multiplier for generating smooth slow-motion sequences (e.g., `--slow-motion 2` doubles frame counts).

---

## 5. Verification

The interpolation planning and execution flows are tested in:

```bash
python3 -m unittest tests.test_phase3_completion
python3 -m unittest tests.test_phase4_completion
```
Tests ensure that the frame rate metadata matches target specifications and that the FFmpeg output is generated correctly.
