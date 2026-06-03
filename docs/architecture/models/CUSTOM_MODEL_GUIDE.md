# Custom ONNX Model Conversion & Import Guide

This document explains how to convert custom PyTorch models to ONNX format and import them safely into `silukman_video_enhancer`.

---

## 1. Overview & Purpose

While the application ships with standard pre-trained upscaling and restoration models (like Real-ESRGAN and GFPGAN), users often train custom models (e.g., custom SwinIR denoisers or specialized cartoon upscalers). 

To execute these models locally, developers must convert them to ONNX formats and declare their configurations.

---

## 2. Converting PyTorch Models to ONNX

Use standard PyTorch export tools to convert models. Ensure the following configurations are maintained:
*   **Static Input Shapes**: Match the expected patch/tile inputs (e.g. $1 \times 3 \times H \times W$).
*   **Opset Version**: Export using **Opset 15, 16, or 17** for compatibility with ONNX Runtime execution providers.

### Conceptual Export Script
```python
import torch

# Instantiate model
model = CustomUpscaler()
model.eval()

# Dummy input matching image tensor: Batch 1, Channels 3 (RGB)
dummy_input = torch.randn(1, 3, 256, 256)

torch.onnx.export(
    model,
    dummy_input,
    "custom_upscaler.onnx",
    export_params=True,
    opset_version=16,
    do_constant_folding=True,
    input_names=['input'],
    output_names=['output']
)
```

---

## 3. Sidecar JSON Configuration

To import the model, write a sidecar metadata JSON file sharing the exact same base name as the `.onnx` file (e.g., `custom_upscaler.json`):

```json
{
  "name": "custom-upscaler-x2",
  "model_type": "upscale",
  "scale": 2,
  "channels": 3,
  "min_app_version": "1.0.0"
}
```

---

## 4. Importing the Model

1.  **Copy**: Move both the `.onnx` and `.json` files into the local models directory (`~/.cache/silukman/models/`).
2.  **Discovery**: On next launch, the discovery scan will automatically identify, validate (structural checks), and register the custom model.

---

## 5. Verification

Model structural compatibility rules and dynamic sidecar metadata parsing are verified in:

```bash
python3 -m unittest tests.test_phase5_completion
```
