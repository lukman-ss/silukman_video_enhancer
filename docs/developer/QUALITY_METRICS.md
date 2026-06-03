# Quality Evaluation Metrics

This document outlines the methods and metrics used to assess the quality of video enhancements in `silukman_video_enhancer`.

---

## Quantitative Metrics [Planned]

To ensure enhancement results are objectively better, the project will implement a benchmarking suite utilizing:

*   **PSNR (Peak Signal-to-Noise Ratio)**: Measures reconstruction quality for lossy compression. Higher is better.
*   **SSIM (Structural Similarity Index Measure)**: Evaluates structural, luminance, and contrast changes. Values closer to 1.0 indicate closer structural fidelity to the source.
*   **VMAF (Video Multi-Method Assessment Fusion)**: Netflix's perceptual video quality metric. It combines human vision modeling with machine learning to provide accurate visual scoring.

---

## Qualitative Assessment [Planned]

Quantitative metrics do not always align with human eyes (e.g., a highly sharpened image might score low on PSNR but look better to a human). We will use:
*   **Side-by-side visual inspections**.
*   **Blind tests on standard video sequences** (e.g., Sintel, Big Buck Bunny).

---

## Benchmarking Suite [Future]

A proposed CLI utility to run quality scoring against a dataset:
```bash
python -m tools.benchmark --input original.mp4 --enhanced enhanced.mp4 --metric vmaf
```

---

## Enhancement Comparison Report Export [Future]
To make results reviewable offline without dynamic application engines:
*   **Report Generation**: The pipeline can output a self-contained interactive `report.html` file.
*   **Split Slider Interface**: Embedded JavaScript/CSS assets will render selected frames side-by-side using an interactive slider component.
*   **Embedded Statistics**: Includes PSNR, SSIM, and execution metadata (FPS, hardware provider) inside the static HTML report.
