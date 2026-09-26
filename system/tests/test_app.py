from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from system.app import APP_HOST, MAX_UPLOAD_BYTES, WorkflowController, create_server
from system.pipeline.models import ProjectError


class LocalWorkflowControllerTests(unittest.TestCase):
    def test_server_binds_only_to_loopback_and_status_uses_launch_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = WorkflowController(Path(directory), token="test-token")
            server = create_server(controller, port=0)
            try:
                self.assertEqual(APP_HOST, "127.0.0.1")
                self.assertEqual(server.server_address[0], APP_HOST)
                self.assertEqual(
                    controller.status_payload(),
                    {
                        "schema": "shine.workflow.app-status.v1",
                        "mode": "enhanced",
                        "token": "test-token",
                    },
                )
            finally:
                server.server_close()

    def test_static_surface_is_allowlisted_and_rejects_traversal(self) -> None:
        root = Path(__file__).resolve().parents[2]
        controller = WorkflowController(root, token="test-token")
        self.assertEqual(controller.static_path("/").name, "editor.html")
        self.assertEqual(controller.static_path("/catalog.json").name, "catalog.json")
        for path in ("/../AGENTS.md", "/system/app.py", "/unknown", "/templates/../README.md"):
            with self.assertRaises(ProjectError, msg=path):
                controller.static_path(path)

    def test_review_surface_serves_only_latest_allowlisted_release_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for version in (1, 2):
                release = root / "3_output" / "lesson" / f"tutorial_v{version}"
                (release / "caption-assets").mkdir(parents=True)
                (release / "editor.html").write_text(str(version))
                (release / "sample-preview.mp4").touch()
                (release / "caption-assets/caption-0001.png").touch()
            controller = WorkflowController(root, token="test-token")
            self.assertEqual(controller.review_static_path("/review/lesson/editor.html").read_text(), "2")
            self.assertEqual(controller.review_static_path("/review/lesson/caption-assets/caption-0001.png").name,
                             "caption-0001.png")
            for path in ("/review/../editor.html", "/review/lesson/../editor.html", "/review/lesson/private.json"):
                with self.assertRaises(ProjectError):
                    controller.review_static_path(path)

    def test_import_accepts_one_supported_media_file_inside_one_safe_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = WorkflowController(root, token="test-token")
            imported = controller.import_media(
                project_id="草間彌生展覽",
                filename="展覽片段.mp4",
                stream=io.BytesIO(b"synthetic-video"),
                content_length=len(b"synthetic-video"),
            )
            self.assertEqual(
                imported,
                (root / "1_input" / "草間彌生展覽" / "展覽片段.mp4").resolve(),
            )
            self.assertEqual(imported.read_bytes(), b"synthetic-video")

            for project_id, filename in (("../escape", "a.mp4"), ("safe", "../a.mp4"), ("safe", "notes.txt")):
                with self.assertRaises(ProjectError):
                    controller.import_media(
                        project_id=project_id,
                        filename=filename,
                        stream=io.BytesIO(b"x"),
                        content_length=1,
                    )

    def test_import_rejects_empty_oversized_and_overwriting_requests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            controller = WorkflowController(Path(directory), token="test-token")
            with self.assertRaises(ProjectError):
                controller.import_media("safe", "a.mp4", io.BytesIO(), 0)
            with self.assertRaises(ProjectError):
                controller.import_media(
                    "safe", "a.mp4", io.BytesIO(b"x"), MAX_UPLOAD_BYTES + 1
                )
            controller.import_media("safe", "a.mp4", io.BytesIO(b"x"), 1)
            with self.assertRaisesRegex(ProjectError, "already exists"):
                controller.import_media("safe", "a.mp4", io.BytesIO(b"y"), 1)

    def test_process_requires_reviewed_cues_or_explicit_network_approval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = WorkflowController(root, token="test-token")
            controller.import_media("lesson", "lesson.mp4", io.BytesIO(b"x"), 1)
            with self.assertRaisesRegex(ProjectError, "explicit"):
                controller.start_process(
                    {
                        "projectId": "lesson",
                        "templateId": "S01",
                        "cues": [],
                        "approveNetworkTranscription": False,
                    }
                )

    def test_successful_job_saves_reviewed_srt_and_only_then_opens_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            opened: list[Path] = []

            def runner(project_id: str, template_id: str, allow_network: bool) -> Path:
                self.assertEqual((project_id, template_id, allow_network), ("lesson", "S01", False))
                output_dir = root / "3_output" / project_id
                output_dir.mkdir(parents=True)
                output = output_dir / "lesson_v1.mp4"
                output.touch()
                return output

            controller = WorkflowController(
                root,
                token="test-token",
                runner=runner,
                opener=lambda path: opened.append(path),
            )
            controller.import_media("lesson", "lesson.mp4", io.BytesIO(b"x"), 1)
            job_id = controller.start_process(
                {
                    "projectId": "lesson",
                    "templateId": "S01",
                    "cues": [
                        {"start": 0.0, "end": 1.25, "text": "第一句"},
                        {"start": 1.25, "end": 2.5, "text": "第二句"},
                    ],
                    "approveNetworkTranscription": False,
                }
            )
            job = controller.wait_for_job(job_id, timeout=2)
            self.assertEqual(job["status"], "complete")
            self.assertEqual(job["stage"], "output")
            self.assertTrue((root / "1_input" / "lesson" / "lesson.srt").is_file())
            self.assertEqual(
                (root / "1_input" / "lesson" / "settings.json").read_text(encoding="utf-8"),
                '{\n  "background_music": false,\n  "mode": "tutorial",\n  "subtitle_template": "S01"\n}\n',
            )
            controller.open_output(job_id)
            self.assertEqual(opened, [(root / "3_output" / "lesson").resolve()])

    def test_failed_job_never_opens_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def fail_runner(project_id: str, template_id: str, allow_network: bool) -> Path:
                raise ProjectError("synthetic failure")

            controller = WorkflowController(root, token="test-token", runner=fail_runner)
            controller.import_media("lesson", "lesson.mp4", io.BytesIO(b"x"), 1)
            job_id = controller.start_process(
                {
                    "projectId": "lesson",
                    "templateId": "S01",
                    "cues": [{"start": 0.0, "end": 1.0, "text": "字幕"}],
                    "approveNetworkTranscription": False,
                }
            )
            job = controller.wait_for_job(job_id, timeout=2)
            self.assertEqual(job["status"], "failed")
            with self.assertRaises(ProjectError):
                controller.open_output(job_id)

    def test_review_asset_job_is_token_scoped_and_never_accepts_client_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = WorkflowController(root, token="test-token")
            controller.import_media("lesson", "lesson.mp4", io.BytesIO(b"x"), 1)
            document = {
                "schema": "shine.project-subtitle-review.v2", "revision": 2,
                "source": "lesson.mp4", "duration": 2.0,
                "style": {"fontFamily": "PingFang TC", "sizePct": 4.0, "weight": 900,
                          "color": "#FFFFFF", "strokePct": 0.07,
                          "strokeColor": "#000000", "bottomPct": 8.0},
                "cues": [{"id": 1, "start": 0.0, "end": 2.0, "text": "字幕",
                          "runs": [{"text": "字幕", "style": {}}]}],
            }
            rendered = {"schema": "shine.review-assets.v1", "fingerprint": "a" * 64,
                        "width": 640, "height": 360,
                        "cues": [{"id": 1, "start": 0, "end": 2,
                                  "asset": "review-assets/" + "a" * 64 + "/caption-0001.png"}]}
            with patch("system.app.probe_media"), patch("system.app.render_review_assets", return_value=rendered):
                job_id = controller.start_review_assets({"projectId": "lesson", "document": document})
                job = controller.wait_for_job(job_id, 2)
            self.assertEqual(job["status"], "complete")
            self.assertEqual(job["result"], rendered)
            with self.assertRaises(ProjectError):
                controller.start_review_assets({"projectId": "../lesson", "document": document})

            def export(source, document, info, processing, output):
                output.parent.mkdir(parents=True, exist_ok=True)
                output.touch()
                return rendered
            with patch("system.app.probe_media"), patch("system.app.render_review_video", side_effect=export):
                export_id = controller.start_review_export({"projectId": "lesson", "document": document})
                exported = controller.wait_for_job(export_id, 2)
            self.assertEqual(exported["status"], "complete")
            self.assertEqual(exported["outputName"], "lesson_v1_captioned.mp4")
            self.assertTrue((root / "3_output/lesson/tutorial_v1/lesson_v1.subtitle-workspace.json").is_file())


if __name__ == "__main__":
    unittest.main()
