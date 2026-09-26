import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GALLERY = ROOT / "template-gallery"


class TemplateGalleryContractTests(unittest.TestCase):
    def test_manifest_catalogs_three_caption_and_three_editing_templates(self) -> None:
        manifest = json.loads((GALLERY / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "shine.video.template-gallery.v1")
        self.assertEqual(
            [item["id"] for item in manifest["subtitle_templates"]],
            ["clean-impact", "keyword-punch", "split-reveal"],
        )
        self.assertEqual(
            [item["id"] for item in manifest["editing_templates"]],
            ["flash-cut", "punch-zoom", "freeze-hit"],
        )

    def test_generated_media_is_kept_out_of_git(self) -> None:
        gallery_ignore = (GALLERY / ".gitignore").read_text(encoding="utf-8")
        repository_ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("generated/**", gallery_ignore)
        self.assertIn("*.mp4", repository_ignore)

    def test_generator_lists_every_template_without_rendering(self) -> None:
        result = subprocess.run(
            [str(GALLERY / "generate-gallery"), "--list"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "gallery",
                "clean-impact",
                "keyword-punch",
                "split-reveal",
                "flash-cut",
                "punch-zoom",
                "freeze-hit",
            ],
        )

    def test_renderer_exposes_split_reveal_and_safe_flash_primitives(self) -> None:
        source = (GALLERY / "render_gallery.swift").read_text(encoding="utf-8")
        self.assertIn("drawSplitReveal", source)
        self.assertIn("drawClippedText", source)
        self.assertIn("transitionFlash", source)
        self.assertIn('NSColor.white', source)
        self.assertIn('NSColor.systemYellow', source)

    def test_renderer_writes_real_png_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    "swift",
                    str(GALLERY / "render_gallery.swift"),
                    "--template",
                    "split-reveal",
                    "--output-dir",
                    directory,
                    "--width",
                    "180",
                    "--height",
                    "320",
                    "--fps",
                    "1",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            frames = sorted(Path(directory).glob("frame-*.png"))
            self.assertEqual(len(frames), 4)
            self.assertGreater(frames[0].stat().st_size, 100)

    def test_generator_uses_next_version_and_full_hd_vertical_output(self) -> None:
        script = (GALLERY / "generate-gallery").read_text(encoding="utf-8")
        self.assertIn("next_version", script)
        self.assertIn("scale=1080:1920", script)
        self.assertIn("libx264", script)
        self.assertIn("yuv420p", script)
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory)
            (generated / "sample_v1.mp4").touch()
            (generated / "sample_v3.mp4").touch()
            probe = subprocess.run(
                [str(GALLERY / "generate-gallery"), "--next-version", str(generated / "sample")],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertEqual(probe.stdout.strip(), "4")


if __name__ == "__main__":
    unittest.main()
