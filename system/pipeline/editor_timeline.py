"""Pure timeline geometry shared by the controller and verification."""
import copy
import uuid
from .editor_project import duration, validate


def intervals(doc):
    start = 0.
    for clip in doc['clips']:
        end = start + clip['end'] - clip['start']
        yield clip, start, end
        start = end


def crop_rect(width, height, output_width, output_height, x=.5):
    ratio = output_width / output_height
    w, h = min(width, height * ratio), min(height, width / ratio)
    return ((width - w) * x, (height - h) / 2, w, h)


def changed_media(before, after):
    timing = lambda d: [(c['id'], c['mediaId'], c['start'], c['end']) for c in d['clips']]
    return timing(before) != timing(after) or before['narration'] != after['narration']


def split_clip(doc, clip_id, timeline_time):
    """Split a clip at a timeline time without changing media or cue timing."""
    result = copy.deepcopy(validate(doc))
    timeline_time = float(timeline_time)
    for index, (item, start, end) in enumerate(intervals(result)):
        if item['id'] != clip_id:
            continue
        if not start + .01 < timeline_time < end - .01:
            raise ValueError('播放位置必須在片段內。')
        source_time = item['start'] + timeline_time - start
        right = copy.deepcopy(item); right['id'] = uuid.uuid4().hex
        item['end'] = source_time; right['start'] = source_time
        result['clips'].insert(index + 1, right)
        return validate(result)
    raise ValueError('片段不存在。')


def _slice_runs(runs, start, end):
    result, offset = [], 0
    for run in runs:
        lo, hi = max(start, offset), min(end, offset + len(run['text']))
        if hi > lo:
            item = copy.deepcopy(run); item['text'] = run['text'][lo-offset:hi-offset]
            result.append(item)
        offset += len(run['text'])
    return result


def _trim_aligned_words(cue, keep_start, keep_end, new_origin):
    if cue['wordTimingState'] != 'valid' or not cue['wordTimings']:
        return False
    words = [w for w in cue['wordTimings'] if w['end'] > keep_start + .001 and w['start'] < keep_end - .001]
    if not words:
        return False
    first, last = words[0]['startOffset'], words[-1]['endOffset']
    if first < 0 or last > len(cue['text']) or first >= last:
        return False
    cue['text'] = cue['text'][first:last]
    cue['original'] = cue['original'][first:last] if len(cue['original']) == last or len(cue['original']) >= last else cue['original']
    for appearance in cue['appearances'].values():
        appearance['runs'] = _slice_runs(appearance['runs'], first, last)
    cue['wordTimings'] = [dict(w, start=w['start']-new_origin, end=w['end']-new_origin,
                               startOffset=w['startOffset']-first, endOffset=w['endOffset']-first)
                          for w in words]
    return True


def trim_clip_with_cues(doc, clip_id, source_start, source_end):
    """Trim one clip and remap its captions in the same atomic document change."""
    result = copy.deepcopy(validate(doc))
    index = next((i for i, item in enumerate(result['clips']) if item['id'] == clip_id), None)
    if index is None:
        raise ValueError('片段不存在。')
    target = result['clips'][index]
    media = result['media'][target['mediaId']]
    limit = 3600 if media['kind'] == 'photo' else media['duration']
    source_start, source_end = float(source_start), float(source_end)
    if source_start < 0 or source_end > limit or source_end - source_start < .1:
        raise ValueError('裁切範圍無效。')

    old_start = sum(c['end'] - c['start'] for c in result['clips'][:index])
    old_end = old_start + target['end'] - target['start']
    keep_start = old_start + source_start - target['start']
    keep_end = old_start + source_end - target['start']
    removed_before = source_start - target['start']
    removed_total = (target['end'] - target['start']) - (source_end - source_start)
    new_cues = []
    for cue in result['cues']:
        updated = copy.deepcopy(cue)
        if cue['end'] <= old_start:
            new_cues.append(updated)
            continue
        if cue['start'] >= old_end:
            updated['start'] -= removed_total
            updated['end'] -= removed_total
            new_cues.append(updated)
            continue
        start, end = max(cue['start'], keep_start), min(cue['end'], keep_end)
        if end - start < .01:
            continue
        clipped = start > cue['start'] + .001 or end < cue['end'] - .001
        updated['start'] = old_start + start - keep_start
        updated['end'] = old_start + end - keep_start
        if clipped:
            if 'translation' in updated: updated['translation']['sourceText'] = ''
            aligned = _trim_aligned_words(updated, start, end, keep_start-old_start)
            marker = ('已依逐字時間裁切，請聆聽邊界。' if aligned else
                      '裁切跨越本句，逐字對齊不可用；請核對文字與語音。')
            updated['note'] = (updated['note'] + ' ' + marker).strip()
            updated['id'] = uuid.uuid4().hex
        new_cues.append(updated)
    target['start'], target['end'] = source_start, source_end
    result['cues'] = sorted(new_cues, key=lambda cue: (cue['start'], cue['end']))
    result['sync'] = 'current'
    return validate(result)


def delete_clip_with_cues(doc, clip_id):
    """Delete one clip and atomically remove/shift captions over its timeline interval."""
    result = copy.deepcopy(validate(doc))
    found = next(((i, item, start, end) for i, (item, start, end) in enumerate(intervals(result))
                  if item['id'] == clip_id), None)
    if found is None: raise ValueError('片段不存在。')
    index, _, cut_start, cut_end = found; removed = cut_end-cut_start
    cues = []
    for cue in result['cues']:
        item = copy.deepcopy(cue)
        if cue['end'] <= cut_start:
            cues.append(item)
        elif cue['start'] >= cut_end:
            item['start'] -= removed; item['end'] -= removed
            for word in item['wordTimings']: word['start'] -= removed; word['end'] -= removed
            cues.append(item)
        else:
            if 'translation' in item: item['translation']['sourceText'] = ''
            left, right = cue['start'] < cut_start, cue['end'] > cut_end
            if not left and not right: continue
            aligned = False
            if left and not right:
                aligned = _trim_aligned_words(item, cue['start'], cut_start, 0)
            elif right and not left:
                aligned = _trim_aligned_words(item, cut_end, cue['end'], removed)
            item['start'] = cue['start'] if left else cut_start
            item['end'] = (cut_start + cue['end']-cut_end) if right else cut_start
            if item['end']-item['start'] < .01: continue
            item['id'] = uuid.uuid4().hex
            if not aligned:
                item['wordTimingState'] = 'edited'
                item['wordTimings'] = []
            marker = ('已依逐字時間裁切，請聆聽邊界。' if aligned else
                      '裁切跨越本句，逐字對齊不可用；請核對文字與語音。')
            item['note'] = (item['note']+' '+marker).strip()
            cues.append(item)
    result['clips'].pop(index); result['cues'] = cues; result['sync'] = 'current'
    return validate(result)
