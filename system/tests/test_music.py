from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from system.pipeline.models import ProjectError
from system.pipeline.music import (
    build_license_record,
    download_track,
    load_catalog,
    select_track,
)


class MusicCatalogTests(unittest.TestCase):
    def test_selector_prefers_instrumental_matching_mood_and_duration(self) -> None:
        tracks = [
            {
                "id": "voice",
                "title": "Voice Track",
                "provider": "Mixkit",
                "source_url": "https://example.test/voice",
                "local_path": "voice.mp3",
                "mood": ["calm"],
                "pace": "slow",
                "duration": 60,
                "instrumental": False,
                "commercial_use": True,
                "attribution_required": False,
                "license_url": "https://example.test/license",
                "license_evidence": "captured",
            },
            {
                "id": "calm-bed",
                "title": "Calm Bed",
                "provider": "Mixkit",
                "source_url": "https://example.test/calm-bed",
                "local_path": "calm-bed.mp3",
                "mood": ["calm", "travel"],
                "pace": "slow",
                "duration": 120,
                "instrumental": True,
                "commercial_use": True,
                "attribution_required": False,
                "license_url": "https://example.test/license",
                "license_evidence": "captured",
            },
        ]
        selected = select_track(
            tracks,
            project_text="calm travel footage",
            mode="silent-footage",
            duration=90,
        )
        self.assertEqual(selected["id"], "calm-bed")

    def test_selector_rejects_missing_commercial_or_attribution_clearance(self) -> None:
        track = {
            "id": "unsafe",
            "title": "Unsafe",
            "provider": "Pixabay",
            "source_url": "https://example.test/unsafe",
            "local_path": "unsafe.mp3",
            "mood": ["calm"],
            "pace": "slow",
            "duration": 60,
            "instrumental": True,
            "commercial_use": False,
            "attribution_required": True,
            "license_url": "",
            "license_evidence": "",
        }
        with self.assertRaisesRegex(ProjectError, "no approved music"):
            select_track([track], project_text="calm", mode="silent-footage", duration=30)

    def test_local_download_preserves_original_and_writes_license_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp3"
            source.write_bytes(b"music")
            destination = root / "project" / "music"
            track = {
                "id": "bed",
                "title": "Bed",
                "provider": "Mixkit",
                "source_url": "https://example.test/bed",
                "local_path": str(source),
                "mood": ["calm"],
                "pace": "slow",
                "duration": 60,
                "instrumental": True,
                "commercial_use": True,
                "attribution_required": False,
                "license_url": "https://example.test/license",
                "license_evidence": "captured",
            }
            copied = download_track(track, destination)
            self.assertEqual(copied.read_bytes(), b"music")
            self.assertEqual(copied.parent, destination)
            record = build_license_record(track, copied)
            self.assertEqual(record["trackId"], "bed")
            self.assertEqual(record["attributionRequired"], False)

    def test_catalog_file_loads_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(
                json.dumps(
                    {
                        "tracks": [
                            {
                                "id": "one",
                                "title": "One",
                                "provider": "Mixkit",
                                "source_url": "https://example.test/one",
                                "mood": [],
                                "pace": "slow",
                                "duration": 30,
                                "instrumental": True,
                                "commercial_use": True,
                                "attribution_required": False,
                                "license_url": "https://example.test/license",
                                "license_evidence": "captured",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_catalog(path)[0]["id"], "one")


if __name__ == "__main__":
    unittest.main()
