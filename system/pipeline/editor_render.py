"""Desktop composition and native caption assets; no network access."""
import copy
import hashlib
import json
import os
import subprocess
import threading
import signal
from pathlib import Path
from .editor_project import duration, validate, atomic_json
from .media import require_tool

SIZE = {'horizontal': (1920, 1080), 'vertical': (1080, 1920)}
_compile_lock = threading.Lock()
_process_lock = threading.Lock()
_processes = set()


def cancel_processes():
    with _process_lock:
        for process in list(_processes):
            if process.poll() is None:
                try: os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError: pass


def run(args, **kwargs):
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, **kwargs)
    with _process_lock: _processes.add(process)
    try:
        output, error = process.communicate(timeout=3600)
        if process.returncode: raise ValueError('處理失敗：' + error.decode(errors='replace')[-1200:])
        return output
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL); process.communicate(); raise ValueError('處理逾時，已停止。')
    finally:
        with _process_lock: _processes.discard(process)


def native_tool(work):
    source = Path(__file__).with_name('editor_typography.swift')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    binary = work / ('typography-' + digest)
    with _compile_lock:
        if not binary.exists():
            work.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy(); env['CLANG_MODULE_CACHE_PATH'] = str(work / 'swift-cache')
            run([require_tool('swiftc'), str(source), '-o', str(binary)], env=env)
    return binary


def caption_assets(doc, mode, work, *, size=None):
    width, height = size or SIZE[mode]
    cues = []
    for source in doc['cues']:
        item = {key: source[key] for key in ('id', 'text', 'start', 'end')}
        item.update(copy.deepcopy(source['appearances'][mode]))
        translation = source.get('translation', {})
        if translation.get('text', '').strip():
            item['text'] += '\n' + translation['text']
            if 'runs' in translation and translation['runs']:
                for i, r in enumerate(translation['runs']):
                    prefix = '\n' if i == 0 else ''
                    item['runs'].append(dict(text=prefix + r['text'], scale=translation['scale'] * r.get('scale', 1.0),
                                             color=r.get('color'), animation='none', font=doc['styles'][mode]['english']))
            else:
                item['runs'].append(dict(text='\n' + translation['text'], scale=translation['scale'], color=None, animation='none', font=doc['styles'][mode]['english']))
        cues.append(item)
    payload = dict(style=doc['styles'][mode], cues=cues, width=width, height=height)
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode() + Path(__file__).with_name('editor_typography.swift').read_bytes()).hexdigest()
    folder = work / 'captions' / key
    with _compile_lock:
        folder.mkdir(parents=True, exist_ok=True)
        atomic_json(folder / 'input.json', payload)
    if not (folder / 'layout.json').exists():
        run([str(native_tool(work)), str(folder / 'input.json'), str(folder)])
    return folder, json.loads((folder / 'layout.json').read_text())


def ffmpeg(args):
    return run([require_tool('ffmpeg'), '-v', 'error', '-nostdin', '-y', '-filter_complex_threads', '1', *args])


def scene_filter(frame, width, height):
    # FFmpeg autorotates first; normalize display pixels before crop or extension.
    normalize = 'scale=trunc(iw*sar/2)*2:trunc(ih/2)*2,setsar=1'
    if 'zoom' in frame or 'y' in frame:
        zoom = frame.get('zoom', 1)
        x, y = frame['x'], frame.get('y', .5)
        base = 'max' if frame['mode'] == 'crop' else 'min'
        factor = f'{base}({width}/iw\\,{height}/ih)*{zoom}'
        return (f'{normalize},split[bg][fg];'
                f'[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},gblur=sigma=24[back];'
                f'[fg]scale=w=ceil(iw*{factor}/2)*2:h=ceil(ih*{factor}/2)*2,'
                f'crop=w=min(iw\\,{width}):h=min(ih\\,{height}):x=(iw-ow)*{x}:y=(ih-oh)*{y}[front];'
                f'[back][front]overlay=x=(W-w)*{x}:y=(H-h)*{y},setsar=1[v]')
    if frame['mode'] == 'crop':
        ratio = width / height
        return rf'{normalize},crop=w=trunc(min(iw\,ih*{ratio})/2)*2:h=trunc(min(ih\,iw/{ratio})/2)*2:x=trunc((iw-ow)*{frame["x"]}/2)*2:y=(ih-oh)/2,scale={width}:{height},setsar=1[v]'
    return (f'{normalize},split[bg][fg];[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},gblur=sigma=24[back];'
            f'[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[front];[back][front]overlay=(W-w)/2:(H-h)/2,setsar=1[v]')


def compose(doc, sources, mode, work, *, size=None):
    validate(doc, render=True)
    width, height = size or SIZE[mode]; work.mkdir(parents=True, exist_ok=True)
    names = []
    for i, clip in enumerate(doc['clips']):
        m = doc['media'][clip['mediaId']]; length = clip['end']-clip['start']; target = work / f'clip-{i}.mp4'
        args = ['-loop', '1'] if m['kind'] == 'photo' else ['-ss', str(clip['start'])]
        args += ['-i', str(sources[clip['mediaId']])]
        if not m['audio']: args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
        args += ['-filter_complex', '[0:v]' + scene_filter(clip['framing'][mode], width, height), '-map', '[v]', '-map', '0:a:0' if m['audio'] else '1:a:0',
                 '-af', 'apad,aresample=48000', '-ac', '2', '-c:a', 'aac', '-b:a', '192k', '-c:v', 'libx264', '-threads', '4', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', '30', '-t', str(length), str(target)]
        ffmpeg(args); names.append(target)
    listing = work / 'clips.ffconcat'
    listing.write_text('ffconcat version 1.0\n' + ''.join(f"file '{p.name}'\n" for p in names))
    assembled = work / 'assembled.mp4'
    ffmpeg(['-f', 'concat', '-safe', '0', '-i', str(listing), '-c', 'copy', str(assembled)])
    if not doc['narration']: return assembled
    args = ['-i', str(assembled)]; graph = []
    ambience = min(n['ambience'] for n in doc['narration'])
    graph.append(f'[0:a]volume={ambience}[a0]')
    for i, n in enumerate(doc['narration'], 1):
        args += ['-i', str(sources[n['mediaId']])]
        graph.append(f'[{i}:a]volume={n["volume"]},adelay={round(n["offset"]*1000)}:all=1[a{i}]')
    graph.append(''.join(f'[a{i}]' for i in range(len(doc['narration'])+1))+f'amix=inputs={len(doc["narration"])+1}:duration=first:normalize=0[a]')
    mixed = work / 'mixed.mp4'
    ffmpeg(args + ['-filter_complex', ';'.join(graph), '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-t', str(duration(doc)), str(mixed)])
    return mixed


def render(doc, sources, mode, work, output, progress=lambda _: None, *, size=None):
    from system.editor_export import verify_movie
    validate(doc, render=True); dimensions = size or SIZE[mode]
    progress(f'{mode}：組合影片與照片')
    assembled = compose(doc, sources, mode, work, size=dimensions)
    folder, records = caption_assets(doc, mode, work.parent / 'assets', size=dimensions)
    progress(f'{mode}：套用字幕與動畫')
    if not doc['cues']:
        ffmpeg(['-i', str(assembled), '-c', 'copy', '-t', str(duration(doc)), '-movflags', '+faststart', str(output)])
    else:
        blank = folder / 'blank.png'
        ffmpeg(['-f', 'lavfi', '-i', f'color=black@0:s={dimensions[0]}x{dimensions[1]},format=rgba', '-frames:v', '1', str(blank)])
        parts = ['ffconcat version 1.0']; cursor = 0
        def add(name, seconds):
            if seconds > 0: parts.extend([f"file '{name}'", f'duration {seconds:.9f}'])
        for cue, layout in zip(doc['cues'], records):
            add('blank.png', cue['start']-cursor)
            frames = layout['frames']; remaining = cue['end']-cue['start']
            for frame in frames[:-1]:
                step = min(1/30, remaining); add(frame, step); remaining -= step
            add(frames[-1], remaining); cursor = cue['end']
        add('blank.png', duration(doc)-cursor); parts.append("file 'blank.png'")
        timeline = folder / 'timeline.ffconcat'; timeline.write_text('\n'.join(parts)+'\n')
        ffmpeg(['-i', str(assembled), '-f', 'concat', '-safe', '0', '-i', str(timeline), '-filter_complex', '[1:v]fps=30,format=rgba[c];[0:v][c]overlay=0:0:format=auto,format=yuv420p[v]', '-map', '[v]', '-map', '0:a:0', '-c:v', 'libx264', '-threads', '4', '-preset', 'veryfast', '-crf', '20', '-c:a', 'copy', '-t', str(duration(doc)), '-movflags', '+faststart', str(output)])
    verify_movie(output, duration(doc), dimensions, True)
    return records


def srt(doc, records):
    def time(t):
        ms = round(t*1000); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
        return f'{h:02}:{m:02}:{s:02},{ms:03}'
    return '\n\n'.join(f'{i}\n{time(c["start"])} --> {time(c["end"])}\n'+ '\n'.join(l['text'].rstrip('\n') for l in r['lines']) for i, (c,r) in enumerate(zip(doc['cues'], records), 1))+'\n'
