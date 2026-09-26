from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class StructureContractTests(unittest.TestCase):
    def test_defaults_preserve_source_and_original_audio(self) -> None:
        defaults = json.loads(
            (ROOT / "system/config/defaults.json").read_text(encoding="utf-8")
        )
        self.assertEqual(defaults["aspect_ratio"], "original")
        self.assertEqual(defaults["audio_mode"], "original-audio")
        self.assertTrue(defaults["subtitles"]["burn_in"])
        self.assertTrue(defaults["subtitles"]["export_srt"])

    def test_ai_narration_is_reserved_but_disabled(self) -> None:
        modes = json.loads(
            (ROOT / "system/config/modes.json").read_text(encoding="utf-8")
        )
        self.assertFalse(modes["future"]["ai-narration"]["enabled"])
        self.assertTrue(modes["future"]["ai-narration"]["requires_explicit_consent"])

    def test_owner_runner_delegates_to_active_python_module(self) -> None:
        runner_path = ROOT / "AI Video Workflow v7.command"
        runner = runner_path.read_text(encoding="utf-8")
        self.assertIn("python3 -m system.app", runner)
        self.assertNotIn(".ps1", runner)
        self.assertTrue(os.access(runner_path, os.X_OK))

    def test_minimal_owner_folders_are_declared(self) -> None:
        for name in ("1_input", "2_processing", "3_output", "system"):
            self.assertTrue((ROOT / name).is_dir(), name)

    def test_current_owner_surface_uses_one_versioned_launcher_and_one_template_area(self) -> None:
        self.assertTrue((ROOT / "AI Video Workflow v7.command").is_file())
        self.assertTrue((ROOT / "templates/editor.html").is_file())
        for name in (
            "AGENTS (1).md",
            "AGENTS.md",
            "CONTEXT.md",
            "HANDOFF.md",
            "docs",
            "guide.html",
            "index.md",
            "requirements.txt",
            "run-video",
        ):
            self.assertFalse((ROOT / name).exists(), name)

    def test_retired_entry_folders_are_not_at_repository_root(self) -> None:
        for name in ("_agent", "_meta", "_human", "scripts", "skills", "tests", "tools", "references"):
            self.assertFalse((ROOT / name).exists(), name)

    def test_active_entry_docs_do_not_describe_the_retired_workspace(self) -> None:
        active = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("2_workspace", active)
        self.assertIn("2_processing", active)

    def test_agents_requires_same_task_updates_and_lowercase_versions(self) -> None:
        agents = (ROOT.parent / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(
            "Record every material repository behavior or governance change in this file before completion",
            agents,
        )
        self.assertIn("每項實質 repository 行為或治理變更都必須在完成前記錄於本檔案", agents)
        self.assertIn("vlog_vN/", agents)
        self.assertNotRegex(agents, r"_V(?:\d|N|n)")
        self.assertIn("S01 `貼字黑底`", agents)

    def test_agents_preserves_governed_workflow_and_safety_contract(self) -> None:
        agents = (ROOT.parent / "AGENTS.md").read_text(encoding="utf-8")
        required_terms = (
            "1_input -> 2_processing -> 3_output",
            ".env",
            "GROQ_API_KEY",
            "127.0.0.1",
            "mature",
            "testing",
            "10 Chinese characters",
            "16 for landscape",
            "same AppKit pass",
            "generated media",
        )
        for term in required_terms:
            self.assertIn(term, agents, term)


if __name__ == "__main__":
    unittest.main()
