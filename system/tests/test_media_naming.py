import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from system.pipeline.media_naming import (
    slugify_subject,
    parse_iso_datetime,
    extract_media_datetime,
    format_media_date,
    generate_standard_name,
    generate_media_names,
)


class MediaNamingTests(unittest.TestCase):
    def test_slugify_known_folders(self):
        self.assertEqual(slugify_subject("0831秘境咖啡廳"), "secret_cafe")
        self.assertEqual(slugify_subject("0901萬丹森林"), "wandan_forest")
        self.assertEqual(slugify_subject("壽山遊客中心"), "shoushan_visitor_center")
        self.assertEqual(slugify_subject("0903佛光山"), "foguangshan")
        self.assertEqual(slugify_subject("新竹一日遊"), "hsinchu_day_trip")
        self.assertEqual(slugify_subject("20250305_classroom_lecture_001"), "classroom_lecture")

    def test_slugify_arbitrary_english_and_symbols(self):
        self.assertEqual(slugify_subject("Campus Entrance"), "campus_entrance")
        self.assertEqual(slugify_subject("  Campus-Entrance-Gate! 1  "), "campus_entrance_gate_1")
        self.assertEqual(slugify_subject(""), "clip")

    def test_parse_iso_and_exif_datetimes(self):
        dt1 = parse_iso_datetime("2019:12:03 14:22:10")
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1.year, 2019)
        self.assertEqual(dt1.month, 12)
        self.assertEqual(dt1.day, 3)

        dt2 = parse_iso_datetime("2026-09-12T01:22:15.000000Z")
        self.assertIsNotNone(dt2)
        self.assertEqual(dt2.year, 2026)
        self.assertEqual(dt2.month, 9)
        self.assertEqual(dt2.day, 12)

    def test_extract_media_datetime_from_filename_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "20191203_something.mov"
            p.touch()
            dt, source = extract_media_datetime(p)
            self.assertEqual(format_media_date(dt), "20191203")
            self.assertEqual(source, "path_pattern_yyyymmdd")

    def test_generate_media_names_chronological_ordering(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            f1 = t / "shot_a.mp4"
            f2 = t / "shot_b.mp4"
            f3 = t / "shot_c.mp4"
            for f in (f1, f2, f3): f.touch()

            # Mock datetimes to be distinct
            dt_map = {
                f1: datetime.datetime(2019, 12, 3, 10, 0, 0),
                f2: datetime.datetime(2019, 12, 3, 9, 30, 0), # earlier than f1
                f3: datetime.datetime(2019, 12, 3, 11, 0, 0), # latest
            }

            with patch("system.pipeline.media_naming.extract_media_datetime", side_effect=lambda p: (dt_map[p], "mock")):
                results = generate_media_names([f1, f2, f3], subject="campus_entrance")

            # f2 should be 001, f1 should be 002, f3 should be 003
            self.assertEqual(results[0]["original_name"], "shot_b.mp4")
            self.assertEqual(results[0]["new_name"], "20191203_campus_entrance_001.mp4")
            self.assertEqual(results[1]["original_name"], "shot_a.mp4")
            self.assertEqual(results[1]["new_name"], "20191203_campus_entrance_002.mp4")
            self.assertEqual(results[2]["original_name"], "shot_c.mp4")
            self.assertEqual(results[2]["new_name"], "20191203_campus_entrance_003.mp4")

    def test_generate_media_names_collision_avoidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            f_new = t / "shot_d.mp4"
            f_new.touch()
            dt = datetime.datetime(2019, 12, 3, 12, 0, 0)

            existing = [
                "20191203_campus_entrance_001.mp4",
                "20191203_campus_entrance_002.mp4",
            ]

            with patch("system.pipeline.media_naming.extract_media_datetime", return_value=(dt, "mock")):
                results = generate_media_names([f_new], subject="campus_entrance", existing_names=existing)

            self.assertEqual(results[0]["new_name"], "20191203_campus_entrance_003.mp4")
            self.assertEqual(results[0]["index"], 3)

    def test_real_video_quicktime_tags(self):
        sample = Path(__file__).resolve().parents[2] / "1_input" / "0912" / "sample.mov"
        if sample.is_file():
            dt, src = extract_media_datetime(sample)
            self.assertEqual(format_media_date(dt), "20260912")
            self.assertIn("creation", src)

    def test_real_photo_exif_tags(self):
        sample = Path(__file__).resolve().parents[2] / "1_input" / "20250305_classroom_lecture_001" / "20250305_classroom_lecture_001.jpg"
        if sample.is_file():
            dt, src = extract_media_datetime(sample)
            self.assertEqual(format_media_date(dt), "20250305")


if __name__ == "__main__":
    unittest.main()
