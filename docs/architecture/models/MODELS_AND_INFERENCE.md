# Models and Inference

This document details the machine learning models supported by `silukman_video_enhancer`, model optimization strategies, and runtime execution providers.

---

## Supported Models

To keep the application offline-first and runnable on consumer hardware, we target lightweight neural networks optimized for frame-by-frame processing.

### 1. Super-Resolution (Upscaling)
*   **Real-ESRGAN (ONNX)**: Good for general-purpose restoration, illustration, and scaling.
*   **Real-ESRGAN-Anime**: Fine-tuned variant specifically for animated videos.
*   **SRCNN / FSRCNN**: Ultra-lightweight models for users with basic hardware (CPU/integrated GPU).

### 2. Denoise & Deblur
*   **SwinIR-Lightweight**: Transformer-based model optimized for image/frame denoising.
*   **DPIR (Deep Plug-and-Play Image Restoration)**: Handles denoise and deblur tasks.

### 3. Compression Artifact Cleanup
*   **Artifact Removal Networks**: Tailored layers targeting macroblocking commonly found in old MP4/FLV files.

---

## Inference Engine (ONNX Runtime)

All deep learning models are converted to the Open Neural Network Exchange (ONNX) format. This allows us to use **ONNX Runtime** (ORT) as our single, consolidated inference driver.

### Advantages of ONNX Runtime:
1.  **Framework Agnostic**: We do not need PyTorch, TensorFlow, or JAX dependencies in the production build.
2.  **Hardware Performance**: Direct API hookups to localized hardware backends.
3.  **Low Footprint**: Dramatically reduces the size of the final packaged application.

---

## Hardware Acceleration

ONNX Runtime utilizes "Execution Providers" (EPs) to compile and run neural operations on physical accelerators. We implement automatic fallback mechanisms:

```
┌─────────────────────────────────────────────────────────┐
│            Initialize Inference Engine                  │
└────────────────────────────┬────────────────────────────┘
                             │
            Is Nvidia GPU & CUDA present?
            ├── [Yes] ──> Use CUDAExecutionProvider
            └── [No]
                 │
            Is Apple Silicon present?
            ├── [Yes] ──> Use CoreMLExecutionProvider
            └── [No]
                 │
            Is Windows OS with Direct3D12?
            ├── [Yes] ──> Use DmlExecutionProvider (DirectML)
            └── [No] ───> Fallback to CPUExecutionProvider
```

### Performance Settings:
*   **Intra-op threads**: Matches physical CPU core counts for the CPU provider.
*   **GPUMemoryLimit**: Prevents CUDA out-of-memory errors by managing maximum VRAM allocations.
*   **FP16 Quantization**: Support for half-precision floating-point inference to double processing speed on compatible GPUs.

---

## Advanced Inference Features [Planned]

### 1. Auto-tuning Hardware Benchmarker
To optimize processing speeds automatically, a startup benchmark routine is planned:
*   **Warmup Test**: Runs a brief 10-frame inference test using various thread configurations and Execution Providers.
*   **Optimal Settings Profiler**: Selects the fastest configuration (highest FPS) without causing runtime instability or thermal throttling, then caches this configuration for future runs.

### 2. Multi-Model Chaining (Sequential Pipelines)
Instead of running only one filter type per video rendering run, users can specify a pipeline chain:
```
[Raw Frame] ──> (Denoise Model) ──> (Upscaling Model) ──> (Color Correction) ──> [Final Frame]
```
Operations are combined in-memory on the GPU/VRAM level to avoid disk I/O bottlenecks.

### 3. Intelligent Scene-based Model Selection
Different scenes require different enhancement approaches (e.g., a low-light indoor shot vs. an outdoor high-action scene):
*   **Scene Classifier**: A lightweight classification header analyzes frame samples at scene boundaries.
*   **Dynamic Model Switching**: The pipeline dynamically swaps the active ONNX model weights in-memory (e.g., switching from an Anime model to a Photographic Restoration model) to match visual characteristics.

### 4. Dynamic VRAM Estimation & Auto-Tiling
Instead of manually guessing tile configurations:
*   **VRAM Sensing**: The engine queries free VRAM prior to execution via platform APIs (CUDA helper, DirectML memory query, macOS system metrics).
*   **Auto-Tiling Calculation**: The system automatically determines the largest safe patch size (e.g., $512 \times 512$ vs $256 \times 256$) that avoids VRAM overflow while maximizing throughput.

---

## Model Management

*   **Offline Access**: Models are cached locally in the user's home directory under `~/.cache/silukman_video_enhancer/models/`.
*   **Integrity Verification (SHA256)**: To prevent runtime errors from corrupt files and ensure security, downloaded models are validated against a local SHA256 hash registry before being loaded into ONNX Runtime.
*   **On-Demand Download**: If a selected model is missing during runtime, the CLI will automatically download it once from the release asset registry.
*   **Manual Placement**: Users can manually place `.onnx` models into the cache folder for fully air-gapped operations.
