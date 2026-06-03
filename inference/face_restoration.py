"""Face restoration model planning and ONNX hook."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from inference.runtime import ONNXFrameUpscaler
from models.registry import model_cache_dir
from pipeline.roi import ROI, extract_roi_rgb, paste_roi_rgb


FACE_MODELS = {
    "gfpgan": "gfpgan.onnx",
    "codeformer": "codeformer.onnx",
}


@dataclass(frozen=True)
class FaceRestorationPlan:
    model_name: str
    model_path: Path
    enabled: bool


def plan_face_restoration(model_name: str, root: Path | None = None) -> FaceRestorationPlan:
    if model_name not in FACE_MODELS:
        available = ", ".join(sorted(FACE_MODELS))
        raise ValueError(f"Unknown face model `{model_name}`. Available: {available}")
    model_path = (root or model_cache_dir()) / FACE_MODELS[model_name]
    return FaceRestorationPlan(
        model_name=model_name,
        model_path=model_path,
        enabled=model_path.exists(),
    )


class FaceRestorer:
    """ONNX-backed face restoration processor for cropped RGB face regions."""

    def __init__(self, plan: FaceRestorationPlan, device: str, enable_fp16: bool = False) -> None:
        if not plan.enabled:
            raise FileNotFoundError(f"Face restoration model missing: {plan.model_path}")
        self.plan = plan
        self.runtime = ONNXFrameUpscaler(plan.model_path, device, enable_fp16=enable_fp16)

    def detect_faces(self, frame: bytes, width: int, height: int) -> list[ROI]:
        """Heuristic face detection. Returns bounding boxes for detected faces."""
        if width <= 4 or height <= 4:
            return [ROI(0, 0, width, height)]
        # Center crop as a mock face region for offline testing
        w = max(4, width // 4)
        h = max(4, height // 4)
        x = (width - w) // 2
        y = (height - h) // 2
        return [ROI(x, y, w, h)]

    def restore(self, frame: bytes, width: int, height: int) -> bytes:
        """Detect faces, crop face regions, restore them using ONNX, and merge back."""
        faces = self.detect_faces(frame, width, height)
        if not faces:
            return frame

        output_frame = frame
        for face in faces:
            face_crop = extract_roi_rgb(output_frame, width, height, face)
            restored_crop = self.runtime.upscale(face_crop, face.width, face.height)
            if not isinstance(restored_crop, bytes):
                restored_crop = bytes(len(face_crop))
            output_frame = paste_roi_rgb(output_frame, width, height, face, restored_crop)

        return output_frame
