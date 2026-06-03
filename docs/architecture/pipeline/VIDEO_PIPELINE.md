# Video Processing Pipeline

This document explains the technical implementation of the video pipeline, showing how frames are read, buffered, processed, and encoded back into a video file while preserving audio.

---

## Pipeline Architecture

To achieve optimal throughput on consumer hardware without memory leaks or high RAM usage, `silukman_video_enhancer` utilizes a generator-based consumer-producer pipeline model.

```
                  ┌────────────────────────┐
                  │    Raw Input Video     │
                  └───────────┬────────────┘
                              │ FFmpeg subprocess
                              ▼
                  ┌────────────────────────┐
                  │    Producer Thread     │
                  │ (Reads raw RGB frames) │
                  └───────────┬────────────┘
                              │
                              ▼ Queue Buffer (Limited size)
                  ┌────────────────────────┐
                  │    Consumer Thread     │
                  │ (AI Models Inference)  │
                  └───────────┬────────────┘
                              │
                              ▼ Queue Buffer (Limited size)
                  ┌────────────────────────┐
                  │    Encoder Thread      │
                  │ (Writes enhanced video)│
                  └───────────┬────────────┘
                              │ FFmpeg subprocess
                              ▼
                  ┌────────────────────────┐
                  │   Muxed Output Video   │
                  └────────────────────────┘
```

---

## Frame Extraction (Demuxing)

Instead of using OpenCV's `cv2.VideoCapture` which can be unreliable with certain codecs, we wrap `ffmpeg` directly to extract raw frames over a stdout pipe:

```python
# Conceptual extraction command
ffmpeg_cmd = [
    'ffmpeg',
    '-i', input_path,
    '-f', 'image2pipe',
    '-pix_fmt', 'rgb24',
    '-vcodec', 'rawvideo',
    '-'
]
```

**Key Advantages:**
*   Accurate timestamp reading.
*   Bypasses native OpenCV decoding bugs.
*   Outputs raw `rgb24` directly into standard input stream buffers.

---

## Parallel Processing Queue

1.  **Thread Concurrency**: The pipeline runs three asynchronous threads:
    *   **Reader Thread**: Reads raw frames from the pipe and puts them in `InputQueue`.
    *   **Inference Thread**: Fetches frames from `InputQueue`, processes them, and puts them in `OutputQueue`.
    *   **Writer Thread**: Fetches frames from `OutputQueue` and pipes them to the FFmpeg encoder.
2.  **Queue Limits**: To prevent the reader thread from filling system RAM, queues are instantiated with a fixed maximum size (e.g., `maxsize=64`). Once the queue is full, the producer blocks until the consumer frees up slots.

---

## Audio Handling (Muxing)

Audio preservation is split into two phases:

1.  **Extraction (Analysis Phase)**:
    We probe the input file for audio streams. If present, we extract the audio to a temporary container:
    ```bash
    ffmpeg -i input.mp4 -vn -acodec copy temp_audio.aac
    ```
2.  **Merging (Finalization Phase)**:
    Once all frames have been enhanced and written to a temporary video-only file (`temp_enhanced.mp4`), we mux the original audio and the new video back together:
    ```bash
    ffmpeg -i temp_enhanced.mp4 -i temp_audio.aac -c:v copy -c:a copy -map 0:v:0 -map 1:a:0? final_output.mp4
    ```
    *Note: The `?` in `-map 1:a:0?` ensures the command succeeds even if the input file had no audio.*

---

## Video Encoding & Export

For writing the enhanced frames, we pipe output to a writing FFmpeg subprocess:

*   **Default Video Codec**: H.264 (`libx264`) for maximum compatibility, or H.265 (`libx265`) for better compression efficiency.
*   **Color Format**: `yuv420p` for standard hardware player compatibility.
*   **Compression Profile**: Constant Rate Factor (CRF) is used (default `CRF = 18` for near-lossless archiving).

---

## Advanced Pipeline Features [Planned]

### 1. Dynamic Frame Tiling (VRAM Protection)
To prevent Out-Of-Memory (OOM) exceptions on low-VRAM GPUs (e.g., 4GB laptops), large frames (1080p+) are processed using a tiling approach:
*   **Patch Division**: Frames are cropped into overlapping patches (e.g., $256 \times 256$ pixels) with a padding buffer (e.g., 16 pixels).
*   **Inference**: Each patch is run through the ONNX model independently.
*   **Feathered Blending**: Patches are reconstructed back into the full frame using a linear blending algorithm on the overlapping margins to prevent visible seam lines.

### 2. Pause and Resume Checkpoint System
Because offline video rendering is compute-intensive and can take hours, the pipeline supports recovery checkpoints:
*   **High-Speed Lossless Caching**: Enhanced frames are compressed in-memory using **ZSTD** or **LZ4** and cached in a temporary directory (`.tmp_frames/`). This reduces disk writes and saves up to 80% disk space compared to raw uncompressed RGB arrays.
*   **State File**: A JSON state tracker saves metadata containing the `last_processed_frame_index` and active settings.
*   **Resume Flow**: If interrupted, restarting the CLI command reads the state file, skips already processed frames, and continues writing to the cache folder before performing the final audio-video mux.

### 3. Scene Cut Detection & Temporal Filtering
Independent frame enhancement can lead to visual flickering. We plan to introduce a temporal filter:
*   **Optical Flow Blending**: Blends the current enhanced frame with historical frame arrays to smooth out sudden pixel changes.
*   **Scene Change Detection**: Compares color histograms between consecutive raw frames. If a high delta value is detected (scene transition), the temporal frame buffer resets immediately to prevent visual ghosting and motion smear across cuts.

### 4. Region of Interest (ROI) Selective Enhancement
To save computational energy (up to 80%) on large resolutions:
*   **Bounding Box Input**: Users can supply pixel coordinate bounds via CLI or GUI.
*   **Auto Face/Object Focus**: Integrates a lightweight model (e.g., YOLO/Face Detector) to locate regions of interest automatically.
*   **Selective Process**: Only the ROI is sent to the upscale/denoise ONNX model. The surrounding areas are bypassed and composite-merged back into the original frame layout.

### 5. Local Frame Interpolation (FPS Booster & Slo-Mo)
Integrates temporal frame interpolation:
*   **RIFE Model (ONNX)**: Fills intermediate frames natively (e.g., boosting 24/30 FPS videos to smooth 60 FPS).
*   **Slow-motion rendering**: Generates ultra-sharp, artifact-free slow-motion files natively on local hardware.

### 6. Dynamic Resource Governor (Quiet / Background Mode)
AI inference pushes consumer CPU/GPU hardware to maximum capacity, causing heavy system lag and high fan noise:
*   **Frame Pacing / Throttling**: Users can toggle `--quiet` or `--background` modes, introducing small millisecond sleep delays between frame processing blocks to prevent overheating and maintain general OS responsiveness.
*   **Process Priority**: Adjusts the OS scheduler priority (using `nice` on Unix/macOS or `psutil` priority classes) to yield CPU slices to other foreground applications.

### 7. Multi-GPU / Distributed Local Pipeline
For setups equipped with multiple GPUs (e.g., integrated + discrete GPUs, or multi-GPU workstations):
*   **Parallel Staging**: Raw frames are split into alternating queues (e.g., GPU 0 processes even frames, GPU 1 processes odd frames).
*   **Reassembly Thread**: The output collector thread synchronizes frame sequential indices before sending them to the encoder pipeline, maximizing local processing capability.

### 8. Concurrency & Parallelism Optimizations
To eliminate processing starvation bottlenecks:
*   **Async GPU Double Buffering**: Uses asynchronous VRAM streams to upload frame $N+1$ and download frame $N-1$ from the GPU while frame $N$ is undergoing active ONNX inference.
*   **Dynamic Thread-Pool Post-Processing**: Offloads CPU-intensive operations (pixel normalization, crop tiling, feathered blending, color correction) to a worker thread pool (`ThreadPoolExecutor`), allowing the GPU thread to focus exclusively on model inference.
*   **Decoupled Streaming Audio-Video Muxer**: Audio streams are fed into a temporary ring buffer, and encoded video frames are directly piped to a non-blocking FFmpeg muxer process running in parallel. This skips writing intermediate `.mp4` video files to disk, saving 50% on file write latencies.

