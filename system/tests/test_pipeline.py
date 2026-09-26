from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from system.pipeline.models import ProjectError, SubtitleCue
from system.pipeline.planning import (
    build_srt,
    discover_project,
    next_output_path,
    order_project_sources,
    parse_srt,
    select_mode,
    split_script,
    versioned_output_path,
)


class PlanningTests(unittest.TestCase):
    def test_discover_project_requires_supported_media(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_dir = root / "1_input" / "lesson"
            project_dir.mkdir(parents=True)
            with self.assertRaisesRegex(ProjectError, "media"):
                discover_project(root, "lesson")

    def test_discover_project_includes_photos_and_videos_in_filename_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_dir = root / "1_input" / "flight"
            project_dir.mkdir(parents=True)
            for name in ("3.MP4", "1.jpg", "notes.txt", "2.jpeg", "4.PNG"):
                (project_dir / name).touch()
            project = discover_project(root, "flight")
        self.assertEqual(
            [item.name for item in project.videos],
            ["1.jpg", "2.jpeg", "3.MP4", "4.PNG"],
        )

    def test_discover_project_reads_safe_settings_without_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_dir = root / "1_input" / "lesson"
            project_dir.mkdir(parents=True)
            (project_dir / "lesson.mp4").touch()
            (project_dir / "settings.json").write_text(
                json.dumps({"mode": "tutorial"}), encoding="utf-8"
            )
            project = discover_project(root, "lesson")
        self.assertEqual(project.settings["mode"], "tutorial")
        self.assertEqual([item.name for item in project.videos], ["lesson.mp4"])

    def test_source_order_setting_reorders_discovered_media(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_dir = root / "1_input" / "flight"
            project_dir.mkdir(parents=True)
            for name in ("1.jpg", "2.MP4", "3.MP4", "4.JPG"):
                (project_dir / name).touch()
            project = discover_project(root, "flight")
        ordered = order_project_sources(
            project.videos,
            {"source_order": ["2.MP4", "3.MP4", "4.JPG", "1.jpg"]},
        )
        self.assertEqual(
            [item.name for item in ordered], ["2.MP4", "3.MP4", "4.JPG", "1.jpg"]
        )

    def test_mode_selection_prefers_explicit_override(self) -> None:
        self.assertEqual(
            select_mode(
                explicit="silent-footage",
                has_subtitles=True,
                has_script=False,
                has_audio=True,
            ),
            "silent-footage",
        )

    def test_mode_selection_routes_subtitles_or_audio_to_tutorial(self) -> None:
        self.assertEqual(
            select_mode("auto", has_subtitles=True, has_script=False, has_audio=False),
            "tutorial",
        )
        self.assertEqual(
            select_mode("auto", has_subtitles=False, has_script=False, has_audio=True),
            "tutorial",
        )

    def test_mode_selection_routes_silent_script_to_silent_footage(self) -> None:
        self.assertEqual(
            select_mode("auto", has_subtitles=False, has_script=True, has_audio=False),
            "silent-footage",
        )

    def test_script_routes_ambient_audio_footage_to_silent_mode(self) -> None:
        self.assertEqual(
            select_mode("auto", has_subtitles=False, has_script=True, has_audio=True),
            "silent-footage",
        )

    def test_script_is_split_into_bounded_caption_blocks(self) -> None:
        blocks = split_script(
            "今天我們從河堤出發，看看沿途的風景。接著飛過田野，最後回到起點。",
            max_chars=14,
        )
        self.assertGreater(len(blocks), 2)
        self.assertTrue(all(1 <= len(block) <= 14 for block in blocks))
        self.assertEqual("".join(blocks), "今天我們從河堤出發，看看沿途的風景。接著飛過田野，最後回到起點。")

    def test_srt_timestamps_are_monotonic_and_round_trip(self) -> None:
        srt = build_srt(["第一段", "第二段比較長"], duration=8.0)
        cues = parse_srt(srt)
        self.assertEqual([cue.text for cue in cues], ["第一段", "第二段比較長"])
        self.assertEqual(cues[0].start, 0.0)
        self.assertGreater(cues[0].end, cues[0].start)
        self.assertGreaterEqual(cues[1].start, cues[0].end)
        self.assertAlmostEqual(cues[-1].end, 8.0, places=3)

    def test_srt_supports_multiline_text(self) -> None:
        original = [SubtitleCue(0.0, 2.5, "第一行\n第二行")]
        parsed = parse_srt(build_srt(original, duration=2.5))
        self.assertEqual(parsed, original)

    def test_next_output_path_uses_project_name_and_increments_numerically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            self.assertEqual(next_output_path(output_dir, "課程").name, "課程_v1.mp4")
            (output_dir / "課程_v1.mp4").touch()
            (output_dir / "課程_v2.mp4").touch()
            (output_dir / "課程_v10.mp4").touch()
            (output_dir / "unrelated_v99.mp4").touch()
            self.assertEqual(next_output_path(output_dir, "課程").name, "課程_v11.mp4")

    def test_versioned_output_path_uses_project_name_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            self.assertEqual(
                versioned_output_path(output_dir, "河堤", 2).name,
                "河堤_v2.mp4",
            )
            (output_dir / "河堤_v2.mp4").touch()
            with self.assertRaisesRegex(ProjectError, "already exists"):
                versioned_output_path(output_dir, "河堤", 2)


if __name__ == "__main__":
    unittest.main()
