"""Tests for Phase 10 GitHub repository presence assets."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GitHubPresenceTests(unittest.TestCase):
    def test_repository_metadata_documents_about_fields_and_topics(self) -> None:
        metadata = (ROOT / ".github" / "repository.yml").read_text(encoding="utf-8")

        self.assertIn("Local-first offline video enhancement CLI", metadata)
        self.assertIn("https://github.com/lukman-ss/silukman_video_enhancer", metadata)
        for topic in ["video-enhancement", "upscaling", "onnx", "ffmpeg", "pyside6", "ai", "python"]:
            self.assertIn(topic, metadata)

    def test_readme_has_release_badges_and_social_preview_reference(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        preview = (ROOT / "docs" / "assets" / "github-social-preview.svg").read_text(encoding="utf-8")

        self.assertIn("img.shields.io/github/v/release/lukman-ss/silukman_video_enhancer", readme)
        self.assertIn("img.shields.io/github/downloads/lukman-ss/silukman_video_enhancer/total", readme)
        self.assertIn("Python Package", readme)
        self.assertIn("docs/assets/github-social-preview.svg", readme)
        self.assertIn('width="1280"', preview)
        self.assertIn('height="640"', preview)

    def test_release_workflow_uses_versioned_asset_names_and_draft_release(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release-installers.yml").read_text(encoding="utf-8")

        self.assertIn("silukman-video-enhancer-v*-windows-x64.exe", workflow)
        self.assertIn("silukman-video-enhancer-desktop-v*-windows-x64.exe", workflow)
        self.assertIn("silukman-video-enhancer-v*-macos-arm64.dmg", workflow)
        self.assertIn("silukman-video-enhancer-v*-linux-x86_64.deb", workflow)
        self.assertIn("silukman-video-enhancer-v*-linux-x86_64.AppImage", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("--draft", workflow)
        self.assertIn("CHANGELOG.md", workflow)

    def test_version_policy_and_package_publish_workflow_exist(self) -> None:
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        packaging = (ROOT / "docs" / "developer" / "BUILD_AND_PACKAGING.md").read_text(encoding="utf-8")
        publish = (ROOT / ".github" / "workflows" / "publish-package.yml").read_text(encoding="utf-8")

        self.assertIn("vMAJOR.MINOR.PATCH", contributing)
        self.assertIn("Patch release", contributing)
        self.assertIn("Minor release", contributing)
        self.assertIn("Major release", contributing)
        self.assertIn("silukman-video-enhancer-vX.Y.Z-windows-x64.exe", packaging)
        self.assertIn("python-package-dist", publish)
        self.assertIn("python -m build", publish)
        self.assertIn("gh release upload", publish)

    def test_issue_templates_and_security_policy_exist(self) -> None:
        issue_dir = ROOT / ".github" / "ISSUE_TEMPLATE"
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

        for name in ["bug_report.yml", "feature_request.yml", "model_request.yml", "config.yml"]:
            self.assertTrue((issue_dir / name).exists(), name)
        self.assertIn("GitHub Security Advisory", security)
        self.assertIn("Plugin sandbox escapes", security)
        self.assertIn("Release signing", security)


if __name__ == "__main__":
    unittest.main()
