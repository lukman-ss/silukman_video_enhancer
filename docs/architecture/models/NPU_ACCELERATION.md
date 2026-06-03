# NPU Acceleration (OpenVINO and QNN)

This document details the configuration, deployment, and optimization strategies for running AI inference on Intel and Qualcomm Neural Processing Units (NPUs) in `silukman_video_enhancer`.

---

## 1. Overview & Purpose

Many modern consumer laptops are equipped with dedicated Neural Processing Units (NPUs) like Intel AI Boost or Qualcomm Hexagon. NPUs offer highly energy-efficient execution profiles, making them ideal for long-running offline video enhancement.

The execution provider coordinator supports running inference on these devices using **Intel OpenVINO** and **Qualcomm QNN** execution providers.

---

## 2. NPU Execution Providers

The runtime layer selects the appropriate provider during startup:

*   **Intel OpenVINO (`OpenVINOExecutionProvider`)**: Targets Intel Core Ultra CPU, integrated Arc graphics, and Intel NPUs.
*   **Qualcomm QNN (`QNNExecutionProvider`)**: Targets Snapdragon Elite X platform NPUs on Windows on ARM.

To maintain execution reliability:
```text
Select Provider: OpenVINO / QNN
  ├──► Success ──► Run NPU Inference
  └──► Failure ──► Fallback to CPU / CUDA execution planner
```

---

## 3. NPU Optimization Strategies

NPU architectures require specific model layouts to run efficiently:

1.  **Format Quantization**: NPUs typically do not support float64 and have limited float32 support. The model must be quantized to **FP16** or **INT8** before compilation.
2.  **Fixed Input Dimensions**: NPUs are optimized for fixed static shapes. The validator ensures model shapes are locked, disabling dynamic resizing on NPU nodes.
3.  **Layout Conversion**: Layouts are automatically converted to optimal channel formats (e.g. NHWC) expected by QNN or OpenVINO runtimes.

---

## 4. Verification

The runtime execution provider selection and NPU fallback logic are verified in:

```bash
python3 -m unittest tests.test_phase5_completion
```
Tests verify that NPU provider choices are registered and that fallback pipelines switch to CPU when hardware runtimes are absent.
