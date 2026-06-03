"""Cross-platform preset compatibility matrix.

Phase 7, Task 7
Defines a registry of codec, color-format, execution-provider, and
package-target presets together with their per-platform support matrix.
``PresetCompatibilityMatrix`` lets callers query which presets are valid
for a given (platform, provider) combination and run automated validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import platform as platform_module
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set

# ---------------------------------------------------------------------------
# Dimension catalogues
# ---------------------------------------------------------------------------

VALID_PLATFORMS: FrozenSet[str] = frozenset({"linux", "macos", "windows"})

VALID_PROVIDERS: FrozenSet[str] = frozenset(
    {"cpu", "cuda", "tensorrt", "coreml", "directml", "rocm"}
)

VALID_CODECS: FrozenSet[str] = frozenset(
    {"h264", "h265", "av1", "vp9", "prores", "dnxhd"}
)

VALID_COLOR_FORMATS: FrozenSet[str] = frozenset(
    {"yuv420p", "yuv444p", "yuv420p10le", "yuv444p10le", "rgb24", "rgba"}
)

VALID_PACKAGE_TARGETS: FrozenSet[str] = frozenset(
    {"wheel", "appimage", "dmg", "exe", "deb", "rpm", "docker"}
)


def _validate_set(values: Set[str], valid: FrozenSet[str], label: str) -> None:
    unknown = set(values) - valid
    if unknown:
        raise ValueError(f"Unknown {label}: {sorted(unknown)}. Valid: {sorted(valid)}.")


# ---------------------------------------------------------------------------
# PresetEntry — one row in the matrix
# ---------------------------------------------------------------------------


@dataclass
class PresetEntry:
    """Describes one preset and on which platforms / providers it is supported."""

    name: str
    codec: str
    color_format: str
    execution_providers: Set[str]   # providers that CAN run this preset
    platforms: Set[str]             # platforms that support this preset
    package_targets: Set[str]       # distributable formats for this preset
    notes: str = ""

    def __post_init__(self) -> None:
        _validate_set({self.codec}, VALID_CODECS, "codec")
        _validate_set({self.color_format}, VALID_COLOR_FORMATS, "color_format")
        _validate_set(self.execution_providers, VALID_PROVIDERS, "execution_providers")
        _validate_set(self.platforms, VALID_PLATFORMS, "platforms")
        _validate_set(self.package_targets, VALID_PACKAGE_TARGETS, "package_targets")

    def supports(self, platform: str, provider: str) -> bool:
        return platform in self.platforms and provider in self.execution_providers

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "codec": self.codec,
            "color_format": self.color_format,
            "execution_providers": sorted(self.execution_providers),
            "platforms": sorted(self.platforms),
            "package_targets": sorted(self.package_targets),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# PresetCompatibilityMatrix
# ---------------------------------------------------------------------------


class PresetCompatibilityMatrix:
    """Registry and validator for cross-platform preset compatibility."""

    def __init__(self) -> None:
        self._presets: Dict[str, PresetEntry] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, entry: PresetEntry) -> "PresetCompatibilityMatrix":
        if entry.name in self._presets:
            raise ValueError(f"Preset '{entry.name}' already registered.")
        self._presets[entry.name] = entry
        return self

    def unregister(self, name: str) -> None:
        self._presets.pop(name, None)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, name: str) -> PresetEntry:
        return self._presets[name]

    def list_all(self) -> List[PresetEntry]:
        return list(self._presets.values())

    def compatible_presets(
        self, platform: str, provider: str
    ) -> List[PresetEntry]:
        """Return all presets valid for *platform* + *provider*."""
        return [
            p for p in self._presets.values() if p.supports(platform, provider)
        ]

    def incompatible_presets(
        self, platform: str, provider: str
    ) -> List[PresetEntry]:
        return [
            p for p in self._presets.values() if not p.supports(platform, provider)
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @dataclass
    class ValidationResult:
        preset_name: str
        platform: str
        provider: str
        compatible: bool
        reason: str = ""

    def validate_all(
        self,
        platforms: Optional[List[str]] = None,
        providers: Optional[List[str]] = None,
    ) -> List["PresetCompatibilityMatrix.ValidationResult"]:
        """
        Run the full compatibility matrix validation.

        For every preset × platform × provider combination, produce a
        ``ValidationResult``.  Filters by *platforms* / *providers* when given.
        """
        target_platforms = list(platforms or VALID_PLATFORMS)
        target_providers = list(providers or VALID_PROVIDERS)
        results: List[PresetCompatibilityMatrix.ValidationResult] = []

        for preset in self._presets.values():
            for plat in target_platforms:
                for prov in target_providers:
                    compatible = preset.supports(plat, prov)
                    reason = ""
                    if not compatible:
                        missing = []
                        if plat not in preset.platforms:
                            missing.append(f"platform '{plat}' not supported")
                        if prov not in preset.execution_providers:
                            missing.append(f"provider '{prov}' not supported")
                        reason = "; ".join(missing)
                    results.append(
                        PresetCompatibilityMatrix.ValidationResult(
                            preset_name=preset.name,
                            platform=plat,
                            provider=prov,
                            compatible=compatible,
                            reason=reason,
                        )
                    )
        return results

    def validate_one(
        self, name: str, platform: str, provider: str
    ) -> "PresetCompatibilityMatrix.ValidationResult":
        preset = self.get(name)
        compatible = preset.supports(platform, provider)
        reason = ""
        if not compatible:
            parts = []
            if platform not in preset.platforms:
                parts.append(f"platform '{platform}' not supported")
            if provider not in preset.execution_providers:
                parts.append(f"provider '{provider}' not supported")
            reason = "; ".join(parts)
        return PresetCompatibilityMatrix.ValidationResult(
            preset_name=name,
            platform=platform,
            provider=provider,
            compatible=compatible,
            reason=reason,
        )

    def __len__(self) -> int:
        return len(self._presets)

    def __contains__(self, name: str) -> bool:
        return name in self._presets


# ---------------------------------------------------------------------------
# Built-in baseline presets (reasonable cross-platform defaults)
# ---------------------------------------------------------------------------

def build_default_matrix() -> PresetCompatibilityMatrix:
    """Return a matrix pre-loaded with common baseline presets."""
    m = PresetCompatibilityMatrix()
    m.register(PresetEntry(
        name="h264_cpu_universal",
        codec="h264",
        color_format="yuv420p",
        execution_providers={"cpu"},
        platforms={"linux", "macos", "windows"},
        package_targets={"wheel", "appimage", "dmg", "exe", "deb", "rpm", "docker"},
        notes="Widest compatibility — CPU-only H.264.",
    ))
    m.register(PresetEntry(
        name="h265_cuda_linux",
        codec="h265",
        color_format="yuv420p10le",
        execution_providers={"cuda", "tensorrt"},
        platforms={"linux"},
        package_targets={"wheel", "docker", "deb", "rpm"},
        notes="High-efficiency HEVC on CUDA/TensorRT Linux nodes.",
    ))
    m.register(PresetEntry(
        name="prores_coreml_macos",
        codec="prores",
        color_format="yuv444p10le",
        execution_providers={"coreml", "cpu"},
        platforms={"macos"},
        package_targets={"dmg", "wheel"},
        notes="ProRes + CoreML on Apple Silicon / Intel Mac.",
    ))
    m.register(PresetEntry(
        name="av1_cpu_multiplatform",
        codec="av1",
        color_format="yuv420p",
        execution_providers={"cpu"},
        platforms={"linux", "macos", "windows"},
        package_targets={"wheel", "appimage", "dmg", "exe", "deb"},
        notes="AV1 software encode — slow but universal.",
    ))
    m.register(PresetEntry(
        name="h264_directml_windows",
        codec="h264",
        color_format="yuv420p",
        execution_providers={"directml", "cpu"},
        platforms={"windows"},
        package_targets={"exe", "wheel"},
        notes="DirectML-accelerated H.264 on Windows.",
    ))
    return m


def current_platform_key(system: str | None = None) -> str:
    """Return the matrix platform key for the current or supplied OS name."""

    name = (system or platform_module.system()).lower()
    if name == "darwin":
        return "macos"
    if name.startswith("win"):
        return "windows"
    return "linux"


def validate_current_environment(
    provider: str = "cpu",
    matrix: PresetCompatibilityMatrix | None = None,
    system: str | None = None,
) -> List[PresetCompatibilityMatrix.ValidationResult]:
    """Validate built-in presets for the local platform/provider pair."""

    active_matrix = matrix or build_default_matrix()
    return active_matrix.validate_all(
        platforms=[current_platform_key(system)],
        providers=[provider],
    )


def write_matrix_report(
    path: Path,
    matrix: PresetCompatibilityMatrix | None = None,
) -> Path:
    """Write the full compatibility matrix validation report as JSON."""

    active_matrix = matrix or build_default_matrix()
    payload = {
        "presets": [entry.to_dict() for entry in active_matrix.list_all()],
        "validation": [
            result.__dict__ for result in active_matrix.validate_all()
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
