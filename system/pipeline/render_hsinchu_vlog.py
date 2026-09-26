"""Render pipeline script for 新竹一日遊 Vlog v1 (20260716_hsinchu_day_trip_v1.mp4)."""
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
from system.pipeline.editor_render import caption_assets, compose, ffmpeg, native_tool, render, srt
from system.pipeline.media import require_tool

ROOT = Path("/Users/yunkumom/Desktop/SHINE_macOS/shine_products/shine-ai-video-studio/ai-video-workflow")
PROJECT_ID = "新竹一日遊"
INPUT_DIR = ROOT / "1_input" / PROJECT_ID
PROC_DIR = ROOT / "2_processing" / PROJECT_ID / "v1"
OUTPUT_DIR = ROOT / "3_output" / PROJECT_ID
RELEASE_NAME = "20260716_hsinchu_day_trip_v1"
MUSIC_SRC = INPUT_DIR / "music" / "mixkit-serene-view-443.mp3"

TIMELINE_CONFIG = [
    {
        "id": "seg01",
        "type": "video",
        "file": "IMG_4506.MOV",
        "start": 0.0,
        "duration": 4.5,
        "zh": "悠閒漫步新竹街頭，開啟美好一日遊",
        "en": "A leisurely stroll in Hsinchu to start the day",
        "note": "出發散策，陽光街道",
    },
    {
        "id": "seg02",
        "type": "photo",
        "file": "desktop-imports/IMG_4533.jpg",
        "start": 0.0,
        "duration": 1.5,
        "zh": "午後走訪在地特色茶飲",
        "en": "Exploring a cozy local tea shop",
        "note": "原一茶宴特寫照片",
    },
    {
        "id": "seg03",
        "type": "video",
        "file": "IMG_4526.MOV",
        "start": 0.5,
        "duration": 3.5,
        "zh": "品一口沁涼茶香，放慢日常步調",
        "en": "Savoring refreshing tea at a gentle pace",
        "note": "茶館門口與悠然氛圍",
    },
    {
        "id": "seg04",
        "type": "video",
        "file": "IMG_4558.MOV",
        "start": 2.0,
        "duration": 5.0,
        "zh": "來到頭前溪畔，擁抱開闊的藍天",
        "en": "Reaching the riverbank under vast blue skies",
        "note": "頭前溪畔藍天白雲遠景",
    },
    {
        "id": "seg05",
        "type": "photo",
        "file": "desktop-imports/IMG_4563.jpg",
        "start": 0.0,
        "duration": 1.5,
        "zh": "河岸微風徐徐，綠意盎然",
        "en": "Gentle river breeze amid lush greenery",
        "note": "頭前溪畔綠地特寫照片",
    },
    {
        "id": "seg06",
        "type": "video",
        "file": "IMG_4561.MOV",
        "start": 2.0,
        "duration": 5.0,
        "zh": "清澈溪水靜靜流淌，療癒心靈",
        "en": "Clear running water calming the soul",
        "note": "頭前溪流水特色岩石景致",
    },
    {
        "id": "seg07",
        "type": "video",
        "file": "IMG_4564.MOV",
        "start": 5.0,
        "duration": 5.0,
        "zh": "大片綠茵草原，享受片刻寧靜",
        "en": "Sprawling meadows offering quiet peace",
        "note": "河堤大草原開闊全景",
    },
    {
        "id": "seg08",
        "type": "video",
        "file": "IMG_4598.MOV",
        "start": 1.0,
        "duration": 4.0,
        "zh": "晚餐走進高人氣的漢神鐵板燒",
        "en": "Heading to Hanshin Teppanyaki for dinner",
        "note": "漢神鐵板燒入座與店景",
    },
    {
        "id": "seg09",
        "type": "photo",
        "file": "desktop-imports/IMG_4604.jpg",
        "start": 0.0,
        "duration": 1.5,
        "zh": "主廚嚴選套餐，現選時令鮮味",
        "en": "Chef's special set with seasonal flavors",
        "note": "鐵板燒精緻食材特寫照片",
    },
    {
        "id": "seg10",
        "type": "video",
        "file": "IMG_4602.MOV",
        "start": 3.0,
        "duration": 5.5,
        "zh": "鐵板高溫炙烤，香氣四溢滋滋作響",
        "en": "Sizzling on the griddle with rich aromas",
        "note": "主廚現場翻炒鐵板料理",
    },
    {
        "id": "seg11",
        "type": "video",
        "file": "IMG_4605.MOV",
        "start": 2.0,
        "duration": 4.5,
        "zh": "鮮嫩多汁的排餐，火候恰到好處",
        "en": "Tender steak grilled to golden perfection",
        "note": "熱騰騰排餐起鍋",
    },
    {
        "id": "seg12",
        "type": "video",
        "file": "IMG_4611.MOV",
        "start": 5.0,
        "duration": 5.0,
        "zh": "每一口都是熱氣騰騰的幸福滋味",
        "en": "Every bite is warm, flavorful happiness",
        "note": "主廚精緻擺盤與用餐美味",
    },
    {
        "id": "seg13",
        "type": "photo",
        "file": "desktop-imports/IMG_4675.jpg",
        "start": 0.0,
        "duration": 1.5,
        "zh": "尋訪老字號名店「竹蓮肉圓」",
        "en": "Visiting the legendary Zhulian Meatballs",
        "note": "西大路竹蓮肉圓店招照片",
    },
    {
        "id": "seg14",
        "type": "video",
        "file": "IMG_4677.MOV",
        "start": 1.0,
        "duration": 4.5,
        "zh": "飄香多年的在地排隊銅板小吃",
        "en": "A beloved street food spot with long queues",
        "note": "竹蓮肉圓門口排隊人潮",
    },
    {
        "id": "seg15",
        "type": "video",
        "file": "IMG_4680.mov",
        "start": 1.0,
        "duration": 5.0,
        "zh": "溫油慢火浸炸，外皮晶瑩軟Ｑ",
        "en": "Slow-fried to tender and chewy perfection",
        "note": "慢火低溫浸炸紅糟肉圓",
    },
    {
        "id": "seg16",
        "type": "photo",
        "file": "desktop-imports/IMG_4685.jpg",
        "start": 0.0,
        "duration": 1.5,
        "zh": "淋上特調甜辣醬，令人食指大動",
        "en": "Topped with savory sauce, pure comfort",
        "note": "紅糟肉圓特寫照片",
    },
    {
        "id": "seg17",
        "type": "video",
        "file": "IMG_4686.MOV",
        "start": 2.0,
        "duration": 5.0,
        "zh": "搭一碗招牌骨仔肉湯，滿足收尾",
        "en": "Paired with classic bone broth to wrap up",
        "note": "滿滿料的骨仔肉湯與滿足享用",
    },
]


def probe_file(path: Path) -> dict:
    cmd = [
        require_tool("ffprobe"),
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s["codec_type"] == "video"), None)
    audio = any(s["codec_type"] == "audio" for s in streams)
    is_photo = path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    w, h = (int(video["width"]), int(video["height"])) if video else (1920, 1080)
    dur = 5.0 if is_photo else float(data.get("format", {}).get("duration", video.get("duration", 0.0)))
    return {
        "name": path.name,
        "kind": "photo" if is_photo else "video",
        "duration": dur,
        "width": w,
        "height": h,
        "audio": audio,
    }


def main():
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    saved_dir = OUTPUT_DIR / "保存區" / "工作中"
    saved_dir.mkdir(parents=True, exist_ok=True)
    segments_dir = PROC_DIR / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Rendering {PROJECT_ID} Vlog v1 ===")

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
    sources = {}
    total_dur = 0.0
    rendered_seg_files = []

    for idx, item in enumerate(TIMELINE_CONFIG, 1):
        rel_path = item["file"]
        full_path = INPUT_DIR / rel_path
        if not full_path.is_file():
            raise FileNotFoundError(f"Missing source file: {full_path}")

        meta = probe_file(full_path)
        mid = f"media_{idx:02d}_{Path(rel_path).stem}"
        doc["media"][mid] = meta
        sources[mid] = full_path

        seg_dur = float(item["duration"])
        c_id = f"clip_{idx:02d}"
        c = {
            "id": c_id,
            "mediaId": mid,
            "start": float(item["start"]),
            "end": float(item["start"]) + seg_dur,
            "framing": framing(meta["kind"], meta["width"], meta["height"]),
            "rationale": item["note"],
        }
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
        cue_obj["translation"] = {
            "text": item["en"],
            "sourceText": item["zh"],
            "scale": 0.70,
        }
        doc["cues"].append(cue_obj)

        # 2. Render intermediate segment
        seg_file = segments_dir / f"seg_{idx:02d}.mp4"
        if not seg_file.exists():
            print(f"[{idx}/17] Encoding {item['type']} segment: {seg_file.name} ({seg_dur}s)")
            if item["type"] == "photo":
                # Still with blurred backdrop & subtle letterbox + silent stereo audio
                cmd = [
                    require_tool("ffmpeg"),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    str(full_path),
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=48000:cl=stereo",
                    "-t",
                    f"{seg_dur:.3f}",
                    "-filter_complex",
                    "[0:v]split=2[bgsrc][fgsrc];"
                    "[bgsrc]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,gblur=sigma=28[bg];"
                    "[fgsrc]scale=1728:972:force_original_aspect_ratio=decrease[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p[outv]",
                    "-map",
                    "[outv]",
                    "-map",
                    "1:a",
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
                # Video scaled to 1920:1080 16:9 + resampled audio
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
                    "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,format=yuv420p",
                    "-af",
                    "aresample=48000,aformat=channel_layouts=stereo",
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
    print("Mixing original live audio with ducked BGM...")
    # Original audio is boosted slightly (volume=1.0), music volume is 0.18 with sidechain ducking
    filter_graph = (
        f"[0:v]fade=t=in:st=0:d=0.4,fade=t=out:st={total_dur-0.6:.3f}:d=0.6[vout];"
        f"[1:a]atrim=0:{total_dur:.3f},afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out_start:.3f}:d=1.5,volume=0.20[music];"
        f"[0:a]volume=0.9[orig];"
        f"[music][orig]sidechaincompress=threshold=0.08:ratio=6:attack=20:release=300[ducked];"
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
    print("Rendering native bilingual typography overlays (PingFang TC + Arial Bold)...")
    captions_dir, records = caption_assets(doc, "horizontal", PROC_DIR / "desktop-assets", size=(1920, 1080))
    blank = captions_dir / "blank.png"
    ffmpeg([
        "-f", "lavfi",
        "-i", "color=black@0:s=1920x1080,format=rgba",
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

    # 7. Validate & Save project.json and sources.json for desktop editor
    validated_doc = validate(doc, render=True)
    atomic_json(saved_dir / "project.json", validated_doc)
    atomic_json(saved_dir / "previous-project.json", validated_doc)
    rel_sources = {k: str(v.relative_to(INPUT_DIR)) for k, v in sources.items()}
    atomic_json(saved_dir / "sources.json", rel_sources)
    print(f"Saved editor project.json and sources.json into {saved_dir}")

    print("=== Render completed successfully! ===")


if __name__ == "__main__":
    main()
