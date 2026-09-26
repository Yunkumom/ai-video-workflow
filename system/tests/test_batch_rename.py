import json
import tempfile
import unittest
from pathlib import Path

from system.pipeline.batch_rename import (
    build_rename_manifest,
    execute_rename_manifest,
    rollback_renames,
)


class BatchRenameTests(unittest.TestCase):
    def test_dry_run_manifest_and_sidecar_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "IMG_1001.MOV").write_bytes(b"mov-data")
            (folder / "IMG_1001.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            (folder / "IMG_1002.JPG").write_bytes(b"jpg-data")
            (folder / "ignore_me.txt").write_text("notes", encoding="utf-8")

            manifest = build_rename_manifest(folder, subject="campus_entrance")

            self.assertEqual(manifest["total_media_count"], 2)
            self.assertEqual(manifest["subject"], "campus_entrance")

            items = manifest["items"]
            # Check media items
            names = [it["new_name"] for it in items]
            self.assertTrue(any("campus_entrance_001" in n for n in names))
            self.assertTrue(any("campus_entrance_002" in n for n in names))

            # Check that IMG_1001 has sidecar IMG_1001.srt
            item_mov = next(it for it in items if it["original_name"] == "IMG_1001.MOV")
            self.assertEqual(len(item_mov["sidecars"]), 1)
            self.assertEqual(item_mov["sidecars"][0]["original_name"], "IMG_1001.srt")
            self.assertTrue(item_mov["sidecars"][0]["new_name"].endswith(".srt"))
            self.assertEqual(Path(item_mov["sidecars"][0]["new_name"]).stem, Path(item_mov["new_name"]).stem)

    def test_apply_and_rollback_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            v = folder / "clip1.mp4"
            v.write_bytes(b"video-1")
            s = folder / "clip1.srt"
            s.write_text("sub-1", encoding="utf-8")

            manifest = build_rename_manifest(folder, subject="test_clip")
            res = execute_rename_manifest(manifest)

            self.assertEqual(res["status"], "success")
            self.assertEqual(res["renamed_count"], 2)

            # Original files should no longer exist under original names
            self.assertFalse(v.exists())
            self.assertFalse(s.exists())

            # New files should exist
            new_v = Path(manifest["items"][0]["new_path"])
            new_s = Path(manifest["items"][0]["sidecars"][0]["new_path"])
            self.assertTrue(new_v.exists())
            self.assertTrue(new_s.exists())
            self.assertEqual(new_v.read_bytes(), b"video-1")
            self.assertEqual(new_s.read_text(encoding="utf-8"), "sub-1")

            # Rollback
            rollback_res = rollback_renames(Path(res["rollback_file"]))
            self.assertEqual(rollback_res["status"], "rolled_back")
            self.assertEqual(rollback_res["reverted_count"], 2)

            # Files are restored
            self.assertTrue(v.exists())
            self.assertTrue(s.exists())
            self.assertFalse(new_v.exists())
            self.assertFalse(new_s.exists())


if __name__ == "__main__":
    unittest.main()
