from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Sequence

from .media import MediaInfo


def _timestamp(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def review_path_for_output(output: Path) -> Path:
    if output.stem.startswith("final"):
        match = re.fullmatch(r"final(_v\d+)?", output.stem)
        if match:
            return output.with_name(f"review{match.group(1) or ''}.html")
    return output.with_suffix(".html")


def build_review_html(
    *,
    project_id: str,
    output_name: str,
    sources: Sequence[tuple[Path, MediaInfo]],
) -> str:
    rows: list[str] = []
    cursor = 0.0
    for index, (source, info) in enumerate(sources, start=1):
        start = cursor
        cursor += info.duration
        kind = "Photo / 照片" if info.is_still else "Video / 影片"
        key = f"source-{index}"
        rows.append(
            f"""
            <tr>
              <td data-label="No.">{index}</td>
              <td data-label="Source / 素材"><strong>{html.escape(source.name)}</strong><br><span class="muted">{kind} · {info.width}×{info.height}</span></td>
              <td data-label="Source duration / 素材長度"><code>{_timestamp(info.duration)}</code>{'<br><span class="hint">Default still duration / 照片預設停留</span>' if info.is_still else ''}</td>
              <td data-label="Timeline / 時間軸"><code>{_timestamp(start)}</code><br>→ <code>{_timestamp(cursor)}</code></td>
              <td data-label="Trim / 裁切"><label>裁切起點 / Trim in<input data-field="{key}-trim-in" value="00:00:00.000"></label><label>裁切終點 / Trim out<input data-field="{key}-trim-out" value="{_timestamp(info.duration)}"></label></td>
              <td data-label="Subtitle / 字幕"><label>字幕 / Subtitle<textarea data-field="{key}-subtitle" placeholder="輸入要加上的字幕 / Enter subtitle text"></textarea></label><label>字幕修正 / Correction<textarea data-field="{key}-correction" placeholder="記錄字幕修正 / Record corrections"></textarea></label></td>
              <td data-label="Notes / 備註"><textarea data-field="{key}-notes" placeholder="剪輯、轉場、畫面或音樂備註 / Editing, transition, visual, or music notes"></textarea></td>
            </tr>"""
        )

    escaped_project = html.escape(project_id)
    escaped_output = html.escape(output_name, quote=True)
    storage_key = json.dumps(f"shine-video-review:{project_id}:{output_name}", ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escaped_project} — Video Review / 影片剪輯工作表</title>
  <style>
    :root{{--ink:#172033;--muted:#667085;--line:#d8dee9;--paper:#fff;--wash:#f5f7fb;--brand:#155eef;--ok:#067647}}
    *{{box-sizing:border-box}} body{{margin:0;background:var(--wash);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC",sans-serif}}
    main{{max-width:1500px;margin:auto;padding:32px}} header,.panel{{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:24px;margin-bottom:20px;box-shadow:0 8px 24px rgba(16,24,40,.05)}}
    h1{{margin:0 0 6px;font-size:28px}} h2{{margin:0 0 12px;font-size:20px}} p{{margin:6px 0}} .muted,.hint{{color:var(--muted)}} .hint{{font-size:12px}} .summary{{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}} .pill{{background:#eef4ff;border-radius:999px;padding:7px 12px}}
    video{{display:block;width:min(100%,960px);max-height:540px;background:#000;border-radius:12px;margin-top:14px}} .actions{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 0}}
    button{{border:0;border-radius:9px;padding:10px 14px;background:var(--brand);color:white;font-weight:650;cursor:pointer}} button.secondary{{background:#344054}} #status{{color:var(--ok);align-self:center}}
    .table-wrap{{overflow:auto}} table{{width:100%;border-collapse:collapse;min-width:1250px}} th,td{{border:1px solid var(--line);padding:12px;vertical-align:top;text-align:left}} th{{background:#eef2f8;position:sticky;top:0}} label{{display:block;font-size:12px;font-weight:650;margin-bottom:8px}}
    input,textarea{{display:block;width:100%;margin-top:4px;border:1px solid #b8c1cf;border-radius:7px;padding:8px;background:white;font:inherit;font-weight:400}} textarea{{min-height:72px;resize:vertical}} code{{white-space:nowrap}}
    .general textarea{{min-height:120px}} @media(max-width:720px){{main{{padding:14px}} header,.panel{{padding:16px}} h1{{font-size:23px}}}}
    @media print{{body{{background:white}} main{{max-width:none;padding:0}} header,.panel{{box-shadow:none;break-inside:avoid}} .actions,video{{display:none}}}}
  </style>
</head>
<body>
<main>
  <header>
    <p class="muted">Video Review Worksheet / 影片剪輯工作表</p>
    <h1>{escaped_project}</h1>
    <p>Fill in trim times, subtitles, corrections, and editing notes. Entries save automatically in this browser.</p>
    <p>請填寫裁切時間、字幕、字幕修正與剪輯備註；內容會自動儲存在目前瀏覽器。</p>
    <div class="summary"><span class="pill">Sources / 素材：{len(sources)}</span><span class="pill">Combined duration / 合併長度：{_timestamp(cursor)}</span><span class="pill">Output / 輸出：{escaped_output}</span></div>
    <video controls preload="metadata" src="{escaped_output}"></video>
    <div class="actions"><button type="button" id="save">Save / 儲存</button><button type="button" class="secondary" id="export">Export JSON / 匯出 JSON</button><button type="button" class="secondary" onclick="window.print()">Print / 列印</button><span id="status" aria-live="polite"></span></div>
  </header>
  <section class="panel">
    <h2>Source timeline / 素材時間軸</h2>
    <p class="muted">Times are measured within each original source. Photo durations are initial defaults and may be noted for revision.</p>
    <p class="muted">裁切時間以各原始素材為準；照片長度是初始預設值，可在備註中提出調整。</p>
    <div class="table-wrap"><table><thead><tr><th>No.</th><th>Source / 素材</th><th>Source duration / 素材長度</th><th>Combined timeline / 合併時間軸</th><th>Trim / 裁切</th><th>Subtitle / 字幕</th><th>Notes / 備註</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
  </section>
  <section class="panel general"><h2>Overall notes / 整體備註</h2><textarea data-field="overall-notes" placeholder="音樂、節奏、封面、輸出版本或其他整體需求 / Music, pacing, cover, output version, or other overall requirements"></textarea></section>
</main>
<script>
(() => {{
  const storageKey = {storage_key};
  const fields = [...document.querySelectorAll('[data-field]')];
  const status = document.getElementById('status');
  const collect = () => Object.fromEntries(fields.map(el => [el.dataset.field, el.value]));
  const save = () => {{ localStorage.setItem(storageKey, JSON.stringify(collect())); status.textContent = 'Saved / 已儲存'; setTimeout(() => status.textContent = '', 1600); }};
  try {{ const saved = JSON.parse(localStorage.getItem(storageKey) || '{{}}'); fields.forEach(el => {{ if (Object.hasOwn(saved, el.dataset.field)) el.value = saved[el.dataset.field]; }}); }} catch (_) {{}}
  fields.forEach(el => el.addEventListener('input', save));
  document.getElementById('save').addEventListener('click', save);
  document.getElementById('export').addEventListener('click', () => {{
    save();
    const blob = new Blob([JSON.stringify({{project:{json.dumps(project_id, ensure_ascii=False)}, output:{json.dumps(output_name, ensure_ascii=False)}, fields:collect()}}, null, 2)], {{type:'application/json'}});
    const link = Object.assign(document.createElement('a'), {{href:URL.createObjectURL(blob), download:'video-review.json'}});
    link.click(); setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }});
}})();
</script>
</body>
</html>
"""


def write_review_html(
    path: Path,
    *,
    project_id: str,
    output_name: str,
    sources: Sequence[tuple[Path, MediaInfo]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_review_html(
            project_id=project_id,
            output_name=output_name,
            sources=sources,
        ),
        encoding="utf-8",
    )
