from __future__ import annotations

import unittest

from system.pipeline.models import ProjectError
from system.pipeline.review_document import migrate_review_document, validate_review_document


class ReviewDocumentTests(unittest.TestCase):
    def test_v1_migrates_to_v2_without_losing_text_or_timing(self):
        old = {
            "schema": "shine.project-subtitle-review.v1",
            "revision": 1,
            "source": "sample.mov",
            "duration": 5.0,
            "style": {"font": "PingFang TC", "size": 6, "weight": 900, "stroke": 0.07},
            "cues": [{"id": 1, "start": 0, "end": 2.5, "text": "中文A🙂"}],
        }
        result = migrate_review_document(old)
        self.assertEqual(result["schema"], "shine.project-subtitle-review.v2")
        self.assertEqual(result["style"]["sizePct"], 6.0)
        self.assertEqual(result["cues"][0]["runs"], [{"text": "中文A🙂", "style": {}}])
        self.assertEqual((result["cues"][0]["start"], result["cues"][0]["end"]), (0.0, 2.5))

    def test_v2_roundtrip_accepts_selected_word_styles(self):
        document = {
            "schema": "shine.project-subtitle-review.v2",
            "revision": 2,
            "source": "sample.mov",
            "duration": 5.0,
            "style": {
                "fontFamily": "PingFang TC", "sizePct": 4.0, "weight": 900,
                "color": "#FFFFFF", "strokePct": 0.07,
                "strokeColor": "#000000", "bottomPct": 8.0,
            },
            "cues": [{
                "id": 1, "start": 0.0, "end": 2.5, "text": "中文A🙂",
                "runs": [
                    {"text": "中文", "style": {}},
                    {"text": "A🙂", "style": {"fontFamily": "Arial", "sizeScale": 1.2, "color": "#FFD400"}},
                ],
            }],
        }
        self.assertEqual(validate_review_document(document, available_fonts={"PingFang TC", "Arial"}), document)

    def test_rejects_malformed_or_unsafe_documents(self):
        base = migrate_review_document({
            "schema": "shine.project-subtitle-review.v1", "revision": 1,
            "source": "sample.mov", "duration": 5,
            "style": {"font": "PingFang TC", "size": 4, "weight": 900, "stroke": 0.07},
            "cues": [{"id": 1, "start": 0, "end": 2, "text": "字幕"}],
        })
        cases = []
        mismatch = {**base, "cues": [{**base["cues"][0], "runs": [{"text": "不同", "style": {}}]}]}
        cases.append(mismatch)
        for key, value in (("sizePct", 20.1), ("strokePct", float("nan"))):
            cases.append({**base, "style": {**base["style"], key: value}})
        cases.append({**base, "style": {**base["style"], "color": "red"}})
        cases.append({**base, "extra": True})
        cases.append({**base, "cues": [{**base["cues"][0], "end": 8.0}]})
        cases.append({**base, "cues": [{**base["cues"][0], "runs": [{"text": "字幕", "style": {"sizeScale": 3.1}}]}]})
        for invalid in cases:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ProjectError):
                    validate_review_document(invalid, available_fonts={"PingFang TC", "Arial"})

    def test_rejects_unavailable_fonts(self):
        document = migrate_review_document({
            "schema": "shine.project-subtitle-review.v1", "revision": 1,
            "source": "sample.mov", "duration": 5,
            "style": {"font": "Missing Font", "size": 4, "weight": 900, "stroke": 0.07},
            "cues": [{"id": 1, "start": 0, "end": 2, "text": "字幕"}],
        })
        with self.assertRaisesRegex(ProjectError, "字體"):
            validate_review_document(document, available_fonts={"PingFang TC"})


if __name__ == "__main__":
    unittest.main()
