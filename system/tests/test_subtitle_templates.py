from __future__ import annotations

import json
import unittest
from pathlib import Path

from system.pipeline.models import SubtitleCue
from system.pipeline.subtitle_templates import (
    caption_limit,
    caption_render_options,
    load_catalog,
    resegment_cues,
    segment_caption_text,
)


ROOT = Path(__file__).resolve().parents[2]


class SubtitleTemplateCatalogTests(unittest.TestCase):
    def test_catalog_preserves_named_first_versions_without_private_fields(self) -> None:
        catalog_path = ROOT / "templates/catalog.json"
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog = load_catalog(catalog_path)

        self.assertEqual(raw["schema"], "shine.subtitle.catalog.v1")
        self.assertEqual(
            [(item.id, item.name_zh_tw, item.version, item.status) for item in catalog],
            [
                ("S01", "貼字黑底", 1, "testing"),
                ("S02", "清晰描邊", 1, "testing"),
                ("S03", "乾淨重擊", 1, "testing"),
                ("S04", "關鍵字跳出", 1, "testing"),
                ("S05", "黃字裂開補白", 1, "testing"),
            ],
        )
        serialized = json.dumps(raw, ensure_ascii=False).casefold()
        for forbidden in ("sample", "example", "media", "path", "captiontext"):
            self.assertNotIn(forbidden, serialized)

    def test_catalog_status_is_data_and_only_uses_owner_visible_states(self) -> None:
        catalog = load_catalog(ROOT / "templates/catalog.json")
        self.assertTrue(catalog)
        self.assertEqual(len({item.id for item in catalog}), len(catalog))
        self.assertTrue(all(item.status in {"mature", "testing"} for item in catalog))

    def test_render_options_keep_s01_fitted_and_preserve_other_first_versions(self) -> None:
        s01 = caption_render_options("S01", ROOT / "templates/catalog.json")
        self.assertTrue(s01.show_background)
        self.assertTrue(s01.fit_background)
        self.assertFalse(s01.outline)

        s02 = caption_render_options("S02", ROOT / "templates/catalog.json")
        self.assertFalse(s02.show_background)
        self.assertTrue(s02.outline)
        self.assertFalse(s02.heavy_text)

        self.assertTrue(
            caption_render_options("S03", ROOT / "templates/catalog.json").heavy_text
        )


class CaptionSegmentationTests(unittest.TestCase):
    def test_orientation_selects_approved_character_limits(self) -> None:
        self.assertEqual(caption_limit(width=1080, height=1920), 10)
        self.assertEqual(caption_limit(width=1920, height=1080), 16)
        self.assertEqual(caption_limit(width=1080, height=1080), 10)

    def test_portrait_segments_preserve_text_and_use_no_more_than_two_lines(self) -> None:
        original = "今天我們從入口慢慢走進展場，接著會看到非常巨大的南瓜作品。"
        segments = segment_caption_text(original, max_chars_per_line=10, max_lines=2)

        self.assertGreater(len(segments), 1)
        self.assertEqual("".join(part.replace("\n", "") for part in segments), original)
        for segment in segments:
            lines = segment.splitlines()
            self.assertLessEqual(len(lines), 2)
            self.assertTrue(all(1 <= len(line) <= 10 for line in lines))

    def test_landscape_segments_prefer_meaningful_boundaries_and_protect_tokens(self) -> None:
        original = "請先設定 OpenAI API，再輸出 1080×1920 影片。"
        segments = segment_caption_text(original, max_chars_per_line=16, max_lines=2)

        rendered = "".join(part.replace("\n", "") for part in segments)
        self.assertEqual(rendered, original)
        self.assertIn("OpenAI", rendered)
        self.assertIn("1080×1920", rendered)
        self.assertTrue(all(len(line) <= 16 for part in segments for line in part.splitlines()))

    def test_resegmented_cues_keep_original_interval_and_monotonic_timing(self) -> None:
        original = SubtitleCue(
            2.0,
            8.0,
            "第一句需要適合手機閱讀，第二句也不能一次塞入太多文字。",
        )
        cues = resegment_cues([original], max_chars_per_line=10, max_lines=2)

        self.assertGreater(len(cues), 1)
        self.assertEqual(cues[0].start, original.start)
        self.assertEqual(cues[-1].end, original.end)
        self.assertEqual(
            "".join(cue.text.replace("\n", "") for cue in cues),
            original.text,
        )
        for previous, current in zip(cues, cues[1:]):
            self.assertAlmostEqual(previous.end, current.start, places=6)
            self.assertLess(previous.start, previous.end)
        self.assertLess(cues[-1].start, cues[-1].end)


if __name__ == "__main__":
    unittest.main()
