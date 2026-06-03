# Model Optimization, Quantization & Validation

This document details the model compression, format quantization, and structural validation workflows in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

Deep learning video processors are highly compute-intensive. To support low-resource consumer computers (such as integrated graphics or NPUs), models must undergo optimization, compression, and strict architectural validation.

The model optimizer (`models/optimization.py`) and validator (`models/validation.py`) manage these tasks.

---

## 2. Structural ONNX Validation

Before running a custom or community-contributed `.onnx` model, the validator checks the network structure:
*   **Opset Version**: Verifies that the model opset is supported by the target ONNX Runtime execution provider.
*   **Tensor Shapes**: Inspects input and output nodes to ensure compatible channel layouts (e.g. 3-channel RGB) and dynamic scaling factors.
*   **Diagnostics**: Emits clear warnings if the model utilizes unsupported operators.

---

## 3. Quantization (FP16 & INT8)

Quantization reduces floating-point precision to speed up model execution:
*   **FP16 (Half-Precision)**: Casts model weights from Float32 to Float16. This doubles speed on modern tensor cores and saves 50% VRAM.
*   **INT8 (Integer-Precision)**: Quantizes weights to 8-bit integers. Useful for CPU and NPU-specific accelerators (like OpenVINO and Qualcomm QNN) where floating-point units are limited.

---

## 4. Pruning and Distillation

The optimization suite supports structural model compression:
*   **Pruning**: Identifies and removes non-critical weights or redundant channels in convolutional layers.
*   **Model Distillation**: Trains smaller student networks to mimic the output of larger, more expensive teacher upscaler models.

---

## 5. Verification

Validation, quantization, and distillation helpers are verified in the test suite:

```bash
python3 -m unittest tests.test_phase2_task2
python3 -m unittest tests.test_phase5_completion
```
Tests verify that FP16 tensor switches, INT8 planning flags, and channel validation behave correctly.
