from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from system.pipeline.cli import _choose_sidecar, _prepare_music, _silent_footage, _tutorial, main
from system.pipeline.media import (
    MediaInfo,
    build_silence_cuts,
    parse_silence_log,
    probe_media,
)
from system.pipeline.models import ProjectError, SubtitleCue
from system.pipeline.planning import find_exact_retake_cuts, remap_cues_after_cuts
from system.pipeline.render import (
    build_music_mix_command,
    build_subtitle_command,
    concatenate_sources,
    render_with_caption_overlays,
)
from system.pipeline.review import build_review_html, review_path_for_output
from system.pipeline.transcription import (
    ensure_network_transcription_allowed,
    groq_payload_to_cues,
)


class MediaPlanningTests(unittest.TestCase):
    def test_app_setting_disables_music_before_catalog_or_network_access(self) -> None:
        project = SimpleNamespace(
            settings={"background_music": False},
            root=Path("/should-not-be-read"),
            project_id="subtitle-only",
            script_path=None,
        )
        music, record, reason = _prepare_music(
            project,
            {"music": {"enabled": True, "catalog_path": "missing.json"}},
            mode="tutorial",
            duration=3.0,
        )
        self.assertIsNone(music)
        self.assertIsNone(record)
        self.assertEqual(reason, "background music is disabled for this project")

    def test_silence_log_becomes_middle_only_cuts(self) -> None:
        log = """
[silencedetect] silence_start: 2.0
[silencedetect] silence_end: 4.0 | silence_duration: 2.0
[silencedetect] silence_start: 8.0
[silencedetect] silence_end: 8.5 | silence_duration: 0.5
"""
        silences = parse_silence_log(log)
        cuts = build_silence_cuts(
            silences,
            duration=10.0,
            min_silence=1.2,
            keep_pause=0.4,
        )
        self.assertEqual(cuts, [(2.2, 3.8)])

    def test_subtitle_cues_are_remapped_after_a_cut(self) -> None:
        cues = [
            SubtitleCue(0.0, 1.0, "第一句"),
            SubtitleCue(4.0, 6.0, "第二句"),
        ]
        remapped = remap_cues_after_cuts(cues, [(2.0, 4.0)])
        self.assertEqual(remapped[0], cues[0])
        self.assertEqual(remapped[1], SubtitleCue(2.0, 4.0, "第二句"))

    def test_exact_adjacent_retake_keeps_later_take(self) -> None:
        cues = [
            SubtitleCue(1.0, 2.0, "現在開始設定。"),
            SubtitleCue(2.2, 3.4, "現在開始設定"),
            SubtitleCue(4.0, 5.0, "下一步。"),
        ]
        self.assertEqual(find_exact_retake_cuts(cues), [(1.0, 2.0)])


class SecurityAndRenderTests(unittest.TestCase):
    def test_tutorial_builds_cut_timeline_and_returns_versioned_subtitles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "1_input" / "lesson"
            processing_dir = root / "2_processing" / "lesson"
            output = root / "3_output" / "lesson" / "lesson_v1.mp4"
            input_dir.mkdir(parents=True)
            processing_dir.mkdir(parents=True)
            source = input_dir / "lesson.mp4"
            source.touch()
            sidecar = input_dir / "lesson.srt"
            sidecar.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\n測試字幕\n", encoding="utf-8"
            )
            project = SimpleNamespace(
                videos=(source,),
                subtitle_paths=(sidecar,),
                input_dir=input_dir,
                processing_dir=processing_dir,
            )
            info = MediaInfo(5.0, 320, 180, True)
            defaults = {
                "tutorial": {
                    "silence_threshold_db": -40,
                    "min_silence_seconds": 1.2,
                    "keep_pause_seconds": 0.4,
                }
            }
            with mock.patch("system.pipeline.cli.detect_silences", return_value=[(2.0, 4.0)]):
                with mock.patch("system.pipeline.cli.render_cut_timeline") as cut_render:
                    with mock.patch("system.pipeline.cli.render_with_subtitles") as subtitle_render:
                        subtitle, cuts = _tutorial(project, info, defaults, output)
            self.assertEqual(subtitle, output.with_suffix(".srt"))
            self.assertEqual(cuts, [(2.2, 3.8)])
            cut_render.assert_called_once()
            subtitle_render.assert_called_once()

    def test_requested_sidecar_selects_one_caption_file_among_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "1_input" / "flight"
            input_dir.mkdir(parents=True)
            for name in ("2.mp4", "3.mp4", "v2.srt", "v4.srt"):
                (input_dir / name).touch()
            from system.pipeline.planning import discover_project

            project = discover_project(root, "flight")
            self.assertEqual(_choose_sidecar(project, "v4.srt").name, "v4.srt")

    def test_silent_sidecar_is_rendered_and_copied_to_versioned_srt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "1_input" / "flight"
            input_dir.mkdir(parents=True)
            source = input_dir / "2.mp4"
            source.touch()
            sidecar = input_dir / "v2.srt"
            sidecar.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\n測試字幕\n", encoding="utf-8"
            )
            from system.pipeline.planning import discover_project

            project = discover_project(root, "flight")
            info = MediaInfo(2.0, 320, 180, False)
            output = root / "3_output" / "flight_v2.mp4"
            with mock.patch(
                "system.pipeline.cli.concatenate_sources", return_value=(source, info)
            ):
                with mock.patch("system.pipeline.cli.render_with_subtitles") as render:
                    with mock.patch("system.pipeline.cli.render_plain"):
                        subtitle, cuts = _silent_footage(project, [info], {}, output)
            self.assertEqual(subtitle.name, "flight_v2.srt")
            self.assertIn("測試字幕", subtitle.read_text(encoding="utf-8"))
            render.assert_called_once()

    def test_photo_probe_uses_configured_still_duration(self) -> None:
        payload = {
            "streams": [
                {"codec_type": "video", "width": 1320, "height": 2565}
            ],
            "format": {},
        }
        completed = mock.Mock(returncode=0, stdout=json.dumps(payload), stderr="")
        with mock.patch("system.pipeline.media.require_tool", return_value="ffprobe"):
            with mock.patch("system.pipeline.media.subprocess.run", return_value=completed):
                info = probe_media(Path("cover.JPG"), still_duration=5.0)
        self.assertEqual(info.duration, 5.0)
        self.assertTrue(info.is_still)

    def test_concatenation_uses_first_video_canvas_and_loops_photos(self) -> None:
        sources = [
            (Path("1.jpg"), MediaInfo(5.0, 1320, 2565, False, True)),
            (Path("2.mp4"), MediaInfo(10.0, 3840, 2160, False, False)),
        ]
        commands: list[list[str]] = []
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("system.pipeline.render.require_tool", side_effect=lambda name: name):
                with mock.patch(
                    "system.pipeline.render.run_command",
                    side_effect=lambda command, **_: commands.append(list(command)),
                ):
                    _, info = concatenate_sources(sources, Path(directory))
        first_command = commands[0]
        self.assertIn("-loop", first_command)
        self.assertIn("scale=3840:2160", " ".join(first_command))
        self.assertEqual((info.width, info.height, info.duration), (3840, 2160, 15.0))

    def test_review_html_contains_timeline_and_editable_persistent_fields(self) -> None:
        html = build_review_html(
            project_id="river & road",
            output_name="final.mp4",
            sources=[
                (Path("1.jpg"), MediaInfo(5.0, 1320, 2565, False, True)),
                (Path("2.mp4"), MediaInfo(10.25, 3840, 2160, False, False)),
            ],
        )
        self.assertIn("river &amp; road", html)
        self.assertIn("00:00:05.000", html)
        self.assertIn("00:00:15.250", html)
        self.assertIn("裁切起點", html)
        self.assertIn("字幕修正", html)
        self.assertIn("localStorage", html)
        self.assertIn('src="final.mp4"', html)

    def test_review_path_tracks_versioned_video_stem(self) -> None:
        self.assertEqual(review_path_for_output(Path("河堤_v2.mp4")).name, "河堤_v2.html")

    def test_network_transcription_requires_one_scoped_approval(self) -> None:
        with self.assertRaisesRegex(ProjectError, "AI_VIDEO_ALLOW_NETWORK"):
            ensure_network_transcription_allowed({"GROQ_API_KEY": "present"})
        with self.assertRaisesRegex(ProjectError, "GROQ_API_KEY"):
            ensure_network_transcription_allowed({"AI_VIDEO_ALLOW_NETWORK": "1"})
        key = ensure_network_transcription_allowed(
            {"AI_VIDEO_ALLOW_NETWORK": "1", "GROQ_API_KEY": "present"}
        )
        self.assertEqual(key, "present")

    def test_groq_segments_convert_to_timestamped_cues(self) -> None:
        cues = groq_payload_to_cues(
            {
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": " 第一段 "},
                    {"start": 1.5, "end": 3.0, "text": "第二段"},
                ]
            }
        )
        self.assertEqual(
            cues,
            [
                SubtitleCue(0.0, 1.5, "第一段"),
                SubtitleCue(1.5, 3.0, "第二段"),
            ],
        )

    def test_tutorial_subtitle_render_preserves_geometry_and_audio(self) -> None:
        command = build_subtitle_command(
            source=Path("source.mp4"),
            subtitle=Path("subtitles.srt"),
            output=Path("final.mp4"),
            has_audio=True,
            normalize_audio=True,
        )
        joined = " ".join(command)
        self.assertIn("subtitles=", joined)
        self.assertIn("loudnorm", joined)
        self.assertIn("Noto Sans CJK TC", joined)
        self.assertIn("BorderStyle=4", joined)
        self.assertIn("BackColour=&H2E000000", joined)
        self.assertNotIn("scale=", joined)
        self.assertNotIn("crop=", joined)
        self.assertNotIn("ffmpeg.exe", joined)

    def test_music_mix_command_loops_fades_and_ducks_background_audio(self) -> None:
        command = build_music_mix_command(
            source=Path("source.mp4"),
            music=Path("music.mp3"),
            output=Path("final.mp4"),
            info=MediaInfo(30.0, 1280, 720, True),
            duck_voice=True,
        )
        joined = " ".join(command)
        self.assertIn("aloop", joined)
        self.assertIn("afade", joined)
        self.assertIn("sidechaincompress", joined)
        self.assertIn("amix", joined)
        self.assertIn("-map 0:v", joined)

    def test_swift_caption_fallback_matches_readable_black_box_style(self) -> None:
        script = Path("system/pipeline/caption_images.swift").read_text(encoding="utf-8")
        self.assertIn('Noto Sans CJK TC', script)
        self.assertIn('Source Han Sans TC', script)
        self.assertIn('alpha: 0.82', script)

    def test_swift_fitted_background_uses_the_same_per_line_text_geometry(self) -> None:
        script = Path("system/pipeline/caption_images.swift").read_text(encoding="utf-8")
        self.assertIn("struct CaptionLineLayout", script)
        self.assertIn("layout.backgroundRect", script)
        self.assertIn("layout.textRect", script)
        self.assertIn("attributed.draw", script)
        self.assertNotIn("fitBackground ? min(CGFloat(canvasWidth - 16)", script)

    def test_swift_caption_fallback_scales_up_for_4k(self) -> None:
        script = Path("system/pipeline/caption_images.swift").read_text(encoding="utf-8")
        self.assertIn('Double(width) * 0.019', script)
        self.assertIn('min(144.0', script)
        self.assertIn('min(42.0, Double(width) * 0.045)', script)
        self.assertRegex(script, r'let fontSize = max\(\s*24\.0')

    def test_swift_caption_fallback_uses_one_height_for_every_timeline_frame(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "captions.json"
            output = root / "images"
            payload.write_text(
                json.dumps(
                    [
                        {"text": "Single line", "start": 0.0, "end": 1.0},
                        {"text": "English line\n中文一行", "start": 1.0, "end": 2.0},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "swift",
                    "system/pipeline/caption_images.swift",
                    "--input",
                    str(payload),
                    "--output-dir",
                    str(output),
                    "--video-width",
                    "3840",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            geometries = []
            for name in ("blank.png", "caption-0001.png", "caption-0002.png"):
                probe = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "stream=width,height",
                        "-of",
                        "csv=p=0",
                        str(output / name),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(probe.returncode, 0, probe.stderr)
                width, height = (int(value) for value in probe.stdout.strip().split(","))
                geometries.append((width, height))
            self.assertEqual(geometries, [(1600, 379), (1600, 379), (1600, 379)])

    def test_caption_fallback_renders_a_continuous_track_before_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            timeline = root / "timeline.ffconcat"
            source = root / "source.mp4"
            subtitle = root / "captions.srt"
            output = root / "3_output" / "flight" / "tutorial_v2" / "flight_v2.mp4"
            processing_dir = root / "2_processing" / "flight"
            commands: list[list[str]] = []
            with mock.patch(
                "system.pipeline.render._caption_timeline", return_value=timeline
            ) as mocked_timeline:
                with mock.patch(
                    "system.pipeline.render.require_tool", side_effect=lambda name: name
                ):
                    with mock.patch(
                        "system.pipeline.render.run_command",
                        side_effect=lambda command, **_: commands.append(list(command)),
                    ):
                        render_with_caption_overlays(
                            source,
                            subtitle,
                            output,
                            processing_dir=processing_dir,
                            info=MediaInfo(12.0, 3840, 2160, True),
                            normalize_audio=False,
                        )

            self.assertEqual(mocked_timeline.call_args.args[1], processing_dir)
            self.assertFalse((root / "3_output" / "2_processing").exists())
            self.assertEqual(len(commands), 2)
            self.assertIn("fps=30", " ".join(commands[0]))
            self.assertIn("qtrle", commands[0])
            self.assertIn("caption-track.mov", " ".join(commands[1]))


class CliTests(unittest.TestCase):
    def test_default_render_uses_project_name_and_first_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "1_input" / "內容名稱"
            input_dir.mkdir(parents=True)
            (input_dir / "內容名稱.mp4").touch()
            info = MediaInfo(duration=6.0, width=1280, height=720, has_audio=False)
            with mock.patch("system.pipeline.cli.probe_media", return_value=info):
                with mock.patch(
                    "system.pipeline.cli._silent_footage", return_value=(None, [])
                ) as render:
                    with mock.patch("system.pipeline.cli._report"):
                        with mock.patch("system.pipeline.cli.write_review_html"):
                            code = main(["內容名稱", "--root", str(root)])
            self.assertEqual(code, 0)
            self.assertEqual(render.call_args.args[3].name, "內容名稱_v1.mp4")

    def test_dry_run_writes_processing_plan_but_no_output_media(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_dir = root / "1_input" / "flight"
            input_dir.mkdir(parents=True)
            (input_dir / "flight.mp4").touch()
            (input_dir / "script.md").write_text("第一段。第二段。", encoding="utf-8")
            info = MediaInfo(duration=6.0, width=1280, height=720, has_audio=False)
            stdout = io.StringIO()
            with mock.patch("system.pipeline.cli.probe_media", return_value=info):
                with redirect_stdout(stdout):
                    code = main(["flight", "--root", str(root), "--dry-run"])
            self.assertEqual(code, 0)
            plan = json.loads(
                (root / "2_processing/flight/plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(plan["mode"], "silent-footage")
            self.assertEqual(plan["aspectRatio"], "original")
            self.assertFalse((root / "3_output/flight/flight_v1.mp4").exists())
            self.assertIn("silent-footage", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
