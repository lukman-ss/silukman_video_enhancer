"""PyInstaller build command helpers."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PackagingTarget:
    platform: str
    extension: str
    installer_tool: str


PACKAGING_TARGETS = {
    "Windows": PackagingTarget("Windows", ".exe", "iscc"),
    "Darwin": PackagingTarget("Darwin", ".dmg", "hdiutil"),
    "Linux": PackagingTarget("Linux", ".deb", "dpkg-deb"),
}


def pyinstaller_command(
    entrypoint: str = "app/cli.py",
    name: str = "silukman-video-enhancer",
    ffmpeg_binary: Path | None = None,
    qt_runtime_dir: Path | None = None,
    onnx_runtime_dir: Path | None = None,
    onefile: bool = True,
) -> list[str]:
    command = [
        "pyinstaller",
        "--clean",
        "--name",
        name,
        "--add-data",
        f"{Path('models')}:{Path('models')}",
    ]
    if onefile:
        command.append("--onefile")
    if ffmpeg_binary is not None:
        command.extend(["--add-binary", f"{ffmpeg_binary}:bin"])
    if qt_runtime_dir is not None:
        command.extend(["--add-data", f"{qt_runtime_dir}:PySide6"])
    if onnx_runtime_dir is not None:
        command.extend(["--add-binary", f"{onnx_runtime_dir}:onnxruntime"])
    command.append(entrypoint)
    return command


def desktop_pyinstaller_command(**kwargs) -> list[str]:
    return pyinstaller_command(
        entrypoint="ui/desktop.py",
        name="silukman-video-enhancer-desktop",
        **kwargs,
    )


def platform_installer_command(
    bundle_path: Path,
    platform: str | None = None,
    package_name: str = "silukman-video-enhancer",
) -> list[str]:
    selected = platform or sys.platform
    normalized = _normalize_platform(selected)
    target = PACKAGING_TARGETS[normalized]
    output_name = f"{package_name}{target.extension}"
    if normalized == "Windows":
        return [target.installer_tool, "/DAppBundle=" + str(bundle_path), f"/O{output_name}"]
    if normalized == "Darwin":
        return [
            target.installer_tool,
            "create",
            "-volname",
            package_name,
            "-srcfolder",
            str(bundle_path),
            output_name,
        ]
    return [target.installer_tool, "--build", str(bundle_path), output_name]


def _normalize_platform(platform: str) -> str:
    lowered = platform.lower()
    if lowered.startswith(("win", "cygwin", "msys")):
        return "Windows"
    if lowered in {"darwin", "mac", "macos"}:
        return "Darwin"
    if lowered.startswith("linux"):
        return "Linux"
    raise ValueError(f"Unsupported packaging platform: {platform}")
