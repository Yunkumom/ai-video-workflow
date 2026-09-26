from __future__ import annotations

import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest import mock

from system.pipeline.media import MediaInfo
from system.pipeline.review_render import render_review_assets, render_review_video


def document(text: str = "測試 Test") -> dict:
    return {
        "schema": "shine.project-subtitle-review.v2", "revision": 2,
        "source": "sample.mov", "duration": 2.0,
        "style": {"fontFamily": "PingFang TC", "sizePct": 4.0, "weight": 900,
                  "color": "#FFFFFF", "strokePct": 0.07,
                  "strokeColor": "#000000", "bottomPct": 8.0},
        "cues": [{"id": 1, "start": 0.0, "end": 2.0, "text": text,
                  "runs": [{"text": "測試 ", "style": {}},
                           {"text": "Test", "style": {"fontFamily": "Arial", "sizeScale": 1.2,
                                                        "color": "#FFD400"}}]}],
    }


class ReviewRenderTests(unittest.TestCase):
    def test_native_assets_are_full_frame_and_content_addressed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = render_review_assets(document(), MediaInfo(2, 640, 360, False), root)
            self.assertEqual((manifest["width"], manifest["height"]), (640, 360))
            self.assertEqual(len(manifest["cues"]), 1)
            image = root / manifest["cues"][0]["asset"]
            self.assertTrue(image.is_file())
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height",
                                    "-of", "csv=p=0", str(image)], capture_output=True, text=True, check=False)
            self.assertEqual(probe.stdout.strip(), "640,360")
            first_key = manifest["fingerprint"]
            self.assertEqual(render_review_assets(document(), MediaInfo(2, 640, 360, False), root)["fingerprint"], first_key)
            changed = document()
            changed["style"]["sizePct"] = 4.1
            self.assertNotEqual(render_review_assets(changed, MediaInfo(2, 640, 360, False), root)["fingerprint"], first_key)

    def test_text_and_runs_must_match_before_rendering(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = document("different")
            with self.assertRaises(Exception):
                render_review_assets(invalid, MediaInfo(2, 640, 360, False), Path(directory))

    def test_video_export_uses_the_same_full_frame_asset_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {"fingerprint": "x", "width": 640, "height": 360,
                        "cues": [{"id": 1, "start": 0, "end": 2,
                                  "asset": "review-assets/x/caption-0001.png"}]}
            asset_dir = root / "review-assets" / "x"
            asset_dir.mkdir(parents=True)
            (asset_dir / "blank.png").touch()
            (asset_dir / "caption-0001.png").touch()
            commands = []
            with mock.patch("system.pipeline.review_render.render_review_assets", return_value=manifest), \
                 mock.patch("system.pipeline.review_render.require_tool", side_effect=lambda name: name), \
                 mock.patch("system.pipeline.review_render.run_command", side_effect=lambda command, **kwargs: commands.append(command)):
                result = render_review_video(root / "source.mov", document(), MediaInfo(2, 640, 360, True),
                                             root, root / "output.mp4")
            self.assertIs(result, manifest)
            self.assertEqual(len(commands), 2)
            self.assertTrue(any("overlay=0:0:shortest=1" in part for part in commands[1]))


if __name__ == "__main__":
    unittest.main()
