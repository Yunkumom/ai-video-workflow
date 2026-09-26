"""Loopback desktop adapter. Original review-export API is intentionally unchanged."""
import argparse
import copy
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import threading
import signal
import time
import fcntl
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .pipeline.editor_project import empty, uid, clip, cue, validate, duration, atomic_json, migrate_review, identifier
from .pipeline.editor_timeline import changed_media, trim_clip_with_cues, split_clip, delete_clip_with_cues, intervals
from .pipeline.editor_render import run, native_tool, caption_assets, render, srt, compose, ffmpeg, cancel_processes
from .pipeline.media import require_tool


def metadata(path):
    info = json.loads(run([require_tool('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))
    streams = info.get('streams', []); video = next((s for s in streams if s['codec_type'] == 'video'), None)
    photo = path.suffix.lower() in ('.jpg', '.jpeg', '.png')
    audio = any(s['codec_type'] == 'audio' for s in streams)
    if not video and not audio: raise ValueError('素材沒有可用畫面或聲音。')
    width, height = (video['width'], video['height']) if video else (0, 0)
    if video:
        sar = video.get('sample_aspect_ratio', '1:1').split(':')
        if len(sar) == 2 and int(sar[1]) != 0: width *= int(sar[0])/int(sar[1])
        rotation = video.get('tags', {}).get('rotate', 0)
        for item in video.get('side_data_list', []): rotation = item.get('rotation', rotation)
        if abs(float(rotation)) % 180 == 90: width, height = height, width
    return dict(name=path.name, kind='photo' if photo else 'video' if video else 'audio',
                duration=5. if photo else float(info['format']['duration']), width=width, height=height, audio=audio)


class Controller:
    def __init__(self, root, project):
        self.root = root.resolve(); self.project = project; self.doc = empty(project)
        self.input = self.root / '1_input' / project
        self.output = self.root / '3_output' / project
        self.work = self.root / '2_processing' / project / 'desktop-editor'
        self.saved = self.output / '保存區' / '工作中'
        for p in (self.input, self.output, self.work, self.saved):
            if not p.resolve().is_relative_to(self.root): raise ValueError('專案路徑不安全。')
            p.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32); self.native = secrets.token_urlsafe(32)
        self.lock = threading.RLock(); self.jobs = {}; self.sources = {}; self.assets = {}
        self.registry = self.saved / 'sources.json'; self.document = self.saved / 'project.json'
        if self.registry.exists():
            self.sources = {k: self.resolve_source(v) for k,v in json.loads(self.registry.read_text()).items()}
        recovery = self.saved / 'recovery-pending.json'
        if recovery.exists() and (not self.document.exists() or recovery.stat().st_mtime > self.document.stat().st_mtime):
            recovered = validate(json.loads(recovery.read_text())); self.check_sources(recovered)
            atomic_json(self.document, recovered)
        if self.document.exists():
            try:
                raw = json.loads(self.document.read_text()); self.doc = validate(raw)
                if raw.get('schema') != self.doc['schema']:
                    atomic_json(self.saved / ('before-v2-migration-' + uid() + '.json'), raw)
                    atomic_json(self.document, self.doc)
            except (ValueError, OSError):
                self.doc = validate(json.loads((self.saved / 'previous-project.json').read_text()))
                atomic_json(self.saved / ('damaged-project-' + uid() + '.json'), dict(raw=self.document.read_text(errors='replace')))
                atomic_json(self.document, self.doc)
            self.check_sources(self.doc)
        elif (self.input / 'sample.mov').is_file():
            mid = uid(); source = self.input / 'sample.mov'; self.sources[mid] = source.resolve()
            # Explicit legacy family only; never infer version order from folder names.
            legacy = self.output / 'tutorial_v1' / '0912_v4.subtitle-workspace.json'
            if legacy.is_file(): self.doc = migrate_review(project, json.loads(legacy.read_text()), mid, metadata(source))
            else:
                self.doc['media'][mid] = metadata(source); self.doc['clips'] = [clip(mid, self.doc['media'][mid])]
            atomic_json(self.saved / 'migration.json', dict(source=str(legacy.relative_to(self.output)) if legacy.exists() else 'original source',
                historicalPackaging='retained; tutorial_v2 is a separate review family, not renumbered',
                inventory=[str(p.relative_to(self.output)) for folder in ('tutorial_v1', 'tutorial_v2') for p in (self.output / folder).glob('*') if p.is_file()]))
            self.save(self.doc)

        self.apply_caption_update()

    def apply_caption_update(self):
        """Apply an owner-requested, exact-text patch after startup recovery, never live edits."""
        pending = self.saved / 'caption-update-pending.json'
        if not pending.exists(): return
        if pending.stat().st_size > 8 * 1024 * 1024: raise ValueError('字幕更新超過大小限制。')
        patch = json.loads(pending.read_text())
        if not isinstance(patch, list) or len(patch) > 10000: raise ValueError('字幕更新格式錯誤。')
        updated = copy.deepcopy(self.doc); matched = []; seen = set()
        from .pipeline.editor_timeline import _slice_runs
        for entry in patch:
            if not isinstance(entry, dict) or set(entry) != {'id', 'sourceText', 'text', 'english'} or any(not isinstance(v, str) or len(v) > 10000 for v in entry.values()): raise ValueError('字幕更新格式錯誤。')
            if entry['id'] in seen: raise ValueError('字幕更新 ID 重複。')
            seen.add(entry['id'])
            cue = next((c for c in updated['cues'] if c['id'] == entry['id'] and c['text'] == entry['sourceText']), None)
            if cue is None: continue  # Never overwrite a subsequent owner correction.
            if cue['text'] != entry['text']:
                if not cue['text'].startswith(entry['text']): raise ValueError('僅允許保留既有中文並移除示範尾段。')
                for appearance in cue['appearances'].values(): appearance['runs'] = _slice_runs(appearance['runs'], 0, len(entry['text']))
                cue['text'] = entry['text']; cue['wordTimings'] = []; cue['wordTimingState'] = 'edited'
            cue['translation'] = dict(text=entry['english'], sourceText=cue['text'], scale=.7)
            matched.append(cue['id'])
        validate(updated)
        if matched:
            atomic_json(self.saved / ('before-caption-update-' + uid() + '.json'), self.doc)
            updated['revision'] += 1; self.save(updated)
        pending.rename(self.saved / ('caption-update-applied-' + uid() + '.json'))

    def resolve_source(self, relative):
        p = (self.input / relative).resolve()
        if not p.is_relative_to(self.input.resolve()) or not p.is_file(): raise ValueError('素材不存在或超出專案。')
        return p

    def check_sources(self, doc):
        if doc['projectId'] != self.project: raise ValueError('專案不相符。')
        for mid, m in doc['media'].items():
            if mid not in self.sources: raise ValueError('請重新匯入缺少的素材。')
            actual = metadata(self.sources[mid])
            if (actual['kind'] != m['kind'] or abs(actual['duration'] - m['duration']) > 0.05 or
                actual['width'] != m['width'] or actual['height'] != m['height'] or actual['audio'] != m['audio']):
                raise ValueError('素材已變更，請重新匯入。')

    def save(self, doc, synchronized_media=False):
        doc = validate(doc)
        with self.lock:
            self.check_sources(doc)
            if changed_media(self.doc, doc) and doc['cues'] and not synchronized_media: doc['sync'] = 'stale'
            # Preserve the last successful draft for recovery from a damaged latest file.
            if self.document.exists(): shutil.copy2(self.document, self.saved / 'previous-project.json')
            atomic_json(self.registry, {k: str(v.relative_to(self.input)) for k,v in self.sources.items()})
            atomic_json(self.document, doc); self.doc = doc
        return doc

    def import_files(self, paths):
        from .pipeline.media_naming import generate_media_names
        imported = []
        video_photo_paths = []
        audio_paths = []
        for name in paths:
            path = Path(name)
            ext = path.suffix.lower()
            if ext not in ('.mp4', '.mov', '.m4v', '.jpg', '.jpeg', '.png', '.wav', '.mp3', '.m4a', '.aac'):
                raise ValueError('支援 MP4/MOV、JPG/PNG 與 WAV/MP3/M4A；HEIC 尚不支援。')
            if ext in ('.wav', '.mp3', '.m4a', '.aac'):
                audio_paths.append(path)
            else:
                video_photo_paths.append(path)

        existing_names = [m['name'] for m in self.doc.get('media', {}).values() if isinstance(m, dict) and 'name' in m]

        # Standardize videos and photos
        if video_photo_paths:
            named_items = generate_media_names(video_photo_paths, subject=self.project, existing_names=existing_names)
            for item in named_items:
                path = item['original_path']
                standard_name = item['new_name']
                m = metadata(path); mid = uid()
                dest = self.input / 'desktop-imports' / f"{mid[:8]}_{standard_name}"
                dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, dest)
                self.sources[mid] = dest
                m['name'] = standard_name
                m['originalName'] = path.name
                imported.append(dict(id=mid, media=m))

        # Audio files preserve original track name
        for path in audio_paths:
            m = metadata(path); mid = uid()
            dest = self.input / 'desktop-imports' / (mid + path.suffix.lower())
            dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, dest)
            self.sources[mid] = dest
            m['originalName'] = path.name
            imported.append(dict(id=mid, media=m))

        atomic_json(self.registry, {k: str(v.relative_to(self.input)) for k,v in self.sources.items()})
        return imported

    def history(self):
        result = []
        for p in (self.output / '保存區').glob('V*/complete.json'):
            data = json.loads(p.read_text())
            version = int(p.parent.name[1:])
            expected = data.get('movies', [])
            valid_names = {f'{self.project}_V{version}_橫式.mp4', f'{self.project}_V{version}_直式.mp4'}
            if data.get('version') == version and expected and set(expected) <= valid_names and all((self.output / f).is_file() for f in expected): result.append(data)
        return sorted(result, key=lambda x: x['version'], reverse=True)

    def local_tools(self):
        python = self.root / '2_processing' / (self.project + '-local-tools') / 'bin' / 'python3'
        snapshots = Path.home() / '.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo/snapshots'
        models = sorted(p for p in snapshots.glob('*') if p.is_dir() and (p / 'config.json').is_file())
        return (python, models[-1]) if python.is_file() and models else None

    def recognize(self, doc):
        doc = validate(doc); self.check_sources(doc); tools = self.local_tools()
        if not tools: raise ValueError('尚未設定本機辨識工具；可先手動新增或匯入 SRT。')
        with self.lock:
            if any(j['status'] == 'running' for j in self.jobs.values()): raise ValueError('請等目前處理完成。')
            jid = uid(); job = dict(id=jid, kind='recognition', status='running', message='準備合成聲音', revision=doc['revision']); self.jobs[jid] = job
        def worker():
            from .pipeline.transcription import audio_windows
            try:
                work = self.work / jid; work.mkdir()
                audio_doc = copy.deepcopy(doc); audio_doc['cues'] = []; audio_doc['sync'] = 'current'
                assembled = compose(audio_doc, self.sources, 'horizontal', work / 'audio', size=(320,180))
                cues = []; windows = audio_windows(duration(doc))
                for index, (start, length) in enumerate(windows):
                    job['message'] = f'本機辨識 {index+1}/{len(windows)} 段'
                    wav = work / f'window-{index}.wav'; result = work / f'window-{index}.json'
                    ffmpeg(['-ss', str(start), '-i', str(assembled), '-t', str(length), '-vn', '-ac', '1', '-ar', '16000', str(wav)])
                    env = os.environ.copy(); env['HF_HUB_OFFLINE'] = '1'; env['TRANSFORMERS_OFFLINE'] = '1'
                    run([str(tools[0]), str(Path(__file__).parent / 'pipeline/editor_transcribe.py'), '--audio', str(wav), '--model', str(tools[1]), '--output', str(result)], env=env)
                    rows = json.loads(result.read_text())
                    for row in rows:
                        begin = max(start, start+float(row['start']), cues[-1]['end'] if cues else 0)
                        end = min(start+length, start+float(row['end'])); text = row['text'].strip()
                        if end-begin < .01 or not text: continue
                        words, cursor = [], 0
                        for word in row.get('words', []):
                            token = str(word.get('word', '')).strip(); offset = text.find(token, cursor)
                            if not token or offset < 0: words = []; break
                            finish = offset + len(token)
                            words.append(dict(text=token, start=max(begin, start+float(word['start'])),
                                              end=min(end, start+float(word['end'])),
                                              startOffset=offset, endOffset=finish))
                            cursor = finish
                        source_clip = next((item['id'] for item, lo, hi in intervals(doc) if lo <= begin < hi), None)
                        cues.append(cue(text, begin, end, original=text, words=words, source_clip_id=source_clip))
                if not cues: raise ValueError('沒有辨識到語音，原字幕保留。')
                proposal = copy.deepcopy(doc); proposal['cues'] = cues; proposal['sync'] = 'current'; validate(proposal, render=True)
                atomic_json(work / 'recognition-proposal.json', proposal)
                job.update(status='complete', message=f'辨識完成：{len(cues)} 句，等待確認替換。', cues=cues)
            except Exception as e: job.update(status='failed',message=str(e))
        threading.Thread(target=worker,daemon=False).start(); return job

    def start_render(self, doc, modes=None):
        doc = validate(doc, render=True); self.check_sources(doc)
        modes = ['horizontal', 'vertical'] if modes is None else modes
        if not isinstance(modes, list) or not modes or len(set(modes)) != len(modes) or not set(modes) <= {'horizontal', 'vertical'}:
            raise ValueError('輸出方向無效。')
        if doc['sync'] == 'stale' and doc['cues']: raise ValueError('剪輯後字幕待同步，請先校對確認或重新辨識。')
        with self.lock:
            if any(j['status'] == 'running' for j in self.jobs.values()): raise ValueError('影片正在生成。')
            existing = [int(m.group(1)) for p in self.output.rglob('*') if (m := re.search(r'(?:_v|_V|^V)(\d+)', p.name))]
            version = max(existing, default=0)+1
            while True:
                reserve = self.output / '保存區' / f'V{version}'
                try: reserve.mkdir(); break
                except FileExistsError: version += 1
            jid = uid(); job = dict(id=jid, status='running', message='準備中', version=version, revision=doc['revision']); self.jobs[jid] = job
        def worker():
            published = []
            try:
                work = self.work / jid; work.mkdir()
                atomic_json(work / 'snapshot.json', doc)
                sources = {}
                source_folder = work / 'sources'; source_folder.mkdir()
                used = {x['mediaId'] for x in doc['clips'] + doc['narration']}
                for mid in used:
                    original = self.sources[mid]; before = original.stat()
                    target = source_folder / (mid + original.suffix.lower())
                    shutil.copy2(original, target)
                    after = original.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns): raise ValueError('素材在快照期間變更，請重新生成。')
                    sources[mid] = target
                movies = []
                for mode, label in (('horizontal', '橫式'), ('vertical', '直式')):
                    if mode not in modes: continue
                    name = f'{self.project}_V{version}_{label}.mp4'; target = work / name
                    records = render(doc, sources, mode, work / mode, target, lambda msg: job.update(message=msg))
                    (reserve / f'{label}.srt').write_text(srt(doc, records), encoding='utf-8'); movies.append(name)
                atomic_json(reserve / 'project.json', doc)
                atomic_json(reserve / 'sources.json', {k: str(v.relative_to(self.input)) for k,v in self.sources.items() if k in doc['media']})
                for name in movies:
                    os.link(work / name, self.output / name); published.append(name)
                manifest = dict(version=version, modes=modes, movies=movies, revision=doc['revision'], sha256={name: hashlib.sha256((self.output / name).read_bytes()).hexdigest() for name in movies})
                atomic_json(reserve / 'complete.json', manifest)
                labels = {'horizontal': '橫式', 'vertical': '直式'}
                job.update(status='complete', message='、'.join(labels[m] for m in modes)+'影片已完成', movies=movies)
            except Exception as e:
                for name in published:
                    os.rename(self.output / name, work / ('incomplete-' + name))
                job.update(status='failed', message=str(e))
            finally: atomic_json(reserve / 'job.json', job)
        threading.Thread(target=worker, daemon=False).start()
        return job


def create_server(controller, port=0):
    c = controller
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def valid_origin(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            return self.headers.get('Host') == origin[7:] and self.headers.get('Origin', origin) == origin and self.headers.get('Sec-Fetch-Site') != 'cross-site'
        def authorized(self):
            cookie = SimpleCookie()
            try: cookie.load(self.headers.get('Cookie', ''))
            except Exception: return False
            value = cookie['desktop'].value if 'desktop' in cookie else ''
            return secrets.compare_digest(value, c.token) or secrets.compare_digest(self.headers.get('X-Workflow-Token', ''), c.token)
        def data(self, status, data, kind='application/json; charset=utf-8', cookie=False):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status); self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            if cookie: self.send_header('Set-Cookie', f'desktop={c.token}; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers(); self.wfile.write(body)
        def stream(self, path):
            size = path.stat().st_size; start, end = 0, size-1
            match = re.fullmatch(r'bytes=(\d+)-(\d*)', self.headers.get('Range', ''))
            if self.headers.get('Range') and not match: self.data(416, {}); return
            if match: start = int(match[1]); end = min(end, int(match[2])) if match[2] else end
            if start > end: self.data(416, {}); return
            self.send_response(206 if match else 200); self.send_header('Content-Type', mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(end-start+1)); self.send_header('Accept-Ranges', 'bytes')
            if match: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            with path.open('rb') as f:
                f.seek(start); remaining = end-start+1
                while remaining:
                    chunk = f.read(min(remaining, 1024*1024))
                    if not chunk: break
                    self.wfile.write(chunk); remaining -= len(chunk)
        def do_GET(self):
            try:
                path = urlsplit(self.path).path
                if not self.valid_origin(): self.data(403, {'error': '請從桌面 App 開啟。'}); return
                # The shell contains no project data. Keeping it visible lets the native app
                # recover from a controller restart instead of replacing the UI with raw JSON.
                if path == '/': self.data(200, (Path(__file__).parent / 'desktop/editor.html').read_bytes(), 'text/html; charset=utf-8', self.authorized())
                elif path == '/brand-mark.png': self.stream(Path(__file__).parent / 'desktop' / 'yunkumom-mark.png')
                elif not self.authorized(): self.data(403, {'error': '本機控制器已重新連線，正在恢復編輯器。'})
                elif path == '/api/project': self.data(200, c.doc)
                elif path == '/api/history': self.data(200, c.history())
                elif path == '/api/fonts': self.data(200, run([str(native_tool(c.work / 'assets')), '--fonts']))
                elif path == '/api/jobs': self.data(200, list(c.jobs.values()))
                elif path == '/api/readiness': self.data(200, dict(localRecognition=c.local_tools() is not None, externalCorrection=bool(os.environ.get('GROQ_API_KEY','').strip())))
                elif path.startswith('/media/') and path.split('/')[-1] in c.sources: self.stream(c.sources[path.split('/')[-1]])
                elif path.startswith('/asset/') and path.split('/')[-1] in c.assets: self.stream(c.assets[path.split('/')[-1]])
                else: self.data(404, {'error': '找不到資源。'})
            except (BrokenPipeError, ConnectionResetError): pass
            except Exception as e: self.data(400, {'error': str(e)})
        def do_POST(self):
            try:
                if not self.valid_origin() or not self.authorized(): self.data(403, {'error': '請從桌面 App 開啟。'}); return
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8*1024*1024: raise ValueError('請求超過 8 MB。')
                body = json.loads(self.rfile.read(size)); path = urlsplit(self.path).path
                if path == '/api/save': self.data(200, c.save(body))
                elif path == '/api/import-review':
                    if not c.doc['clips']: raise ValueError('請先匯入字幕對應的原影片。')
                    from .editor_export import validate_editor
                    from .pipeline.review_document import validate_review_document
                    old = validate_review_document(body) if 'style' in body else validate_editor(body)
                    mid = c.doc['clips'][0]['mediaId']; media = c.doc['media'][mid]
                    if abs(old['duration']-media['duration']) > .1 or old['source'] != media['name']: raise ValueError('工作檔不是目前原影片。')
                    self.data(200, migrate_review(c.project, old, mid, media))
                elif path == '/api/render':
                    if isinstance(body, dict) and set(body) == {'document', 'modes'}:
                        self.data(202, c.start_render(body['document'], body['modes']))
                    else:
                        self.data(202, c.start_render(body))
                elif path == '/api/trim':
                    if not isinstance(body, dict) or set(body) != {'document', 'clipId', 'start', 'end'}: raise ValueError('裁切請求無效。')
                    document = validate(body['document']); c.check_sources(document)
                    updated = trim_clip_with_cues(document, body['clipId'], body['start'], body['end'])
                    updated['revision'] = document['revision'] + 1
                    self.data(200, c.save(updated, synchronized_media=True))
                elif path == '/api/split':
                    if not isinstance(body, dict) or set(body) != {'document', 'clipId', 'time'}: raise ValueError('分割請求無效。')
                    document = validate(body['document']); c.check_sources(document)
                    updated = split_clip(document, body['clipId'], body['time']); updated['revision'] = document['revision'] + 1
                    self.data(200, c.save(updated, synchronized_media=True))
                elif path == '/api/delete-clip':
                    if not isinstance(body, dict) or set(body) != {'document', 'clipId'}: raise ValueError('刪除片段請求無效。')
                    document = validate(body['document']); c.check_sources(document)
                    updated = delete_clip_with_cues(document, body['clipId']); updated['revision'] = document['revision'] + 1
                    self.data(200, c.save(updated, synchronized_media=True))
                elif path == '/api/recognize': self.data(202, c.recognize(body))
                elif path == '/api/correct':
                    from .pipeline.workspace import assistant_proposal
                    self.data(200, assistant_proposal(body))
                elif path == '/api/layout':
                    doc = validate(body['document']); mode = body['mode']
                    if mode not in ('horizontal', 'vertical'): raise ValueError('方向無效。')
                    folder, records = caption_assets(doc, mode, c.work / 'assets')
                    for record in records:
                        links = []
                        for name in record['frames']:
                            key = hashlib.sha256(str(folder / name).encode()).hexdigest()+'.png'; c.assets[key] = folder / name; links.append('/asset/'+key)
                        record['frames'] = links
                    self.data(200, records)
                elif path == '/native/import':
                    if not secrets.compare_digest(self.headers.get('X-Native-Token', ''), c.native): self.data(403, {}); return
                    self.data(200, c.import_files(body['paths']))
                elif path == '/api/restore':
                    version = body['version']
                    if not isinstance(version, int) or version not in [x['version'] for x in c.history()]: raise ValueError('版本不存在。')
                    self.data(200, json.loads((c.output / '保存區' / f'V{version}' / 'project.json').read_text()))
                else: self.data(404, {'error': '操作不存在。'})
            except Exception as e: self.data(400, {'error': str(e)})
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--root', type=Path, required=True); parser.add_argument('--project', required=True)
    args = parser.parse_args(); identifier(args.project)
    work = args.root.resolve() / '2_processing' / args.project / 'desktop-editor'
    if not work.resolve().is_relative_to(args.root.resolve()): raise ValueError('專案路徑不安全。')
    work.mkdir(parents=True, exist_ok=True)
    lock = (work / 'controller.lock').open('a')
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('這個專案已有編輯器開啟。')
    c = Controller(args.root, args.project)
    server = create_server(c); parent = os.getppid()
    def shutdown(*_):
        cancel_processes()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown); signal.signal(signal.SIGINT, shutdown)
    def parent_watch():
        while True:
            time.sleep(2)
            if os.getppid() != parent:
                cancel_processes(); os.kill(os.getpid(), signal.SIGTERM); return
    threading.Thread(target=parent_watch, daemon=True).start()
    print(json.dumps(dict(url=f'http://127.0.0.1:{server.server_port}/', token=c.token, native=c.native)), flush=True)
    server.serve_forever()

if __name__ == '__main__': main()
