from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import unicodedata
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO, Callable
from urllib.parse import parse_qs, quote, unquote, urlparse

from .pipeline.models import ProjectError, SubtitleCue
from .pipeline.planning import MEDIA_EXTENSIONS, build_srt
from .pipeline.subtitle_templates import get_template
from .pipeline.workspace import analyze_clip, render_clip, assistant_proposal, validate_assistant_request, network_readiness
from .pipeline.media import IMAGE_EXTENSIONS, probe_media
from .pipeline.review_render import render_review_assets, render_review_video


APP_HOST = "127.0.0.1"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024 * 1024
MAX_JSON_BYTES = 8 * 1024 * 1024
STATUS_SCHEMA = "shine.workflow.app-status.v1"


def _validate_project_id(project_id: object) -> str:
    if not isinstance(project_id, str):
        raise ProjectError("project ID is required")
    project_id = unicodedata.normalize("NFC", project_id.strip())
    if (
        not project_id
        or project_id in {".", ".."}
        or "/" in project_id
        or "\\" in project_id
        or "\x00" in project_id
        or project_id.startswith(".")
        or len(project_id) > 80
    ):
        raise ProjectError("project ID must be one safe folder name")
    return project_id


def _validate_filename(filename: object) -> str:
    if not isinstance(filename, str) or not filename or len(filename) > 255:
        raise ProjectError("media filename is invalid")
    if Path(filename).name != filename or "/" in filename or "\\" in filename or "\x00" in filename:
        raise ProjectError("media filename must be one safe filename")
    if Path(filename).suffix.lower() not in MEDIA_EXTENSIONS:
        raise ProjectError("unsupported media filename")
    return filename


def _parse_cues(payload: object) -> list[SubtitleCue]:
    if not isinstance(payload, list) or len(payload) > 10_000:
        raise ProjectError("caption cues must be a bounded list")
    cues: list[SubtitleCue] = []
    for row in payload:
        if not isinstance(row, dict) or set(row) != {"start", "end", "text"}:
            raise ProjectError("caption cue fields are invalid")
        start, end, text = row["start"], row["end"], row["text"]
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or not 0 <= start <= 172800
            or not 0 < end <= 172800
            or not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0
            or end <= start
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > 1_000
        ):
            raise ProjectError("caption cue value is invalid")
        if cues and float(start) < cues[-1].end:
            raise ProjectError("caption cues must not overlap")
        cues.append(SubtitleCue(float(start), float(end), text.strip()))
    return cues


Runner = Callable[[str, str, bool], Path]
Opener = Callable[[Path], None]


class WorkflowController:
    def __init__(
        self,
        root: Path,
        *,
        token: str | None = None,
        runner: Runner | None = None,
        opener: Opener | None = None,
    ) -> None:
        self.root = root.resolve()
        self.templates_dir = self.root / "templates"
        self.token = token or secrets.token_urlsafe(32)
        self._runner = runner or self._run_pipeline
        self._opener = opener or self._open_finder
        self._jobs: dict[str, dict[str, object]] = {}
        self._lock = threading.Lock()

    def status_payload(self) -> dict[str, object]:
        return {"schema": STATUS_SCHEMA, "mode": "enhanced", "token": self.token}

    def static_path(self, request_path: str) -> Path:
        parsed = unquote(urlparse(request_path).path)
        allowed = {
            "/": self.templates_dir / "editor.html",
            "/editor.html": self.templates_dir / "editor.html",
            "/catalog.json": self.templates_dir / "catalog.json",
        }
        path = allowed.get(parsed)
        if path is None or not path.is_file():
            raise ProjectError("application resource is not available")
        return path

    def review_static_path(self, request_path: str) -> Path:
        parsed = unquote(urlparse(request_path).path)
        match = re.fullmatch(r"/review/([^/]+)/(editor\.html|sample-preview\.mp4|caption-assets/caption-\d{4}\.png)", parsed)
        if not match:
            raise ProjectError("review resource is not available")
        project_id = _validate_project_id(match.group(1))
        output_root = self.root / "3_output" / project_id
        releases = [(int(version.group(1)), path) for path in output_root.glob("tutorial_v*")
                    if path.is_dir() and (version := re.fullmatch(r"tutorial_v(\d+)", path.name))]
        if not releases:
            raise ProjectError("review release is not available")
        release = max(releases)[1].resolve()
        path = (release / match.group(2)).resolve()
        if not path.is_relative_to(release) or not path.is_file():
            raise ProjectError("review resource is not available")
        return path

    def import_media(
        self,
        project_id: str,
        filename: str,
        stream: BinaryIO,
        content_length: int,
    ) -> Path:
        project_id = _validate_project_id(project_id)
        filename = _validate_filename(filename)
        if (
            isinstance(content_length, bool)
            or not isinstance(content_length, int)
            or content_length < 1
            or content_length > MAX_UPLOAD_BYTES
        ):
            raise ProjectError("media upload size is invalid")
        input_root = (self.root / "1_input").resolve()
        project_dir = (input_root / project_id).resolve()
        if project_dir.parent != input_root:
            raise ProjectError("project path escapes Input")
        project_dir.mkdir(parents=True, exist_ok=True)
        destination = project_dir / filename
        if destination.exists():
            raise ProjectError("input media already exists")

        remaining = content_length
        try:
            with destination.open("xb") as output:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ProjectError("media upload ended early")
                    output.write(chunk)
                    remaining -= len(chunk)
        except Exception:
            if destination.exists():
                destination.unlink()
            raise
        return destination

    def _single_source(self, project_id: str) -> Path:
        folder = self._project_dir(project_id)
        sources = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS]
        if len(sources) != 1 or sources[0].is_symlink():
            raise ProjectError('每支影片必須有自己的 Input，且不能是符號連結。')
        return sources[0]

    def _start_workspace_job(self, project_id: str, kind: str, operation: Callable) -> str:
        job_id = uuid.uuid4().hex
        event = threading.Event()
        with self._lock:
            if any(j.get('projectId') == project_id and j.get('status') == 'running' for j in self._jobs.values()):
                raise ProjectError('這支影片目前仍在處理，請等待完成後重試。')
            self._jobs[job_id] = {'jobId':job_id,'projectId':project_id,'kind':kind,
                                 'status':'running','stage':'process','message':'處理中…','_event':event}
        def progress(message: str) -> None:
            with self._lock: self._jobs[job_id]['message'] = message
        def run() -> None:
            try:
                result = operation(progress)
                fields = {'status':'complete','result':result,'message':'已完成。'}
                if kind in {'render', 'review-export'}:
                    output = Path(result['output']).resolve()
                    expected = (self.root/'3_output'/project_id).resolve()
                    valid_parent = output.parent == expected if kind == 'render' else output.is_relative_to(expected)
                    if not valid_parent or not output.is_file():
                        raise ProjectError('沒有產生有效的獨立 Output。')
                    fields.update({'_output':output,'outputName':output.name,'stage':'output',
                                   'result':{'outputName':output.name}})
                with self._lock: self._jobs[job_id].update(fields)
            except Exception as exc:
                message = str(exc) if isinstance(exc,ProjectError) else '處理失敗，原始資料已保留。'
                with self._lock: self._jobs[job_id].update({'status':'failed','error':message})
            finally: event.set()
        threading.Thread(target=run,daemon=True).start()
        return job_id

    def start_analyze(self, payload: object) -> str:
        if not isinstance(payload,dict) or set(payload) != {'projectId','approved'} or not isinstance(payload['approved'],bool):
            raise ProjectError('影片分析請求無效。')
        project_id = _validate_project_id(payload['projectId'])
        source = self._single_source(project_id)
        if source.suffix.lower() in IMAGE_EXTENSIONS:
            raise ProjectError('照片沒有語音，不需要語音辨識；請手動新增字幕。')
        if payload['approved'] and not source.with_suffix('.srt').is_file():
            readiness = network_readiness()
            if not readiness['transcriptionReady']: raise ProjectError(readiness['message'])
        return self._start_workspace_job(project_id,'analyze',lambda progress: analyze_clip(
            source,self.root/'2_processing'/project_id,approved=payload['approved'],progress=progress))

    def start_render(self, payload: object) -> str:
        if not isinstance(payload,dict) or set(payload) not in ({'projectId','templateId','cues'}, {'projectId','templateId','cues','stillDuration'}):
            raise ProjectError('影片輸出請求無效。')
        project_id = _validate_project_id(payload['projectId'])
        source = self._single_source(project_id)
        if not isinstance(payload['templateId'],str): raise ProjectError('字幕模板無效。')
        get_template(payload['templateId'])
        cues = _parse_cues(payload['cues'])
        is_photo = source.suffix.lower() in IMAGE_EXTENSIONS
        if not cues and not is_photo: raise ProjectError('請先完成這支影片的字幕。')
        if 'stillDuration' in payload and not is_photo: raise ProjectError('只有照片可以設定顯示時間。')
        options = {'still_duration':payload.get('stillDuration',5)} if is_photo else {}
        return self._start_workspace_job(project_id,'render',lambda progress: {'output':str(render_clip(
            source,self.root/'3_output'/project_id,self.root/'2_processing'/project_id,
            project_id,cues,payload['templateId'],**options))})

    def start_assistant(self, payload: object) -> str:
        request = validate_assistant_request(payload)
        return self._start_workspace_job('assistant-' + uuid.uuid4().hex,'assistant',
                                          lambda progress: assistant_proposal(request))

    def start_review_assets(self, payload: object) -> str:
        if not isinstance(payload, dict) or set(payload) != {"projectId", "document"}:
            raise ProjectError("字幕預覽請求無效。")
        project_id = _validate_project_id(payload["projectId"])
        source = self._single_source(project_id)
        document = payload["document"]
        if not isinstance(document, dict) or document.get("source") != source.name:
            raise ProjectError("字幕工作檔與 Input 影片不符。")
        info = probe_media(source)
        return self._start_workspace_job(
            project_id, "review-assets",
            lambda progress: render_review_assets(document, info, self.root / "2_processing" / project_id),
        )

    def start_review_export(self, payload: object) -> str:
        if not isinstance(payload, dict) or set(payload) != {"projectId", "document"}:
            raise ProjectError("字幕成品請求無效。")
        project_id = _validate_project_id(payload["projectId"])
        source = self._single_source(project_id)
        document = payload["document"]
        if not isinstance(document, dict) or document.get("source") != source.name:
            raise ProjectError("字幕工作檔與 Input 影片不符。")
        info = probe_media(source)
        output_root = self.root / "3_output" / project_id
        versions = [int(match.group(1)) for path in output_root.glob("tutorial_v*")
                    if path.is_dir() and (match := re.fullmatch(r"tutorial_v(\d+)", path.name))]
        version = max(versions, default=0) + 1
        release = output_root / f"tutorial_v{version}"
        output = release / f"{project_id}_v{version}_captioned.mp4"
        def export(progress: Callable[[str], None]) -> dict[str, object]:
            progress("正在使用與預覽相同的字幕圖片輸出成品…")
            manifest = render_review_video(source, document, info,
                                           self.root / "2_processing" / project_id, output)
            work = release / f"{project_id}_v{version}.subtitle-workspace.json"
            work.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return {"output": str(output), "fingerprint": manifest["fingerprint"]}
        return self._start_workspace_job(project_id, "review-export", export)

    def review_asset_path(self, project_id: object, fingerprint: object, filename: object) -> Path:
        project_id = _validate_project_id(project_id)
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ProjectError("字幕素材識別碼無效。")
        if not isinstance(filename, str) or not re.fullmatch(r"(?:caption-\d{4}|blank)\.png", filename):
            raise ProjectError("字幕素材檔名無效。")
        directory = (self.root / "2_processing" / project_id / "review-assets" / fingerprint).resolve()
        path = (directory / filename).resolve()
        if path.parent != directory or not path.is_file():
            raise ProjectError("字幕素材不存在。")
        return path

    def _project_dir(self, project_id: str) -> Path:
        project_id = _validate_project_id(project_id)
        input_root = (self.root / "1_input").resolve()
        project_dir = (input_root / project_id).resolve()
        if project_dir.parent != input_root or not project_dir.is_dir():
            raise ProjectError("Input project does not exist")
        return project_dir

    def _save_reviewed_cues(self, project_id: str, cues: list[SubtitleCue]) -> Path:
        project_dir = self._project_dir(project_id)
        media = sorted(
            path for path in project_dir.iterdir()
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS
        )
        if len(media) != 1:
            raise ProjectError("the v1 app requires exactly one imported media file")
        subtitle = project_dir / f"{media[0].stem}.srt"
        subtitle.write_text(build_srt(cues, duration=cues[-1].end), encoding="utf-8")
        return subtitle

    def start_process(self, payload: object) -> str:
        if not isinstance(payload, dict) or set(payload) != {
            "projectId",
            "templateId",
            "cues",
            "approveNetworkTranscription",
        }:
            raise ProjectError("process request fields are invalid")
        project_id = _validate_project_id(payload["projectId"])
        template_id = payload["templateId"]
        if not isinstance(template_id, str):
            raise ProjectError("template ID is required")
        catalog_path = self.templates_dir / "catalog.json"
        get_template(template_id, catalog_path if catalog_path.is_file() else None)
        approve_network = payload["approveNetworkTranscription"]
        if not isinstance(approve_network, bool):
            raise ProjectError("network transcription approval must be explicit")
        self._project_dir(project_id)
        cues = _parse_cues(payload["cues"])
        if cues:
            self._save_reviewed_cues(project_id, cues)
        elif not approve_network:
            raise ProjectError("automatic transcription requires explicit approval for this video")

        settings = {
            "background_music": False,
            "mode": "tutorial",
            "subtitle_template": template_id,
        }
        (self._project_dir(project_id) / "settings.json").write_text(
            json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        job_id = uuid.uuid4().hex
        event = threading.Event()
        with self._lock:
            self._jobs[job_id] = {
                "jobId": job_id,
                "projectId": project_id,
                "status": "running",
                "stage": "process",
                "message": "正在執行字幕與影片處理…",
                "_event": event,
            }
        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, project_id, template_id, approve_network),
            daemon=True,
        )
        thread.start()
        return job_id

    def _run_job(
        self, job_id: str, project_id: str, template_id: str, approve_network: bool
    ) -> None:
        try:
            output = self._runner(project_id, template_id, approve_network).resolve()
            expected_dir = (self.root / "3_output" / project_id).resolve()
            if output.parent != expected_dir or not output.is_file():
                raise ProjectError("pipeline did not create the expected Output")
            with self._lock:
                job = self._jobs[job_id]
                job.update(
                    {
                        "status": "complete",
                        "stage": "output",
                        "message": "影片與字幕已完成。",
                        "outputName": output.name,
                        "_output": output,
                    }
                )
        except Exception as exc:
            with self._lock:
                job = self._jobs[job_id]
                job.update(
                    {
                        "status": "failed",
                        "stage": "process",
                        "message": "處理未完成，Input 已保留。",
                        "error": str(exc) if isinstance(exc, ProjectError) else "video processing failed",
                    }
                )
        finally:
            with self._lock:
                event = self._jobs[job_id]["_event"]
            assert isinstance(event, threading.Event)
            event.set()

    def job_payload(self, job_id: str) -> dict[str, object]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ProjectError("unknown processing job")
            return {key: value for key, value in job.items() if not key.startswith("_")}

    def wait_for_job(self, job_id: str, timeout: float) -> dict[str, object]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ProjectError("unknown processing job")
            event = job["_event"]
        assert isinstance(event, threading.Event)
        if not event.wait(timeout):
            raise ProjectError("processing job did not finish in time")
        return self.job_payload(job_id)

    def open_output(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.get("status") != "complete" or "_output" not in job:
                raise ProjectError("Output is not ready")
            output = job["_output"]
        assert isinstance(output, Path)
        self._opener(output.parent)

    def _run_pipeline(self, project_id: str, template_id: str, allow_network: bool) -> Path:
        output_dir = self.root / "3_output" / project_id
        before = set(output_dir.glob(f"{project_id}_v*.mp4")) if output_dir.exists() else set()
        environment = os.environ.copy()
        if allow_network:
            environment["AI_VIDEO_ALLOW_NETWORK"] = "1"
        else:
            environment.pop("AI_VIDEO_ALLOW_NETWORK", None)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "system.pipeline.cli",
                project_id,
                "--root",
                str(self.root),
            ],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ProjectError("video pipeline failed; Input was preserved")
        after = set(output_dir.glob(f"{project_id}_v*.mp4")) if output_dir.exists() else set()
        created = sorted(after - before, key=lambda path: path.stat().st_mtime)
        if not created:
            raise ProjectError("video pipeline produced no new Output")
        return created[-1]

    @staticmethod
    def _open_finder(path: Path) -> None:
        subprocess.run(
            ["open", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def _handler(controller: WorkflowController) -> type[BaseHTTPRequestHandler]:
    class WorkflowHandler(BaseHTTPRequestHandler):
        server_version = "ShineWorkflow/1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            query_token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
            return secrets.compare_digest(self.headers.get("X-Workflow-Token", ""), controller.token) or secrets.compare_digest(query_token, controller.token)

        def _require_authorized(self) -> bool:
            if self._authorized():
                return True
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "local workflow token is invalid"})
            return False

        def _read_json(self) -> object:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise ProjectError("request length is required")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ProjectError("request length is invalid") from exc
            if length < 1 or length > MAX_JSON_BYTES:
                raise ProjectError("JSON request size is invalid")
            try:
                return json.loads(self.rfile.read(length))
            except json.JSONDecodeError as exc:
                raise ProjectError("JSON request is invalid") from exc

        def do_GET(self) -> None:
            try:
                parsed = urlparse(self.path)
                if parsed.path == "/api/status":
                    self._send_json(HTTPStatus.OK, controller.status_payload())
                    return
                if parsed.path == '/api/capabilities':
                    if not self._require_authorized(): return
                    self._send_json(HTTPStatus.OK, network_readiness())
                    return
                if parsed.path.startswith("/api/jobs/"):
                    if not self._require_authorized():
                        return
                    job_id = parsed.path.removeprefix("/api/jobs/")
                    self._send_json(HTTPStatus.OK, controller.job_payload(job_id))
                    return
                if parsed.path.startswith("/api/review/assets/"):
                    if not self._require_authorized(): return
                    parts = parsed.path.split("/")
                    if len(parts) != 7:
                        raise ProjectError("字幕素材路徑無效。")
                    path = controller.review_asset_path(parts[4], parts[5], parts[6])
                    body = path.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers(); self.wfile.write(body); return
                if parsed.path.startswith("/review/"):
                    path = controller.review_static_path(self.path)
                    body = path.read_bytes()
                    content_type = "text/html; charset=utf-8" if path.suffix == ".html" else "video/mp4" if path.suffix == ".mp4" else "image/png"
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers(); self.wfile.write(body); return
                path = controller.static_path(self.path)
                body = path.read_bytes()
                content_type = (
                    "text/html; charset=utf-8"
                    if path.suffix == ".html"
                    else "application/json; charset=utf-8"
                )
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.end_headers()
                self.wfile.write(body)
            except ProjectError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})

        def do_POST(self) -> None:
            if not self._require_authorized():
                return
            try:
                parsed = urlparse(self.path)
                if parsed.path == "/api/import":
                    query = parse_qs(parsed.query, strict_parsing=True)
                    project = query.get("project", [None])[0]
                    filename = query.get("filename", [None])[0]
                    raw_length = self.headers.get("Content-Length")
                    if raw_length is None:
                        raise ProjectError("media upload length is required")
                    try:
                        length = int(raw_length)
                    except ValueError as exc:
                        raise ProjectError("media upload length is invalid") from exc
                    imported = controller.import_media(project, filename, self.rfile, length)  # type: ignore[arg-type]
                    self._send_json(HTTPStatus.CREATED, {"status": "input", "name": imported.name})
                    return
                if parsed.path == "/api/process":
                    job_id = controller.start_process(self._read_json())
                    self._send_json(HTTPStatus.ACCEPTED, {"jobId": job_id})
                    return
                if parsed.path in {'/api/analyze','/api/render','/api/assistant','/api/review/render-assets','/api/review/export'}:
                    action = {'/api/analyze':controller.start_analyze,
                              '/api/render':controller.start_render,
                              '/api/assistant':controller.start_assistant,
                              '/api/review/render-assets':controller.start_review_assets,
                              '/api/review/export':controller.start_review_export}[parsed.path]
                    self._send_json(HTTPStatus.ACCEPTED, {'jobId':action(self._read_json())})
                    return
                if parsed.path == "/api/open-output":
                    payload = self._read_json()
                    if not isinstance(payload, dict) or set(payload) != {"jobId"} or not isinstance(payload["jobId"], str):
                        raise ProjectError("open Output request is invalid")
                    controller.open_output(payload["jobId"])
                    self._send_json(HTTPStatus.OK, {"status": "opened"})
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown local workflow action"})
            except (ProjectError, ValueError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    return WorkflowHandler


def create_server(controller: WorkflowController, *, port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((APP_HOST, port), _handler(controller))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Video Workflow v1 local controller")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--review-project")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    controller = WorkflowController(args.root)
    server = create_server(controller, port=args.port)
    review_path = "/"
    if args.review_project:
        project_id = _validate_project_id(args.review_project)
        controller.review_static_path(f"/review/{quote(project_id)}/editor.html")
        review_path = f"/review/{quote(project_id)}/editor.html"
    url = f"http://{APP_HOST}:{server.server_address[1]}{review_path}"
    if not args.no_open:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()
    print("AI Video Workflow v1 is running locally; close this window to stop it.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
