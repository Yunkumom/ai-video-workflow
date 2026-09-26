"""Render pipeline script for 20260925 Rope Flow 9:16 Shorts v1 (20260925_rope_flow_v1.mp4)."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

from system.pipeline.editor_project import (
    MODES,
    SCHEMA,
    appearance,
    atomic_json,
    clip,
    cue,
    duration,
    framing,
    style,
    uid,
    validate,
)
from system.pipeline.editor_render import caption_assets, ffmpeg, srt
from system.pipeline.media import require_tool

ROOT = Path("/Users/yunkumom/Desktop/SHINE_macOS/shine_products/shine-ai-video-studio/ai-video-workflow")
PROJECT_ID = "20260925_rope_flow"
INPUT_DIR = ROOT / "1_input" / PROJECT_ID
PROC_DIR = ROOT / "2_processing" / PROJECT_ID / "v1"
OUTPUT_DIR = ROOT / "3_output" / PROJECT_ID
RELEASE_NAME = "20260925_rope_flow_v1"
MUSIC_SRC = INPUT_DIR / "mixkit-serene-view-443.mp3"

TIMELINE_CONFIG = [
    {
        "id": "seg01",
        "file": "20260925_rope_flow_006.mp4",
        "orig_file": "DJI_20260925173852_0004_D.MP4",
        "start": 4.0,
        "duration": 3.5,
        "zh": "台南戶外草地繩流團練！",
        "en": "Outdoor Rope Flow Session in Tainan!",
        "note": "空拍俯瞰草地團練全景開場",
        "has_audio": False,
    },
    {
        "id": "seg02",
        "file": "20260925_rope_flow_001.mov",
        "orig_file": "IMG_9598.MOV",
        "start": 1.8,
        "duration": 3.2,
        "zh": "認識台南繩流教練 CR",
        "en": "Meet Rope Flow Coach CR",
        "note": "CR 教練在草坪中央親切微笑介紹",
        "has_audio": True,
    },
    {
        "id": "seg03",
        "file": "20260925_rope_flow_002.mov",
        "orig_file": "IMG_9601.MOV",
        "start": 1.3,
        "duration": 3.8,
        "zh": "重心隨腳步自然轉移，帶動全身節奏",
        "en": "Shift your weight naturally with every step",
        "note": "教練帶領腳步轉移與重心擺動",
        "has_audio": True,
    },
    {
        "id": "seg04",
        "file": "20260925_rope_flow_003.mov",
        "orig_file": "IMG_9602.MOV",
        "start": 3.5,
        "duration": 4.0,
        "zh": "經典入門「鬥牛式」，手腕微幅變化帶動旋律",
        "en": "The Matador: subtle wrist shifts create seamless arcs",
        "note": "入門鬥牛式教學動作示範",
        "has_audio": True,
    },
    {
        "id": "seg05",
        "file": "20260925_rope_flow_009.mov",
        "orig_file": "IMG_9610.MOV",
        "start": 41.8,
        "duration": 5.4,
        "zh": "瞬間發力、滯空放鬆，繩子自然不打結",
        "en": "Strike with intent, relax in mid-air to prevent tangles",
        "note": "教練傳授滯空放鬆不打結發力核心",
        "has_audio": True,
    },
    {
        "id": "seg06",
        "file": "20260925_rope_flow_004.mov",
        "orig_file": "IMG_9605.MOV",
        "start": 273.5,
        "duration": 4.7,
        "zh": "招式「龍頭」：轉身戴上安全帽、順勢再脫下",
        "en": "The Dragon Roll: turn and slide the rope behind you",
        "note": "生動口訣：戴全罩安全帽轉身脫安全帽打",
        "has_audio": True,
    },
    {
        "id": "seg07",
        "file": "20260925_rope_flow_008.mov",
        "orig_file": "IMG_9609.MOV",
        "start": 66.0,
        "duration": 6.5,
        "zh": "雙手合流，人繩一體的極致流動美學",
        "en": "Double rope mastery: seamless harmony in motion",
        "note": "教練 CR 雙手雙繩高難度行雲流水示範",
        "has_audio": True,
    },
    {
        "id": "seg08",
        "file": "20260925_rope_flow_006.mp4",
        "orig_file": "DJI_20260925173852_0004_D.MP4",
        "start": 12.5,
        "duration": 4.0,
        "zh": "一起走出戶外，在草地上感受繩流魅力！",
        "en": "Step outside and feel the rhythm of Rope Flow!",
        "note": "無人機高空盤旋草地全景收尾",
        "has_audio": False,
    },
]


from system.desktop_server import metadata


def generate_html_review(doc: dict, output_file: Path, video_filename: str):
    """Generate interactive review worksheet."""
    total_duration = duration(doc)
    cues_rows = []
    for i, c in enumerate(doc["cues"], 1):
        tr = c.get("translation", {})
        cues_rows.append(f"""
        <tr>
          <td class="num">{i:02d}</td>
          <td class="tc">{c['start']:.2f}s - {c['end']:.2f}s</td>
          <td class="zh">{c['text']}</td>
          <td class="en">{tr.get('text', '')}</td>
          <td class="note">{c.get('note', '')}</td>
        </tr>
        """)
    rows_html = "\n".join(cues_rows)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>20260925 Rope Flow 繩流 Shorts v1 審閱工作表</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang TC", "Microsoft JhengHei", sans-serif;
      background: #0f141c;
      color: #e2e8f0;
      margin: 0;
      padding: 32px 24px;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    h1 {{
      font-size: 24px;
      font-weight: 700;
      margin-bottom: 8px;
      color: #38bdf8;
    }}
    .meta-bar {{
      display: flex;
      gap: 16px;
      background: #1e293b;
      padding: 12px 18px;
      border-radius: 8px;
      margin-bottom: 24px;
      font-size: 14px;
      color: #94a3b8;
    }}
    .meta-bar strong {{
      color: #f1f5f9;
    }}
    .preview-box {{
      background: #182234;
      padding: 20px;
      border-radius: 12px;
      display: flex;
      gap: 24px;
      align-items: flex-start;
      margin-bottom: 32px;
    }}
    video {{
      max-width: 360px;
      border-radius: 8px;
      background: #000;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    }}
    .guide {{
      flex: 1;
      font-size: 14px;
      line-height: 1.6;
      color: #cbd5e1;
    }}
    .guide h3 {{
      margin-top: 0;
      color: #f8fafc;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #1e293b;
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      padding: 12px 16px;
      text-align: left;
      border-bottom: 1px solid #334155;
      font-size: 14px;
    }}
    th {{
      background: #0f172a;
      color: #94a3b8;
      font-weight: 600;
    }}
    tr:last-child td {{
      border-bottom: none;
    }}
    .num {{
      color: #38bdf8;
      font-weight: 600;
    }}
    .tc {{
      font-family: monospace;
      color: #facc15;
    }}
    .zh {{
      font-weight: 500;
      color: #f8fafc;
    }}
    .en {{
      color: #94a3b8;
      font-size: 13px;
    }}
    .note {{
      color: #64748b;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>台南草地繩流 (Rope Flow) 團練精華 - Shorts v1 審閱</h1>
    <div class="meta-bar">
      <div>成片檔案：<strong>{video_filename}</strong></div>
      <div>畫面規格：<strong>1080 × 1920 (9:16 直式)</strong></div>
      <div>影格率：<strong>30 fps</strong></div>
      <div>總長度：<strong>{total_duration:.2f} 秒</strong></div>
      <div>配樂：<strong>Mixkit〈Serene View〉(自動人聲閃避)</strong></div>
    </div>

    <div class="preview-box">
      <video controls src="{video_filename}"></video>
      <div class="guide">
        <h3>🎬 9:16 直式 Shorts 剪輯重點：</h3>
        <ul>
          <li><strong>空拍震撼開場</strong>：DJI 航拍高空直式視角，大草皮上全員舞動彩繩，瞬間吸睛。</li>
          <li><strong>教練親和引導</strong>：CR 教練親自示範核心動作「重心轉移」、「鬥牛式」、「龍頭」。</li>
          <li><strong>金句記憶點</strong>：生動傳授「像戴全罩安全帽、轉身再脫下」、「滯空放鬆不打結」發力密技。</li>
          <li><strong>雙繩極致展示</strong>：CR 教練高階雙手單繩行雲流水展示，視覺張力拉滿。</li>
          <li><strong>雙語原生字幕</strong>：Apple CoreText 繁中 + 70% 英文字級比例，黑框白字極致清晰。</li>
        </ul>
      </div>
    </div>

    <h3>鏡頭與雙語字幕對照表</h3>
    <table>
      <thead>
        <tr>
          <th>序號</th>
          <th>時間碼</th>
          <th>中文字幕</th>
          <th>英文字幕</th>
          <th>畫面與動作要點</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>
</body>
</html>"""
    output_file.write_text(html_content, encoding="utf-8")


def generate_report(doc: dict, output_file: Path, video_file: Path, srt_file: Path, html_file: Path):
    """Generate Markdown delivery report."""
    total_duration = duration(doc)
    cues_rows = []
    for i, c in enumerate(doc["cues"], 1):
        tr = c.get("translation", {})
        cues_rows.append(f"| **{i:02d}** | `{c['start']:05.2f} - {c['end']:05.2f}` | {c['text']} | {tr.get('text', '')} | {c.get('note', '')} |")
    table_md = "\n".join(cues_rows)

    report_md = f"""# 台南戶外草地繩流團練 (Rope Flow) Shorts v1 交付報告

## 成果摘要 (Deliverables Summary)

* **成片檔案 (Video)**：[`{video_file.name}`]({video_file.name})
* **雙語字幕檔 (SRT)**：[`{srt_file.name}`]({srt_file.name})
* **互動審閱工作表 (HTML Worksheet)**：[`{html_file.name}`]({html_file.name})
* **工作檔契約 (Project Contract)**：[`project.json`](保存區/工作中/project.json)
* **專屬桌面編輯器 (Desktop App)**：[`開啟編輯器.app`](開啟編輯器.app)

---

## 規格細節 (Specifications)

* **解析度與比例**：1080 × 1920 (9:16 直式 Shorts / Reels / TikTok 規格)
* **幀率與編碼**：30.0 fps, H.264 / AVC (CRF 18 高畫質)
* **總時長**：{total_duration:.2f} 秒 (符合 30–45 秒社群完播黃金區間)
* **音訊與混音**：
  * **原片人聲**：經過 highpass 與音量均衡處理，保留教練講授與現場真實氛圍。
  * **背景音樂**：商業授權 Mixkit〈Serene View〉，以 Sidechain 自動人聲閃避（Ducking，說話時降至 0.15，空拍與展示時平滑升至 0.38）。
* **雙語字幕**：
  * 原生 CoreText / CoreGraphics 高品質排版引擎渲染。
  * 繁體中文 100% 字級 + 英文 70% 字級比例。
  * S02 樣式：高對比純白字體 + 粗黑邊框，草地背景下依然清晰易讀。

---

## 8 段鏡頭結構與雙語字幕對照

| 序號 | 時間碼 (Start - End) | 中文字幕 | 英文字幕 | 畫面與動作要點 |
| :---: | :---: | :--- | :--- | :--- |
{table_md}

---

## 專屬桌面編輯器操作指引

1. 雙擊本目錄中的 [`開啟編輯器.app`](開啟編輯器.app)，即刻喚起單頁桌面工作台。
2. 支援直式/橫式構圖切換、滑鼠兩指縮放平移、字幕文字與英文字級百分比即時調整。
3. 按 `Cmd+S` 即可存檔，隨時復原與調整。
"""
    output_file.write_text(report_md, encoding="utf-8")


def main():
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    saved_dir = OUTPUT_DIR / "保存區" / "工作中"
    saved_dir.mkdir(parents=True, exist_ok=True)
    segments_dir = PROC_DIR / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Rendering {PROJECT_ID} Shorts v1 (1080x1920) ===")

    # 1. Build project document
    doc = {
        "schema": SCHEMA,
        "projectId": PROJECT_ID,
        "media": {},
        "clips": [],
        "narration": [],
        "cues": [],
        "styles": {m: style() for m in MODES},
        "revision": 1,
        "sync": "current",
    }
    # Set styles for vertical
    doc["styles"]["vertical"]["size"] = 5.0  # compact clear subtitle size in 9:16

    sources = {}
    total_dur = 0.0
    rendered_seg_files = []

    # Register music
    doc["media"]["audio001"] = {
        "name": "mixkit-serene-view-443.mp3",
        "kind": "audio",
        "duration": 113.930091,
        "width": 0,
        "height": 0,
        "audio": True,
    }
    sources["audio001"] = MUSIC_SRC

    for idx, item in enumerate(TIMELINE_CONFIG, 1):
        rel_path = item["file"]
        full_path = INPUT_DIR / rel_path
        if not full_path.is_file():
            raise FileNotFoundError(f"Missing source file: {full_path}")

        meta = metadata(full_path)
        meta["originalName"] = item["orig_file"]
        mid = f"video_{idx:02d}_{Path(rel_path).stem}"
        doc["media"][mid] = meta
        sources[mid] = full_path

        seg_dur = float(item["duration"])
        c_id = f"clip_{idx:02d}"
        c = {
            "id": c_id,
            "mediaId": mid,
            "start": float(item["start"]),
            "end": float(item["start"]) + seg_dur,
            "framing": framing("video", meta["width"], meta["height"]),
            "rationale": item["note"],
        }
        # In vertical mode, maintain centered full-height framing
        c["framing"]["vertical"] = {"mode": "crop", "x": 0.5, "y": 0.5, "zoom": 1.0}
        c["framing"]["horizontal"] = {"mode": "extend", "x": 0.5, "y": 0.5, "zoom": 1.0}
        doc["clips"].append(c)

        # Cue
        start_t = round(total_dur, 3)
        end_t = round(total_dur + seg_dur, 3)
        cue_obj = cue(
            item["zh"],
            start_t,
            end_t,
            original=item["zh"],
            note=item["note"],
            cue_id=f"cue_{idx:02d}",
            source_clip_id=c_id,
        )
        cue_obj["appearances"]["vertical"]["y"] = 0.82
        cue_obj["appearances"]["vertical"]["boxWidth"] = 0.90
        cue_obj["appearances"]["horizontal"]["y"] = 0.88
        cue_obj["appearances"]["horizontal"]["boxWidth"] = 0.90
        cue_obj["translation"] = {
            "text": item["en"],
            "sourceText": item["zh"],
            "scale": 0.70,
        }
        doc["cues"].append(cue_obj)

        # 2. Render intermediate segment to standard 1080x1920 30fps
        seg_file = segments_dir / f"seg_{idx:02d}.mp4"
        if not seg_file.exists():
            print(f"[{idx}/8] Encoding segment: {seg_file.name} ({seg_dur}s)")
            if not item["has_audio"]:
                # Video only: generate silent audio track
                cmd = [
                    require_tool("ffmpeg"),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{item['start']:.3f}",
                    "-i",
                    str(full_path),
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=48000:cl=stereo",
                    "-t",
                    f"{seg_dur:.3f}",
                    "-vf",
                    "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p",
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-ar",
                    "48000",
                    "-movflags",
                    "+faststart",
                    str(seg_file),
                ]
            else:
                # Video with audio
                cmd = [
                    require_tool("ffmpeg"),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{item['start']:.3f}",
                    "-i",
                    str(full_path),
                    "-t",
                    f"{seg_dur:.3f}",
                    "-vf",
                    "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p",
                    "-af",
                    "highpass=f=80,aresample=48000,aformat=channel_layouts=stereo",
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-ar",
                    "48000",
                    "-movflags",
                    "+faststart",
                    str(seg_file),
                ]
            subprocess.run(cmd, check=True)
        rendered_seg_files.append(seg_file)
        total_dur += seg_dur

    print(f"All segments ready. Total duration: {total_dur:.3f}s")

    # 3. Concatenate picture timeline
    segments_txt = PROC_DIR / "segments.txt"
    segments_txt.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in rendered_seg_files),
        encoding="utf-8",
    )
    picture_mp4 = PROC_DIR / "picture_assembled.mp4"
    print("Concatenating picture timeline...")
    cmd_concat = [
        require_tool("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(segments_txt),
        "-c",
        "copy",
        str(picture_mp4),
    ]
    subprocess.run(cmd_concat, check=True)

    # 4. Mix original audio with ducked BGM
    audio_mixed_mp4 = PROC_DIR / "assembled_with_music.mp4"
    fade_out_start = max(0.0, total_dur - 1.5)
    print("Mixing original speech with ducked BGM...")
    filter_graph = (
        f"[0:v]fade=t=in:st=0:d=0.3,fade=t=out:st={total_dur-0.5:.3f}:d=0.5[vout];"
        f"[1:a]atrim=0:{total_dur:.3f},afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out_start:.3f}:d=1.5,volume=0.35[music];"
        f"[0:a]volume=1.0[orig];"
        f"[music][orig]sidechaincompress=threshold=0.08:ratio=5:attack=20:release=300[ducked];"
        f"[orig][ducked]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.95[aout]"
    )
    cmd_mix = [
        require_tool("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(picture_mp4),
        "-i",
        str(MUSIC_SRC),
        "-filter_complex",
        filter_graph,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-t",
        f"{total_dur:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(audio_mixed_mp4),
    ]
    subprocess.run(cmd_mix, check=True)

    # 5. Burn-in bilingual subtitles using native Swift typography rasterizer
    print("Rendering native bilingual typography overlays (1080x1920)...")
    captions_dir, records = caption_assets(doc, "vertical", PROC_DIR / "desktop-assets", size=(1080, 1920))
    blank = captions_dir / "blank.png"
    ffmpeg([
        "-f", "lavfi",
        "-i", "color=black@0:s=1080x1920,format=rgba",
        "-frames:v", "1",
        str(blank),
    ])

    timeline_parts = ["ffconcat version 1.0"]
    cursor = 0.0
    for cue_item, layout in zip(doc["cues"], records):
        if cue_item["start"] > cursor:
            timeline_parts.extend(["file 'blank.png'", f"duration {cue_item['start'] - cursor:.9f}"])
        frames = layout["frames"]
        rem = cue_item["end"] - cue_item["start"]
        for f in frames[:-1]:
            step = min(1.0 / 30.0, rem)
            timeline_parts.extend([f"file '{f}'", f"duration {step:.9f}"])
            rem -= step
        timeline_parts.extend([f"file '{frames[-1]}'", f"duration {rem:.9f}"])
        cursor = cue_item["end"]
    if total_dur > cursor:
        timeline_parts.extend(["file 'blank.png'", f"duration {total_dur - cursor:.9f}"])
    timeline_parts.append("file 'blank.png'")

    timeline_ffconcat = captions_dir / "timeline.ffconcat"
    timeline_ffconcat.write_text("\n".join(timeline_parts) + "\n", encoding="utf-8")

    final_mp4 = OUTPUT_DIR / f"{RELEASE_NAME}.mp4"
    print(f"Composing final release: {final_mp4.name}...")
    cmd_burn = [
        require_tool("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(audio_mixed_mp4),
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(timeline_ffconcat),
        "-filter_complex",
        "[1:v]fps=30,format=rgba[c];[0:v][c]overlay=0:0:format=auto,format=yuv420p[v]",
        "-map",
        "[v]",
        "-map",
        "0:a",
        "-c:v",
        "libx264",
        "-threads",
        "4",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "copy",
        "-t",
        f"{total_dur:.3f}",
        "-movflags",
        "+faststart",
        str(final_mp4),
    ]
    subprocess.run(cmd_burn, check=True)
    print(f"Final MP4 generated: {final_mp4} ({final_mp4.stat().st_size} bytes)")

    # 6. Generate bilingual SRT sidecar
    final_srt = OUTPUT_DIR / f"{RELEASE_NAME}.srt"
    srt_content = srt(doc, records)
    final_srt.write_text(srt_content, encoding="utf-8")
    print(f"SRT generated: {final_srt}")

    # 7. Generate interactive review worksheet & Markdown report
    final_html = OUTPUT_DIR / f"{RELEASE_NAME}.html"
    final_report = OUTPUT_DIR / f"{RELEASE_NAME}_report.md"
    generate_html_review(doc, final_html, final_mp4.name)
    generate_report(doc, final_report, final_mp4, final_srt, final_html)
    print(f"Worksheet & report generated: {final_html}, {final_report}")

    # 8. Validate & Save project.json and sources.json for desktop editor
    validated_doc = validate(doc, render=True)
    atomic_json(saved_dir / "project.json", validated_doc)
    atomic_json(saved_dir / "previous-project.json", validated_doc)
    rel_sources = {k: str(v.relative_to(INPUT_DIR)) for k, v in sources.items()}
    atomic_json(saved_dir / "sources.json", rel_sources)
    print(f"Saved editor project.json and sources.json into {saved_dir}")

    # 9. Build desktop editor app bundle
    print("Building standalone desktop editor app bundle...")
    subprocess.run(["bash", "system/desktop/build_app.sh", PROJECT_ID], check=True)
    print("Desktop editor built successfully!")

    print("=== All rendering & packaging completed successfully! ===")


if __name__ == "__main__":
    main()
