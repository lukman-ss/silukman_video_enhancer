# CLI Workflow Reference

This document covers the planned command-line interface design, commands, and parameters for `silukman_video_enhancer`.

---

## Command Structure

The application will be invoked as a Python module or executable:

```bash
python -m app enhance [OPTIONS]
python -m app desktop
```

---

## Available Options

| Flag | Argument | Description | Default | Status |
| :--- | :--- | :--- | :--- | :--- |
| `-i`, `--input` | `PATH` | Path to the source input video. | *Required* | `[MVP]` |
| `-o`, `--output` | `PATH` | Path to save the enhanced output video. | `output.mp4` | `[MVP]` |
| `-m`, `--model` | `STR` | Selects the AI model to use (`realesrgan`, `swinir`, `srcnn`). | `realesrgan` | `[MVP]` |
| `-s`, `--scale` | `INT` | Upscaling multiplier (`2`, `4`). | `2` | `[MVP]` |
| `--denoise` | None | Enables frame denoising. | `False` | `[Planned]` |
| `--color-correct` | None | Enables automatic color correction. | `False` | `[Planned]` |
| `--device` | `STR` | Target device (`cpu`, `cuda`, `coreml`, `directml`, `auto`). | `auto` | `[MVP]` |
| `--crf` | `INT` | Constant Rate Factor (quality preset) for output encoding. | `18` | `[MVP]` |
| `--dry-run` | None | Validates and prints settings without running the pipeline. | `False` | `[MVP]` |
| `--audio-restore` | None | Applies FFmpeg FFT audio denoising before final muxing. | `False` | `[MVP]` |
| `--no-metadata` | None | Skips source metadata, subtitle, and chapter mapping. | `False` | `[MVP]` |
| `--quiet` | None | Enables frame-loop throttling to reduce heat and foreground lag. | `False` | `[MVP]` |
| `--benchmark` | None | Runs a short startup provider warmup benchmark. | `False` | `[MVP]` |
| `--batch` | None | Treats `--input` as a folder and processes supported video files inside it. | `False` | `[Planned]` |
| `--chain` | `STR` | Comma-separated model chain for sequential processing. | `""` | `[Planned]` |
| `--roi` | `x,y,w,h` | Selective region of interest for enhancement. | None | `[Planned]` |
| `--fp16` | None | Enables FP16 quantization when supported by the provider. | `False` | `[Planned]` |
| `--destination` | `PATH[,START,END,COPY]` | Adds an extra output destination plan. | None | `[Planned]` |
| `--face-model` | `gfpgan|codeformer` | Enables face restoration with the selected ONNX model. | None | `[Planned]` |
| `--dynamic-scale` | None | Enables dynamic spatial-temporal scaling decisions. | `False` | `[Planned]` |
| `--async-workers` | `INT` | Sets thread-pool worker count for post-processing. | `1` | `[Planned]` |
| `--checkpoint-dir` | `PATH` | Stores resumable checkpoint state and compressed frame cache. | None | `[Planned]` |
| `--worker-devices` | `STR` | Comma-separated local worker devices for distributed planning. | `""` | `[Planned]` |
| `--restore` | `denoise|deblur|artifact` | Adds a restoration model operation. Can be repeated. | None | `[Planned]` |

---

## Common CLI Recipes

### Upscale a Video by 4x using CUDA (NVIDIA GPU)
```bash
python -m app -i holiday.mp4 -o holiday_4k.mp4 -s 4 --device cuda
```

### Apply Denoise and Color Correction without Scaling
```bash
python -m app -i grainy.mp4 -o clean.mp4 -s 1 --denoise --color-correct
```

### Launch the Python Desktop App
```bash
python -m app desktop
```
