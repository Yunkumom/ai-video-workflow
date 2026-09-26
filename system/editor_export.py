"""Project-scoped local export bridge for the standalone subtitle editor.

No external services, arbitrary input paths, or changes to the batch controller.
Only a fully validated pair of MP4s becomes downloadable. Failed work stays local.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import secrets
import subprocess
import tempfile
import threading
import uuid
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .pipeline.media import probe_media, require_tool
from .pipeline.models import ProjectError

LIMIT = 8 * 1024 * 1024
SIZES = {'horizontal': (1920, 1080), 'vertical': (1080, 1920)}


def number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ProjectError('字幕數值超出範圍。')
    return value


def keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected.split()):
        raise ProjectError('字幕工作檔欄位無效。')


def normalize_editor(document):
    """Return the current document shape without mutating a saved work copy."""
    if not isinstance(document, dict):
        raise ProjectError('字幕工作檔欄位無效。')
    if document.get('schema') == 'shine.project-subtitle-review.v2' and document.get('revision') == 2:
        migrated = copy.deepcopy(document)
        if set(migrated) != set('schema revision source duration styles cues'.split()):
            raise ProjectError('字幕工作檔欄位無效。')
        migrated.update(schema='shine.project-subtitle-review.v3', revision=3)
        migrated['framing'] = {'vertical': {'segments': [{
            'start': 0.0, 'end': migrated.get('duration'), 'mode': 'extend', 'positionX': 0.5
        }]}}
        return migrated
    return copy.deepcopy(document)


def crop_geometry(width, height, position_x):
    """Calculate an even-pixel 9:16 crop with normalized horizontal travel."""
    if type(width) is not int or type(height) is not int or width < 2 or height < 2:
        raise ProjectError('來源影片尺寸無效。')
    position_x = number(position_x, 0, 1)
    crop_width = min(width, int(height * 9 / 16) // 2 * 2)
    crop_height = min(height, int(width * 16 / 9) // 2 * 2)
    travel = max(0, width - crop_width)
    x = int(travel * position_x) // 2 * 2
    return x, 0, crop_width, crop_height


def validate_editor(document):
    document = normalize_editor(document)
    keys(document, 'schema revision source duration styles cues framing')
    if document['schema'] != 'shine.project-subtitle-review.v3' or type(document['revision']) is not int or document['revision'] != 3:
        raise ProjectError('字幕工作檔版本無效。')
    if document['source'] != 'sample.mov':
        raise ProjectError('請使用此專案的原始 sample.mov。')
    duration = number(document['duration'], .001, 86400)
    keys(document['styles'], 'horizontal vertical')
    for style in document['styles'].values():
        keys(style, 'font size weight stroke')
        if style['font'] not in ('PingFang TC', 'Arial', 'Heiti TC') or style['weight'] not in (700, 800, 900):
            raise ProjectError('字幕字型或粗細無效。')
        number(style['size'], 2, 20); number(style['stroke'], .02, .2)
    keys(document['framing'], 'vertical')
    keys(document['framing']['vertical'], 'segments')
    segments = document['framing']['vertical']['segments']
    if not isinstance(segments, list) or not 1 <= len(segments) <= 1000:
        raise ProjectError('直式構圖區段無效。')
    cursor = 0.0
    for segment in segments:
        keys(segment, 'start end mode positionX')
        start = number(segment['start'], 0, duration)
        stop = number(segment['end'], 0, duration)
        if abs(start - cursor) > .00001 or stop <= start:
            raise ProjectError('直式構圖區段必須連續且不可重疊。')
        if segment['mode'] not in ('crop', 'extend'):
            raise ProjectError('直式構圖模式無效。')
        number(segment['positionX'], 0, 1)
        cursor = stop
    if abs(cursor - duration) > .00001:
        raise ProjectError('直式構圖區段必須涵蓋完整影片。')
    cues = document['cues']
    if not isinstance(cues, list) or not 1 <= len(cues) <= 10000:
        raise ProjectError('字幕數量無效。')
    end = 0; ids = set()
    for cue in cues:
        keys(cue, 'id start end text original note size runs')
        if type(cue['id']) is not int or cue['id'] in ids:
            raise ProjectError('字幕識別碼重複或無效。')
        ids.add(cue['id'])
        start = number(cue['start'], 0, duration)
        stop = number(cue['end'], 0, duration)
        if start < end or stop <= start:
            raise ProjectError('字幕時間重疊或無效。')
        end = stop
        for field, maximum in [('text', 2000), ('original', 2000), ('note', 4000)]:
            if not isinstance(cue[field], str) or len(cue[field]) > maximum:
                raise ProjectError('字幕文字過長或無效。')
        if not cue['text'].strip(): raise ProjectError('字幕不可空白。')
        if cue['size'] is not None: number(cue['size'], .5, 2)
        if not isinstance(cue['runs'], list) or not 1 <= len(cue['runs']) <= 2000:
            raise ProjectError('字詞樣式無效。')
        for run in cue['runs']:
            keys(run, 'text scale')
            if not isinstance(run['text'], str) or not run['text']:
                raise ProjectError('字詞不可空白。')
            number(run['scale'], .5, 3)
        if ''.join(r['text'] for r in cue['runs']) != cue['text']:
            raise ProjectError('字幕與字詞格式不一致，請重新編輯該句。')
    try:
        if len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode()) > LIMIT:
            raise ProjectError('工作檔超過 8 MB。')
    except (ValueError, UnicodeError) as exc:
        raise ProjectError('工作檔字元或數值無效。') from exc
    return copy.deepcopy(document)


def native_document(document, mode):
    document = validate_editor(document)
    if mode not in SIZES: raise ProjectError('輸出方向無效。')
    style = document['styles'][mode]
    return {'style': {'fontFamily': style['font'], 'sizePct': style['size'],
                     'weight': style['weight'], 'color': '#FFFFFF', 'strokePct': style['stroke'],
                     'strokeColor': '#000000', 'bottomPct': 8},
            'cues': [{**cue, 'runs': [{'text': run['text'], 'style': {
                'sizeScale': run['scale'] * (cue['size'] if cue['size'] is not None else 1)}}
                for run in cue['runs']]} for cue in document['cues']]}


def verify_movie(path, duration, size, audio):
    result = subprocess.run([require_tool('ffprobe'), '-v', 'error', '-show_streams', '-of', 'json', str(path)],
                            capture_output=True, text=True, check=True, timeout=60)
    streams = json.loads(result.stdout)['streams']
    video = next((s for s in streams if s.get('codec_type') == 'video'), {})
    if (video.get('width'), video.get('height')) != size or video.get('codec_name') != 'h264':
        raise ProjectError('影片尺寸或編碼驗證失敗。')
    video_end = float(video.get('start_time', 0)) + float(video.get('duration', 0))
    if abs(video_end - duration) > .1: raise ProjectError('影片長度驗證失敗。')
    if audio:
        track = next((s for s in streams if s.get('codec_type') == 'audio'), {})
        audio_end = float(track.get('start_time', 0)) + float(track.get('duration', 0))
        if not track or audio_end < video_end - .1:
            raise ProjectError('聲音在影片結束前中斷，未交付此版本。')


def scene_filter(document, mode, info, width, height):
    """Build the source-to-output scene graph before transparent captions."""
    if mode != 'vertical' or info.width <= info.height:
        return (f'[0:v]scale=iw*sar:ih,setsar=1,split=2[bg][fg];'
                f'[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},'
                'gblur=sigma=24,eq=brightness=-0.12[blur];'
                f'[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[front];'
                '[blur][front]overlay=(W-w)/2:(H-h)/2[scene]')
    segments = document['framing']['vertical']['segments']
    graph = [f'[0:v]scale=iw*sar:ih,setsar=1,split={len(segments)}' +
             ''.join(f'[source{i}]' for i in range(len(segments)))]
    outputs = []
    for i, segment in enumerate(segments):
        start, stop = segment['start'], segment['end']
        base = f'[source{i}]trim=start={start:.8f}:end={stop:.8f},setpts=PTS-STARTPTS'
        if segment['mode'] == 'crop':
            crop_width = 'trunc(ih*9/16/2)*2'
            x = f'trunc((iw-({crop_width}))*{segment["positionX"]:.8f}/2)*2'
            graph.append(f'{base},crop=w={crop_width}:h=trunc(ih/2)*2:x={x}:y=0,'
                         f'scale={width}:{height}[segment{i}]')
        else:
            graph.append(f'{base},split=2[bg{i}][fg{i}]')
            graph.append(f'[bg{i}]scale={width}:{height}:force_original_aspect_ratio=increase,'
                         f'crop={width}:{height},gblur=sigma=24,eq=brightness=-0.12[blur{i}]')
            graph.append(f'[fg{i}]scale={width}:{height}:force_original_aspect_ratio=decrease[front{i}]')
            graph.append(f'[blur{i}][front{i}]overlay=(W-w)/2:(H-h)/2[segment{i}]')
        outputs.append(f'[segment{i}]')
    graph.append(''.join(outputs) + f'concat=n={len(outputs)}:v=1:a=0[scene]')
    return ';'.join(graph)


def render_movie(source, document, mode, work, output, progress, *, size=None):
    document = validate_editor(document)
    size = size or SIZES[mode]
    info = probe_media(source)
    if abs(info.duration - document['duration']) > .1:
        raise ProjectError('工作檔與原影片長度不符。')
    width, height = size
    work.mkdir(parents=True, exist_ok=True)
    native = work / 'native.json'
    native.write_text(json.dumps(native_document(document, mode), ensure_ascii=False), encoding='utf-8')
    progress('產生' + ('橫式' if mode == 'horizontal' else '直式') + '字幕…')
    swift_env = os.environ.copy()
    swift_env['CLANG_MODULE_CACHE_PATH'] = str(Path(tempfile.gettempdir()) / 'shine-caption-swift-cache')
    result = subprocess.run([require_tool('swift'), str(Path(__file__).parent / 'pipeline/review_caption_images.swift'),
                             '--input', str(native), '--output-dir', str(work),
                             '--width', str(width), '--height', str(height)],
                            capture_output=True, text=True, timeout=300, env=swift_env)
    if result.returncode:
        raise ProjectError('字幕無法放入畫面或字型不可用，請縮小全片／單句／字詞字級後重試。')
    lines = ['ffconcat version 1.0']; cursor = 0; last = 'blank.png'
    for index, cue in enumerate(document['cues'], 1):
        if cue['start'] > cursor:
            lines += ["file 'blank.png'", f"duration {cue['start'] - cursor:.8f}"]
        last = f'caption-{index:04d}.png'
        lines += [f"file '{last}'", f"duration {cue['end'] - cue['start']:.8f}"]
        cursor = cue['end']
    if cursor < info.duration:
        last = 'blank.png'; lines += ["file 'blank.png'", f'duration {info.duration - cursor:.8f}']
    lines.append(f"file '{last}'")
    (work / 'timeline.ffconcat').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    # Normalize SAR; vertical landscape footage can use fixed framing per time segment.
    graph = (scene_filter(document, mode, info, width, height) +
             ';[1:v]fps=30,format=rgba[captions];'
             '[scene][captions]overlay=0:0:eof_action=repeat,format=yuv420p[out]')
    command = [require_tool('ffmpeg'), '-v', 'error', '-nostdin', '-n', '-filter_complex_threads', '2',
               '-i', str(source), '-f', 'concat', '-safe', '0', '-i', 'timeline.ffconcat',
               '-filter_complex', graph, '-map', '[out]']
    if info.has_audio: command += ['-map', '0:a:0', '-c:a', 'aac', '-b:a', '192k']
    else: command += ['-an']
    command += ['-c:v', 'libx264', '-threads', '4', '-preset', 'veryfast', '-crf', '20', '-r', '30',
                '-t', str(info.duration), '-movflags', '+faststart', '-progress', 'pipe:1', str(output)]
    with (work / 'render.log').open('w') as log:
        process = subprocess.Popen(command, cwd=work, stdout=subprocess.PIPE, stderr=log, text=True)
        # A watchdog prevents a stuck native encoder from keeping a job forever.
        watchdog = threading.Timer(3600, process.kill); watchdog.start()
        try:
            for line in process.stdout:
                if line.startswith('out_time_us='):
                    try: percent = min(99, int(float(line.split('=')[1]) / 1000000 / info.duration * 100))
                    except ValueError: continue
                    progress(('橫式' if mode == 'horizontal' else '直式') + f'影片渲染 {percent}%')
            if process.wait() != 0: raise ProjectError('影片渲染失敗；原影片及前一版已保留。')
        finally:
            watchdog.cancel()
            process.stdout.close()
    verify_movie(output, info.duration, size, info.has_audio)


class ExportController:
    def __init__(self, root, project_id, release_name):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', project_id) or not re.fullmatch(r'tutorial_v\d+', release_name):
            raise ProjectError('專案或版本名稱無效。')
        self.root = Path(root).resolve(); self.project_id = project_id
        self.release = (self.root / '3_output' / project_id / release_name).resolve()
        self.source = (self.root / '1_input' / project_id / 'sample.mov').resolve()
        if not self.release.is_relative_to(self.root / '3_output') or not self.source.is_relative_to(self.root / '1_input'):
            raise ProjectError('專案路徑無效。')
        if not self.source.is_file() or not (self.release / 'editor.html').is_file():
            raise ProjectError('請確認原片與 editor.html 都存在。')
        self.work = self.root / '2_processing' / project_id / 'editor-export'
        if (self.source != self.root / '1_input' / project_id / 'sample.mov' or
                self.release != self.root / '3_output' / project_id / release_name or
                not self.work.resolve().is_relative_to(self.root / '2_processing' / project_id)):
            raise ProjectError('不支援指向其他位置的專案連結。')
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock(); self.jobs = {}; self.downloads = {}; self.history = []
        self.restore_downloads()

    def restore_downloads(self):
        # Only this exporter's exact file family in the explicitly selected release.
        for path in self.release.glob(f'{self.project_id}_horizontal_v*.mp4'):
            match = re.fullmatch(re.escape(self.project_id) + r'_horizontal_v(\d+)\.mp4', path.name)
            if not match: continue
            version = int(match[1]); paths = [self.release / f'{self.project_id}_{mode}_v{version}.mp4' for mode in SIZES]
            if any(p.resolve().parent != self.release or not p.is_file() for p in paths): continue
            try:
                info = probe_media(self.source)
                for p, mode in zip(paths, SIZES): verify_movie(p, info.duration, SIZES[mode], info.has_audio)
            except Exception: continue
            for suffix in ('subtitle-workspace.json', 'editor.html'):
                p = self.release / f'{self.project_id}_v{version}.{suffix}'
                if p.is_file() and p.resolve().parent == self.release: paths.append(p)
            for p in paths: self.downloads[p.name] = p
            self.history.append({'version': version, 'downloads': [p.name for p in paths]})
        self.history.sort(key=lambda row: row['version'], reverse=True)

    def reserve_version(self):
        # Files and reservation directories are atomic across multiple launcher instances.
        found = [1]
        for p in self.release.iterdir():
            match = re.search(r'_v(\d+)(?:[_.]|$)', p.name)
            if match: found.append(int(match.group(1)))
        version = max(found) + 1
        while True:
            try: (self.release / f'.export_v{version}.reserved').mkdir(); return version
            except FileExistsError: version += 1

    def start(self, payload):
        keys(payload, 'document')
        document = validate_editor(payload['document'])
        info = probe_media(self.source)
        if abs(info.duration - document['duration']) > .1: raise ProjectError('原影片長度不符。')
        with self.lock:
            if any(j['status'] == 'running' for j in self.jobs.values()):
                raise ProjectError('正在產生影片，請等目前版本完成。')
            job_id = uuid.uuid4().hex; version = self.reserve_version()
            fingerprint = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
            self.jobs[job_id] = dict(status='running', version=version, message='準備生成橫式與直式影片…',
                                     downloads=[], fingerprint=fingerprint)
        threading.Thread(target=self.run, args=(job_id, document), daemon=True).start()
        return {'jobId': job_id, 'version': version}

    def run(self, job_id, document):
        document = validate_editor(document)
        version = self.jobs[job_id]['version']; work = self.work / job_id
        def progress(message):
            with self.lock: self.jobs[job_id]['message'] = message
        try:
            work.mkdir(parents=True)
            staged = []
            for mode in SIZES:
                filename = f'{self.project_id}_{mode}_v{version}.mp4'
                path = work / filename
                render_movie(self.source, document, mode, work / mode, path, progress)
                staged.append(path)
            filename = f'{self.project_id}_v{version}.subtitle-workspace.json'
            (work / filename).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
            staged.append(work / filename)
            # Keep an editable snapshot with every successful film version; all share one folder.
            html = (self.release / 'editor.html').read_text(encoding='utf-8')
            data = json.dumps(document, ensure_ascii=False).replace('<', '\\u003c')
            html = re.sub(r'(<script id="project-data" type="application/json">)[\s\S]*?(</script>)',
                          lambda m: m[1] + data + m[2], html, count=1)
            name = f'{self.project_id}_v{version}.editor.html'
            (work / name).write_text(html, encoding='utf-8'); staged.append(work / name)
            ready = []
            for path in staged:
                target = self.release / path.name
                # Exclusive creation: even files added during rendering are never overwritten.
                os.link(path, target)
                ready.append(target)
            with self.lock:
                for path in ready: self.downloads[path.name] = path
                self.jobs[job_id].update(status='complete', message=f'V{version} 橫式與直式影片已完成。',
                                         downloads=[p.name for p in ready])
                self.history.insert(0, {'version': version, 'downloads': [p.name for p in ready]})
        except Exception as exc:
            with self.lock:
                self.jobs[job_id].update(status='failed', message=str(exc) if isinstance(exc, ProjectError)
                                         else '生成未完成，請重試；原片與先前版本已保留。')


def create_server(controller, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def origin_ok(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            return (self.headers.get('Host') == origin[7:] and
                    self.headers.get('Origin', origin) == origin and
                    self.headers.get('Sec-Fetch-Site', 'none') != 'cross-site')

        def authorized(self):
            cookie = SimpleCookie()
            try: cookie.load(self.headers.get('Cookie', ''))
            except Exception: return False
            value = cookie['review_session'].value if 'review_session' in cookie else ''
            return (secrets.compare_digest(self.headers.get('X-Workflow-Token', ''), controller.token)
                    or secrets.compare_digest(value, controller.token))

        def data(self, status, body, content_type='application/json; charset=utf-8', cookie=False):
            if not isinstance(body, bytes): body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type); self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY'); self.send_header('Referrer-Policy', 'no-referrer')
            if cookie: self.send_header('Set-Cookie', f'review_session={controller.token}; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers(); self.wfile.write(body)

        def stream_file(self, path, attachment=False):
            size = path.stat().st_size; start, end = 0, size - 1; status = 200
            byte_range = self.headers.get('Range')
            if byte_range:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', byte_range)
                if not match or not any(match.groups()): self.data(416, {'error': '範圍無效。'}); return
                a, b = match.groups()
                start = int(a) if a else max(0, size - int(b))
                end = min(int(b), size - 1) if a and b else size - 1
                if start > end: self.data(416, {'error': '範圍無效。'}); return
                status = 206
            self.send_response(status)
            kind = 'video/mp4' if path.suffix == '.mp4' else 'text/html; charset=utf-8' if path.suffix == '.html' else 'application/json'
            self.send_header('Content-Type', kind); self.send_header('Content-Length', str(end - start + 1))
            self.send_header('Accept-Ranges', 'bytes'); self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if status == 206: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            if attachment: self.send_header('Content-Disposition', f'attachment; filename="{path.name}"')
            self.end_headers()
            with path.open('rb') as src:
                src.seek(start); remaining = end - start + 1
                while remaining:
                    chunk = src.read(min(1024 * 1024, remaining))
                    if not chunk: break
                    self.wfile.write(chunk); remaining -= len(chunk)

        def do_GET(self):
            try:
                if not self.origin_ok(): self.data(403, {'error': '僅限本機編輯器。'}); return
                path = urlsplit(self.path).path
                if path in ('/', '/editor.html'):
                    html = (controller.release / 'editor.html').read_text(encoding='utf-8')
                    html = html.replace("connect-src 'none'", "connect-src 'self'", 1)
                    config = '<script id="export-config" type="application/json">' + json.dumps({'token': controller.token}) + '</script>'
                    html = html.replace('<script id="project-data"', config + '<script id="project-data"', 1)
                    if 'id="export-config"' not in html: html += config
                    self.data(200, html.encode(), 'text/html; charset=utf-8', cookie=True); return
                if not self.authorized(): self.data(403, {'error': '請從本機啟動器重新開啟。'}); return
                if path == '/api/exports':
                    with controller.lock: history = copy.deepcopy(controller.history)
                    self.data(200, {'versions': history}); return
                if path == '/sample-preview.mp4':
                    preview = (controller.release / 'sample-preview.mp4').resolve()
                    if preview.parent != controller.release or not preview.is_file():
                        self.data(404, {'error': '預覽影片不存在。'}); return
                    self.stream_file(preview); return
                if path.startswith('/api/jobs/'):
                    with controller.lock: result = copy.deepcopy(controller.jobs.get(path.rsplit('/', 1)[-1]))
                    self.data(200 if result else 404, result or {'error': '工作不存在。'}); return
                if path.startswith('/download/'):
                    with controller.lock: target = controller.downloads.get(path.removeprefix('/download/'))
                    if target and target.is_file() and target.resolve().parent == controller.release:
                        self.stream_file(target, attachment=True); return
                self.data(404, {'error': '資源不存在。'})
            except (BrokenPipeError, ConnectionResetError): pass

        def do_POST(self):
            if not self.origin_ok() or not self.authorized(): self.data(403, {'error': '請從本機啟動器開啟。'}); return
            try:
                if urlsplit(self.path).path != '/api/export': self.data(404, {'error': '操作不存在。'}); return
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= LIMIT: raise ProjectError('工作檔超過 8 MB 或請求無效。')
                payload = json.loads(self.rfile.read(size))
                self.data(202, controller.start(payload))
            except (ValueError, ProjectError) as exc: self.data(400, {'error': str(exc)})
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--project', required=True); parser.add_argument('--release', required=True)
    parser.add_argument('--port', type=int, default=0); parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    server = create_server(ExportController(args.root, args.project, args.release), args.port)
    url = f'http://127.0.0.1:{server.server_port}/editor.html'
    print('Local editor / 本機影片編輯器：' + url, flush=True)
    if not args.no_open: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == '__main__': main()
