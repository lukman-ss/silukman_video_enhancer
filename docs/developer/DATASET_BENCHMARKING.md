# Dataset Benchmarking & Regression Testing

This document details the design, execution, and baseline comparison mechanism of the Dataset Benchmarking tool in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

To ensure that changes to the video enhancement pipeline (model switches, parameter tuning, FFmpeg upgrades) do not introduce visual regressions or quality degradation, the project includes an automated **Dataset Benchmark Runner**.

This runner:
*   Discovers pairs of original and enhanced videos.
*   Calculates quality metrics (PSNR, SSIM, VMAF) for each pair.
*   Runs statistical artifact detection to flag corrupted frames or rendering anomalies.
*   Compares results against historical baselines and fails the run if quality drops below acceptable thresholds.
*   Exports structured JSON summaries for CI/CD or QA pipelines.

---

## 2. Dataset Directory Structure

The benchmark runner expects a structured input directory matching this layout:

```text
dataset/
├── original/
│   ├── sample_01.mp4
│   └── sample_02.mp4
└── enhanced/
    ├── sample_01.mp4
    └── sample_02.mp4
```

*   **original/**: Contains the source video clips before processing.
*   **enhanced/**: Contains the processed outputs. Files must share the exact same names as their original counterparts.

---

## 3. Benchmarking Workflow

The execution pipeline consists of four major stages:

```mermaid
graph LR
    A[Discover Pairs] --> B[Collect Metrics]
    B --> C[Check Artifacts]
    C --> D[Compare Baseline]
    D --> E[Export JSON]
```

### A. Discovery
The helper scans the `original/` folder and matches each file with the corresponding file in `enhanced/`. Missing matches are silently skipped.

### B. Metric Collection
For each matched pair, the runner calculates:
*   **PSNR** (Peak Signal-to-Noise Ratio)
*   **SSIM** (Structural Similarity Index)
*   **VMAF** (Video Multi-Method Assessment Fusion)

### C. Visual Artifact Check
The system scans frame buffers (or file byte slices) using the `detect_artifact` utility to identify indicators of corrupted frames, pure black output, or visual noise blocks.

### D. Baseline Comparison
Results are evaluated against a configured dictionary of minimum metrics:
```python
baselines = {
    "sample_01": {
        "psnr": 35.0,
        "ssim": 0.95
    }
}
```
If any metric is lower than the baseline, the test case is marked as **failed**.

### E. JSON Report Generation
A summary is written to the output path containing detailed stats for each case:
```json
{
  "passed": true,
  "cases": [
    {
      "name": "sample_01",
      "metrics": {
        "psnr": "38.251",
        "ssim": "0.978"
      },
      "artifact_score": 0.0,
      "passed": true,
      "failure_reason": ""
    }
  ]
}
```

---

## 4. Verification

The benchmark suite and regression detection are fully verified in the unit test suite:

```bash
python3 -m unittest tests.test_phase4_completion
```
