"""Release pipeline planning for packaged installer builds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.pyinstaller_spec import (
    desktop_pyinstaller_command,
    platform_installer_command,
    pyinstaller_command,
)


@dataclass(frozen=True)
class ReleasePipelinePlan:
    platform: str
    cli_build_command: list[str]
    desktop_build_command: list[str]
    installer_command: list[str]


def build_release_pipeline(
    platform: str,
    bundle_path: Path,
    ffmpeg_binary: Path | None = None,
    qt_runtime_dir: Path | None = None,
    onnx_runtime_dir: Path | None = None,
) -> ReleasePipelinePlan:
    """Create the commands needed for an offline packaged release."""

    return ReleasePipelinePlan(
        platform=platform,
        cli_build_command=pyinstaller_command(
            ffmpeg_binary=ffmpeg_binary,
            onnx_runtime_dir=onnx_runtime_dir,
        ),
        desktop_build_command=desktop_pyinstaller_command(
            ffmpeg_binary=ffmpeg_binary,
            qt_runtime_dir=qt_runtime_dir,
            onnx_runtime_dir=onnx_runtime_dir,
        ),
        installer_command=platform_installer_command(bundle_path, platform=platform),
    )


def write_release_script(plan: ReleasePipelinePlan, output_path: Path) -> Path:
    """Write a small shell script for running the planned release commands."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "#!/usr/bin/env sh",
        "set -eu",
        _quote_command(plan.cli_build_command),
        _quote_command(plan.desktop_build_command),
        _quote_command(plan.installer_command),
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")
    output_path.chmod(0o755)
    return output_path


def _quote_command(command: list[str]) -> str:
    return " ".join(_shell_quote(part) for part in command)


def _shell_quote(value: str) -> str:
    if not value or any(char.isspace() or char in "'\"$`\\" for char in value):
        return "'" + value.replace("'", "'\"'\"'") + "'"
    return value
