"""Tests for shared configuration and CLI parsing."""

from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from app.cli import build_parser, config_from_args, main
from app.config import EnhancementConfig


class EnhancementConfigTests(unittest.TestCase):
    def test_valid_dry_run_config_accepts_documented_options(self) -> None:
        config = EnhancementConfig(
            input_path=Path("missing.mp4"),
            output_path=Path("output.mp4"),
            model="realesrgan",
            scale=4,
            device="cuda",
            crf=18,
            denoise=True,
            color_correct=True,
        )

        config.validate(require_existing_input=False)

        self.assertIn("scale=4x", config.summary())
        self.assertIn("denoise", config.summary())

    def test_invalid_scale_is_rejected(self) -> None:
        config = EnhancementConfig(input_path=Path("in.mp4"), output_path=Path("out.mp4"), scale=3)

        with self.assertRaises(ValueError):
            config.validate(require_existing_input=False)


class CliTests(unittest.TestCase):
    def test_parser_maps_cli_flags_to_shared_config(self) -> None:
        args = build_parser().parse_args(
            [
                "enhance",
                "-i",
                "input.mp4",
                "-o",
                "result.mp4",
                "-s",
                "4",
                "--device",
                "cpu",
                "--denoise",
            ]
        )

        config = config_from_args(args)

        self.assertEqual(config.input_path, Path("input.mp4"))
        self.assertEqual(config.output_path, Path("result.mp4"))
        self.assertEqual(config.scale, 4)
        self.assertEqual(config.device, "cpu")
        self.assertTrue(config.denoise)

    def test_dry_run_does_not_require_existing_input_file(self) -> None:
        with redirect_stdout(StringIO()):
            exit_code = main(["enhance", "-i", "missing.mp4", "--dry-run"])

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
