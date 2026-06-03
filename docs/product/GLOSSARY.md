# Glossary of Technical Terms

This document provides definitions for the key technical terms, metrics, and abbreviations used throughout `silukman_video_enhancer`.

---

## Terms & Definitions

### 3D LUT (Look-Up Table)
A three-dimensional table used in post-production color grading to map source RGB input color coordinates to new color output values. Configured via `.cube` files.

### RIFE (Real-Time Intermediate Flow Estimation)
A deep learning flow estimation model used for video frame interpolation, enabling frame-rate doubling or slow-motion frame synthesis.

### ONNX (Open Neural Network Exchange)
An open-source format for machine learning models, permitting interoperability between different training frameworks (like PyTorch) and runtime engines.

### ONNX Runtime Execution Provider
A hardware-specific plugin (e.g. `CUDAExecutionProvider`, `CoreMLExecutionProvider`, `OpenVINOExecutionProvider`) that maps ONNX operations to optimized hardware acceleration APIs.

### VMAF (Video Multi-Method Assessment Fusion)
An objective video quality metric developed by Netflix that predicts subjective user video quality scores by combining spatial and temporal metrics.

### PSNR (Peak Signal-to-Noise Ratio)
An engineering metric representing the ratio between the maximum possible power of a signal and the power of corrupting noise that affects the fidelity of its representation. Measured in decibels (dB).

### SSIM (Structural Similarity Index)
A perceptual metric that measures the similarity between two images by evaluating luminance, contrast, and structure changes. Returns a value between -1.0 and 1.0.

### Crop Tiling
A memory-management technique that crops large video frames into smaller overlapping patches (tiles) to prevent Out-Of-Memory (OOM) errors during GPU model inference.

### Double Buffering
A hardware pipeline technique that uploads input frame $N+1$ and downloads output frame $N-1$ from GPU VRAM asynchronously while frame $N$ is actively undergoing inference.

### FFmpeg `afftdn`
An FFmpeg audio filter that performs noise reduction using Fast Fourier Transforms (FFT) to analyze and attenuate background noise frequencies.
