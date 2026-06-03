# Face Restoration and Model Chaining

This document details the multi-model chaining pipelines and localized face restoration mechanics in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

Simple upscaling models can fail to recover high-frequency facial details, sometimes leading to blurred or distorted faces in video exports. 

To overcome this, the application supports **Face Restoration** (via GFPGAN or CodeFormer models) and **Multi-Model Chaining**, allowing multiple ONNX models to process each video frame sequentially.

---

## 2. Multi-Model Chaining

The pipeline builds a `ModelChain` representing the sequence of enhancement operations applied to each frame:

```text
Raw Frame Input
       │
       ▼
 ┌───────────┐
 │ Denoise   │ ──► (SwinIR / Compression Artifact Cleanup)
 └─────┬─────┘
       │
       ▼
 ┌───────────┐
 │ Upscale   │ ──► (Real-ESRGAN / Baseline Lanczos)
 └─────┬─────┘
       │
       ▼
 ┌───────────┐
 │ Face Rest │ ──► (GFPGAN / CodeFormer Face ROI restoration)
 └─────┬─────┘
       │
       ▼
Enhanced Frame Output
```

---

## 3. Localized Face Restoration Workflow

Face restoration is executed as a localized region-of-interest (ROI) process to save compute cycles:

1.  **Face Detection**: The detector scans the frame to find bounding boxes enclosing faces.
2.  **Crop & Extract**: Facial regions are cropped out and aligned.
3.  **Enhance**: The aligned face crops are run through the GFPGAN/CodeFormer ONNX models.
4.  **Feathered Blend**: The enhanced face is warped back into the original frame location using a feathered blending mask to prevent harsh seams.

---

## 4. Configuration

Model chaining and face restoration are configured via CLI or presets:
*   `--face-model`: Selects the face restorer (e.g., `gfpgan`, `codeformer`).
*   `--model-chain`: Ordered list of model identifiers to chain sequentially.

---

## 5. Verification

Model chain building, execution routing, and face ROI restoration coordinates mapping are verified in:

```bash
python3 -m unittest tests.test_phase2_task2
```
Unit tests cover the sequence execution flow and ensure fallback strategies are applied if a model in the chain fails to load.
