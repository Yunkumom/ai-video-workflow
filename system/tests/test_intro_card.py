import subprocess
import tempfile
import unittest
from pathlib import Path

class IntroCardTests(unittest.TestCase):
    def test_intro_card_render_vertical_and_horizontal(self):
        root = Path(__file__).resolve().parents[2]
        script = root / "system" / "pipeline" / "intro_card.swift"
        self.assertTrue(script.exists(), "intro_card.swift must exist")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Create a small dummy image using ffmpeg or sips
            dummy_img = tmp / "test_input.png"
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=green:s=720x1280",
                "-frames:v", "1", str(dummy_img)
            ], check=True, capture_output=True)

            out_v = tmp / "intro_v.png"
            res_v = subprocess.run([
                "swift", str(script),
                "--input", str(dummy_img),
                "--output", str(out_v),
                "--title", "TEST TITLE",
                "--subtitle", "Test Subtitle",
                "--category", "TEST CATEGORY",
                "--orientation", "vertical"
            ], capture_output=True, text=True)
            self.assertEqual(res_v.returncode, 0, f"Vertical render failed: {res_v.stderr}")
            self.assertTrue(out_v.exists())

            # Check dimensions via sips
            dim_v = subprocess.run(
                ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(out_v)],
                capture_output=True, text=True, check=True
            ).stdout
            self.assertIn("1080", dim_v)
            self.assertIn("1920", dim_v)

            out_h = tmp / "intro_h.png"
            res_h = subprocess.run([
                "swift", str(script),
                "--input", str(dummy_img),
                "--output", str(out_h),
                "--title", "HORIZONTAL TEST",
                "--orientation", "horizontal"
            ], capture_output=True, text=True)
            self.assertEqual(res_h.returncode, 0, f"Horizontal render failed: {res_h.stderr}")
            self.assertTrue(out_h.exists())

            dim_h = subprocess.run(
                ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(out_h)],
                capture_output=True, text=True, check=True
            ).stdout
            self.assertIn("1920", dim_h)
            self.assertIn("1080", dim_h)

if __name__ == "__main__":
    unittest.main()
