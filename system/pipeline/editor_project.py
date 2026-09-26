"""Private desktop project documents; paths are resolved by the controller only."""
import copy
import json
import math
import os
import re
import uuid
from pathlib import Path

SCHEMA_V1 = 'shine.video-editor-project.v1'
SCHEMA = 'shine.video-editor-project.v2'
MODES = ('horizontal', 'vertical')


def uid():
    return uuid.uuid4().hex


def numeric(x, low, high):
    if isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) or not low <= x <= high:
        raise ValueError(f'數值必須介於 {low}–{high}。')
    return x


def exact(obj, names):
    if not isinstance(obj, dict) or set(obj) != set(names.split()):
        raise ValueError('工作檔欄位不相容。')


def identifier(x):
    if not isinstance(x, str) or not re.fullmatch(r'[\w-]{1,80}', x):
        raise ValueError('識別碼無效。')


def style():
    return dict(chinese='PingFangTC-Semibold', english='Arial-BoldMT', size=4., outline=.07, color='#ffffff')


def appearance(size=1., runs=None):
    return dict(size=size, runs=copy.deepcopy(runs or []), x=.5, y=.9,
                anchor='bottom-center', boxWidth=.92)


def cue(text, start, end, *, original='', note='', cue_id=None, words=None, source_clip_id=None):
    runs = [dict(text=text, scale=1., color=None, animation='none')]
    return dict(id=cue_id or uid(), start=float(start), end=float(end), text=text,
                original=original, note=note,
                appearances={mode: appearance(1., runs) for mode in MODES},
                wordTimings=copy.deepcopy(words or []),
                wordTimingState='valid' if words else 'unavailable',
                sourceClipId=source_clip_id)


def empty(project):
    identifier(project)
    return dict(schema=SCHEMA, projectId=project, media={}, clips=[], narration=[], cues=[],
                styles={m: style() for m in MODES}, revision=0, sync='current')


def framing(kind='video', width=1920, height=1080):
    return {m: dict(mode='crop' if m == 'vertical' and width > height else 'extend', x=.5) for m in MODES}


def clip(media_id, media):
    return dict(id=uid(), mediaId=media_id, start=0., end=media['duration'],
                framing=framing(media['kind'], media['width'], media['height']), rationale='手動加入／保留原順序')


def duration(doc):
    return sum(c['end'] - c['start'] for c in doc['clips'])


def migrate(doc):
    """Upgrade an in-memory v1 document without changing its visible appearance."""
    if not isinstance(doc, dict) or doc.get('schema') != SCHEMA_V1:
        return copy.deepcopy(doc)
    result = copy.deepcopy(doc); result['schema'] = SCHEMA
    for item in result.get('cues', []):
        size = item.pop('size', 1.)
        runs = item.pop('runs', [dict(text=item.get('text', ''), scale=1., color=None, animation='none')])
        item['appearances'] = {mode: appearance(size, runs) for mode in MODES}
        item['wordTimings'] = []
        item['wordTimingState'] = 'unavailable'
        item['sourceClipId'] = None
    return result


def validate(doc, *, render=False):
    doc = migrate(doc)
    if len(json.dumps(doc, ensure_ascii=False).encode()) > 8 * 1024 * 1024:
        raise ValueError('工作檔超過 8 MB。')
    exact(doc, 'schema projectId media clips narration cues styles revision sync')
    if doc['schema'] != SCHEMA: raise ValueError('工作檔版本不相容。')
    identifier(doc['projectId']); numeric(doc['revision'], 0, 1e12)
    if doc['sync'] not in ('current', 'stale'): raise ValueError('同步狀態無效。')
    if not isinstance(doc['media'], dict) or len(doc['media']) > 1000: raise ValueError('素材過多。')
    for key, m in doc['media'].items():
        identifier(key)
        if not isinstance(m, dict) or not {'name', 'kind', 'duration', 'width', 'height', 'audio'} <= set(m) <= {'name', 'kind', 'duration', 'width', 'height', 'audio', 'originalName'}:
            raise ValueError('工作檔欄位不相容。')
        if not isinstance(m['name'], str) or len(m['name']) > 255: raise ValueError('素材名稱無效。')
        if 'originalName' in m and (not isinstance(m['originalName'], str) or len(m['originalName']) > 255):
            raise ValueError('原始素材名稱無效。')
        if m['kind'] not in ('video', 'photo', 'audio'): raise ValueError('素材種類無效。')
        numeric(m['duration'], .01, 86400); numeric(m['width'], 0, 32768); numeric(m['height'], 0, 32768)
        if type(m['audio']) is not bool: raise ValueError('聲音欄位無效。')
    ids = set()
    if not isinstance(doc['clips'], list) or len(doc['clips']) > 1000: raise ValueError('片段過多。')
    for c in doc['clips']:
        exact(c, 'id mediaId start end framing rationale'); identifier(c['id'])
        if c['id'] in ids or c['mediaId'] not in doc['media']: raise ValueError('片段來源或 ID 無效。')
        ids.add(c['id']); m = doc['media'][c['mediaId']]
        if m['kind'] == 'audio': raise ValueError('音軌不能當畫面。')
        numeric(c['start'], 0, m['duration']); numeric(c['end'], c['start'] + .01, 3600 if m['kind'] == 'photo' else m['duration'])
        if not isinstance(c['rationale'], str) or len(c['rationale']) > 2000: raise ValueError('排序備註過長。')
        exact(c['framing'], 'horizontal vertical')
        for f in c['framing'].values():
            # Optional transform fields preserve legacy v2 documents unchanged.
            if not isinstance(f, dict) or not {'mode', 'x'} <= set(f) <= {'mode', 'x', 'y', 'zoom'}: raise ValueError('構圖欄位無效。')
            numeric(f['x'], 0, 1); numeric(f.get('y', .5), 0, 1); numeric(f.get('zoom', 1), .01, 8)
            if f['mode'] not in ('crop', 'extend'): raise ValueError('構圖無效。')
    total = duration(doc); numeric(total, 0, 86400)
    if render and not doc['clips']: raise ValueError('請先新增影片或照片。')
    if not isinstance(doc['narration'], list) or len(doc['narration']) > 100: raise ValueError('音軌過多。')
    for n in doc['narration']:
        exact(n, 'id mediaId offset volume ambience'); identifier(n['id'])
        if n['mediaId'] not in doc['media'] or not doc['media'][n['mediaId']]['audio']: raise ValueError('配音來源無效。')
        numeric(n['offset'], 0, 86400); numeric(n['volume'], 0, 2); numeric(n['ambience'], 0, 1)
    exact(doc['styles'], 'horizontal vertical')
    for s in doc['styles'].values():
        exact(s, 'chinese english size outline color')
        for k in ('chinese', 'english'):
            if not isinstance(s[k], str) or not re.fullmatch(r'[\w .-]{1,120}', s[k]): raise ValueError('字型無效。')
        numeric(s['size'], 2, 20); numeric(s['outline'], 0, .2)
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', s['color']): raise ValueError('色彩無效。')
    ids = set(); prev = 0
    if not isinstance(doc['cues'], list) or len(doc['cues']) > 10000: raise ValueError('字幕過多。')
    for index, c in enumerate(doc['cues'], 1):
        try:
            required = set('id start end text original note appearances wordTimings wordTimingState sourceClipId'.split())
            if not isinstance(c, dict) or not required <= set(c) <= required | {'translation'}: raise ValueError('字幕欄位無效。')
            if 'translation' in c:
                tr = c['translation']
                if not isinstance(tr, dict) or not {'text', 'sourceText', 'scale'} <= set(tr) <= {'text', 'sourceText', 'scale', 'runs'}: raise ValueError('翻譯欄位不相容。')
                if any(not isinstance(tr[k], str) or len(tr[k]) > 10000 for k in ('text', 'sourceText')): raise ValueError('翻譯文字無效。')
                numeric(tr['scale'], .4, .9)
                if 'runs' in tr:
                    if not isinstance(tr['runs'], list) or len(tr['runs']) > 1000: raise ValueError('翻譯格式過多。')
                    for r in tr['runs']:
                        if not isinstance(r, dict) or not {'text'} <= set(r) <= {'text', 'color', 'scale'}: raise ValueError('翻譯字詞欄位無效。')
                        if r.get('color') is not None and not re.fullmatch(r'#[0-9a-fA-F]{6}', r['color']): raise ValueError('翻譯色彩無效。')
            identifier(c['id'])
            if c['id'] in ids: raise ValueError('ID 重複。')
            ids.add(c['id'])
            numeric(c['start'], prev, 86400); numeric(c['end'], c['start'] + .01, 86400)
            if (render or doc['sync'] == 'current') and c['end'] > total + .001: raise ValueError('超出影片長度。')
            prev = c['end']
            for k in ('text', 'original', 'note'):
                if not isinstance(c[k], str) or len(c[k]) > 10000: raise ValueError('文字無效。')
            if render and not c['text'].strip(): raise ValueError('請填字幕或刪除空白句。')
            exact(c['appearances'], 'horizontal vertical')
            for a in c['appearances'].values():
                exact(a, 'size runs x y anchor boxWidth')
                numeric(a['size'], .5, 3); numeric(a['x'], 0, 1); numeric(a['y'], 0, 1)
                numeric(a['boxWidth'], .1, 1)
                if a['anchor'] not in ('bottom-center', 'center'): raise ValueError('字幕錨點無效。')
                if not isinstance(a['runs'], list) or len(a['runs']) > 1000: raise ValueError('格式過多。')
                for r in a['runs']:
                    if not isinstance(r, dict) or not {'text','scale','color','animation'} <= set(r) <= {'text','scale','color','animation','font'}: raise ValueError('字詞格式欄位無效。')
                    if r.get('font') is not None and (not isinstance(r['font'], str) or not re.fullmatch(r'[\w .-]{1,120}', r['font'])): raise ValueError('字型無效。')
                    numeric(r['scale'], .5, 3)
                    if not isinstance(r['text'], str): raise ValueError('字詞無效。')
                    if r['color'] is not None and not re.fullmatch(r'#[0-9a-fA-F]{6}', r['color']): raise ValueError('色彩無效。')
                    if r['animation'] not in ('none', 'pop', 'bounce'): raise ValueError('動畫無效。')
                if ''.join(r['text'] for r in a['runs']) != c['text']: raise ValueError('文字與格式不一致。')
            if c['wordTimingState'] not in ('valid', 'edited', 'unavailable'): raise ValueError('逐字時間狀態無效。')
            if c['sourceClipId'] is not None: identifier(c['sourceClipId'])
            if not isinstance(c['wordTimings'], list) or len(c['wordTimings']) > 5000: raise ValueError('逐字時間過多。')
            last_word_end = c['start']
            for word in c['wordTimings']:
                exact(word, 'text start end startOffset endOffset')
                if not isinstance(word['text'], str): raise ValueError('逐字內容無效。')
                numeric(word['start'], c['start'], c['end']); numeric(word['end'], word['start'], c['end'])
                numeric(word['startOffset'], 0, len(c['text'])); numeric(word['endOffset'], word['startOffset'], len(c['text']))
                if word['start'] < last_word_end - .001: raise ValueError('逐字時間順序無效。')
                last_word_end = word['end']
        except (ValueError, TypeError) as exc:
            raise ValueError(f'字幕 {index:03d}：{exc}') from exc
    return copy.deepcopy(doc)


def atomic_json(path, doc):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uid() + '.tmp')
    with temp.open('x', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)


def migrate_review(project, old, media_id, media):
    doc = empty(project); doc['media'][media_id] = media; doc['clips'] = [clip(media_id, media)]
    for c in old['cues']:
        note = c.get('note', '')
        # Remove only exact known diagnostics, retaining any owner-authored suffix.
        for diagnostic in ('辨識信心較低，請對照原聲。', '可能有同音字或專有名詞錯誤，請核對。'):
            note = note.replace(diagnostic, '')
        runs = []
        for r in c.get('runs', []):
            rs = r.get('style', {})
            run = dict(text=r['text'], scale=r.get('scale', rs.get('sizeScale', 1)), color=rs.get('color'), animation='none')
            if rs.get('fontFamily'): run['font'] = rs['fontFamily']
            runs.append(run)
        if not runs: runs = [dict(text=c['text'], scale=1., color=None, animation='none')]
        item = cue(c['text'], c['start'], c['end'], original=c.get('original', c['text']), note=note.strip())
        for mode in MODES: item['appearances'][mode] = appearance(c.get('size') or 1., runs)
        doc['cues'].append(item)
    for mode in MODES:
        old_style = old.get('styles', {}).get(mode, {})
        doc['styles'][mode]['size'] = old_style.get('size', 4.)
        if 'style' in old:
            style_old = old['style']
            doc['styles'][mode].update(chinese=style_old['fontFamily'], english=style_old['fontFamily'], size=style_old['sizePct'], outline=style_old['strokePct'], color=style_old['color'])
    segments = old.get('framing', {}).get('vertical', {}).get('segments', [])
    if segments:
        doc['clips'] = []
        for seg in segments:
            item = clip(media_id, media); item.update(start=seg['start'], end=seg['end'])
            item['framing']['vertical'] = dict(mode=seg['mode'], x=seg['positionX'])
            item['rationale'] = '原合成影片的既有構圖片段；不是推測的原始素材。'
            doc['clips'].append(item)
    return validate(doc)
