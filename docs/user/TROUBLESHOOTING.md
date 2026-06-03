# Troubleshooting and FAQ

This document addresses common bugs, setup issues, and hardware limitations encountered when running `silukman_video_enhancer`.

---

## Hardware Issues

### 1. GPU Acceleration is not active (falling back to CPU)
*   **CUDA (NVIDIA)**: Ensure you have compatible NVIDIA GPU drivers installed and that the CUDA Toolkit version matches the ONNX Runtime compilation target. You can verify CUDA visibility by running:
    ```bash
    python -c "import onnxruntime as ort; print(ort.get_device())"
    ```
*   **DirectML (Windows)**: DirectML requires Windows 10/11 with DirectX 12 support. Ensure your GPU drivers are updated.

### 2. Out of Memory (OOM) Errors on GPU
*   **Cause**: Processing large frame resolutions (e.g., upscaling directly to 4K) exceeds GPU VRAM capacity.
*   **Solution**: Downscale output resolution, reduce batch execution numbers, or switch to a lighter model profile.

---

## Input / Output Formats

### 1. Video file has no audio output after enhancement
*   **Cause**: The input video may not contain any audio streams, or FFmpeg mapping did not succeed.
*   **Check**: Use `ffprobe` to verify if the source video indeed had audio streams:
    ```bash
    ffprobe -i input.mp4 -show_streams -select_streams a
    ```

### 2. Unsupported video codec errors
*   **Cause**: Local FFmpeg builds do not support the target video container/codec.
*   **Solution**: Re-encode input files to standard H.264/AAC MP4 formats before running the enhancer.
