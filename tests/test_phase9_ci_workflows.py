"""Tests for Phase 9 GitHub Actions workflow coverage."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SIGNING = ROOT / ".github" / "signing"


class GitHubActionsWorkflowTests(unittest.TestCase):
    def test_ci_workflow_runs_unittest_matrix_on_push_and_pr(self) -> None:
        workflow = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("push:", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertIn("ubuntu-latest", workflow)
        self.assertIn("macos-latest", workflow)
        self.assertIn("windows-latest", workflow)
        self.assertIn('"3.9"', workflow)
        self.assertIn('"3.10"', workflow)
        self.assertIn('"3.11"', workflow)
        self.assertIn("actions/setup-python@v5", workflow)
        self.assertIn("cache: pip", workflow)
        self.assertIn("actions/cache@v4", workflow)
        self.assertIn(".venv", workflow)
        self.assertIn("python -m unittest", workflow)

    def test_version_tag_workflow_tags_pyproject_version_on_main(self) -> None:
        workflow = (WORKFLOWS / "version-tag.yml").read_text(encoding="utf-8")

        self.assertIn("branches:", workflow)
        self.assertIn("- main", workflow)
        self.assertIn("pyproject.toml", workflow)
        self.assertIn("permissions:", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("tomllib.load", workflow)
        self.assertIn("tag=v$VERSION", workflow)
        self.assertIn("git tag -a", workflow)
        self.assertIn("git push origin", workflow)

    def test_release_workflow_builds_signed_windows_onefile_artifacts(self) -> None:
        workflow = (WORKFLOWS / "release-installers.yml").read_text(encoding="utf-8")

        self.assertIn("windows-installer:", workflow)
        self.assertIn("runs-on: windows-latest", workflow)
        self.assertIn("choco install ffmpeg", workflow)
        self.assertIn("--onefile --name $env:APP_NAME", workflow)
        self.assertIn("--add-binary \"$env:FFMPEG_BINARY;bin\"", workflow)
        self.assertIn("--add-binary \"$env:ONNX_RUNTIME_DIR;onnxruntime\"", workflow)
        self.assertIn("--add-data \"$env:QT_RUNTIME_DIR;PySide6\"", workflow)
        self.assertIn("signtool sign", workflow)
        self.assertIn("Validate Windows signing secrets", workflow)
        self.assertIn("WINDOWS_SIGNING_CERTIFICATE_BASE64", workflow)
        self.assertIn("WINDOWS_SIGNING_PASSWORD", workflow)
        self.assertIn("Get-AuthenticodeSignature", workflow)
        self.assertIn("Smoke test Windows CLI executable", workflow)
        self.assertIn("--dry-run", workflow)
        self.assertIn("windows-onefile-executables", workflow)

    def test_release_workflow_builds_notarized_macos_dmg(self) -> None:
        workflow = (WORKFLOWS / "release-installers.yml").read_text(encoding="utf-8")

        self.assertIn("macos-installer:", workflow)
        self.assertIn("runs-on: macos-latest", workflow)
        self.assertIn("brew install ffmpeg", workflow)
        self.assertIn("--onefile --name \"$APP_NAME\"", workflow)
        self.assertIn("--add-binary \"$FFMPEG_BINARY:bin\"", workflow)
        self.assertIn("--add-binary \"$ONNX_RUNTIME_DIR:onnxruntime\"", workflow)
        self.assertIn("--add-data \"$QT_RUNTIME_DIR:PySide6\"", workflow)
        self.assertIn("codesign --force", workflow)
        self.assertIn("Validate macOS signing and notarization secrets", workflow)
        self.assertIn("MACOS_SIGNING_CERTIFICATE_BASE64", workflow)
        self.assertIn("MACOS_SIGNING_PASSWORD", workflow)
        self.assertIn("security import", workflow)
        self.assertIn("macos-entitlements.plist", workflow)
        self.assertIn("codesign --verify", workflow)
        self.assertIn("hdiutil create", workflow)
        self.assertIn("xcrun notarytool submit", workflow)
        self.assertIn("xcrun stapler staple", workflow)
        self.assertIn("spctl --assess", workflow)
        self.assertIn("Smoke test macOS CLI executable", workflow)
        self.assertIn("macos-dmg", workflow)

    def test_release_workflow_builds_linux_deb_and_appimage(self) -> None:
        workflow = (WORKFLOWS / "release-installers.yml").read_text(encoding="utf-8")

        self.assertIn("linux-installer:", workflow)
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertIn("sudo apt-get install -y ffmpeg fuse libfuse2", workflow)
        self.assertIn("PACKAGE_VERSION", workflow)
        self.assertIn("dpkg-deb --build", workflow)
        self.assertIn("appimagetool-x86_64.AppImage", workflow)
        self.assertIn("Smoke test Linux CLI executable", workflow)
        self.assertIn("silukman-video-enhancer-v*-linux-x86_64.deb", workflow)
        self.assertIn("silukman-video-enhancer-v*-linux-x86_64.AppImage", workflow)
        self.assertIn("linux-installers", workflow)

    def test_release_workflow_caches_dependencies_and_build_outputs(self) -> None:
        workflow = (WORKFLOWS / "release-installers.yml").read_text(encoding="utf-8")

        self.assertIn("cache: pip", workflow)
        self.assertIn("actions/cache@v4", workflow)
        self.assertIn(".venv", workflow)
        self.assertIn("build", workflow)
        self.assertIn("~/.cache/pip", workflow)

    def test_release_workflow_publishes_draft_github_release(self) -> None:
        workflow = (WORKFLOWS / "release-installers.yml").read_text(encoding="utf-8")

        self.assertIn("contents: write", workflow)
        self.assertIn("publish-draft-release:", workflow)
        self.assertIn("actions/download-artifact@v4", workflow)
        self.assertIn("CHANGELOG.md", workflow)
        self.assertIn("release-notes.md", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("--draft", workflow)
        self.assertIn("release-artifacts/**/*", workflow)

    def test_release_signing_documentation_and_entitlements_exist(self) -> None:
        readme = (SIGNING / "README.md").read_text(encoding="utf-8")
        entitlements = (SIGNING / "macos-entitlements.plist").read_text(encoding="utf-8")

        self.assertIn("WINDOWS_SIGNING_CERTIFICATE_BASE64", readme)
        self.assertIn("WINDOWS_SIGNING_PASSWORD", readme)
        self.assertIn("MACOS_SIGNING_CERTIFICATE_BASE64", readme)
        self.assertIn("MACOS_NOTARY_TEAM_ID", readme)
        self.assertIn("com.apple.security.cs.disable-library-validation", entitlements)


if __name__ == "__main__":
    unittest.main()
