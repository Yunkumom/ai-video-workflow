"""Native review-caption assets shared by HTML preview and final video export."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .media import MediaInfo, require_tool
from .models import ProjectError
from .review_document import validate_review_document
from .render import run_command


def _fingerprint(document: dict[str, Any], info: MediaInfo) -> str:
    payload = {"renderer": 3, "document": document, "width": info.width, "height": info.height}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def render_review_assets(
    document: object, info: MediaInfo, processing_dir: Path
) -> dict[str, Any]:
    checked = validate_review_document(document)
    if info.width < 2 or info.height < 2 or info.duration <= 0:
        raise ProjectError("影片尺寸或長度無效。")
    if abs(float(checked["duration"]) - info.duration) > 0.1:
        raise ProjectError("字幕工作檔與影片長度不符。")
    fingerprint = _fingerprint(checked, info)
    root = processing_dir.resolve()
    asset_dir = root / "review-assets" / fingerprint
    manifest_path = asset_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (asset_dir / "blank.png").is_file() and all((root / row["asset"]).is_file() for row in manifest.get("cues", [])):
            return manifest
    asset_dir.mkdir(parents=True, exist_ok=True)
    input_path = asset_dir / "document.json"
    input_path.write_text(json.dumps(checked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    script = Path(__file__).with_name("review_caption_images.swift")
    result = subprocess.run(
        [require_tool("swift"), str(script), "--input", str(input_path),
         "--output-dir", str(asset_dir), "--width", str(info.width), "--height", str(info.height)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise ProjectError(result.stderr.strip() or "字幕圖片渲染失敗。")
    cues = []
    for index, cue in enumerate(checked["cues"], start=1):
        image = asset_dir / f"caption-{index:04d}.png"
        if not image.is_file():
            raise ProjectError("字幕圖片渲染不完整。")
        cues.append({"id": cue["id"], "start": cue["start"], "end": cue["end"],
                     "asset": str(image.relative_to(root))})
    manifest = {"schema": "shine.review-assets.v1", "fingerprint": fingerprint,
                "width": info.width, "height": info.height, "cues": cues}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def render_review_video(
    source: Path,
    document: object,
    info: MediaInfo,
    processing_dir: Path,
    output: Path,
) -> dict[str, Any]:
    """Export a movie using exactly the full-frame PNG assets exposed to preview."""
    manifest = render_review_assets(document, info, processing_dir)
    root = processing_dir.resolve()
    asset_dir = (root / manifest["cues"][0]["asset"]).parent
    timeline = asset_dir / "timeline.ffconcat"
    lines = ["ffconcat version 1.0"]
    cursor = 0.0
    last = "blank.png"
    for row in manifest["cues"]:
        start, end = max(cursor, float(row["start"])), min(info.duration, float(row["end"]))
        if start > cursor:
            lines.extend(["file 'blank.png'", f"duration {start - cursor:.6f}"])
        if end > start:
            last = Path(row["asset"]).name
            lines.extend([f"file '{last}'", f"duration {end - start:.6f}"])
            cursor = end
    if cursor < info.duration:
        last = "blank.png"
        lines.extend(["file 'blank.png'", f"duration {info.duration - cursor:.6f}"])
    lines.append(f"file '{last}'")
    timeline.write_text("\n".join(lines) + "\n", encoding="utf-8")
    caption_track = asset_dir / "caption-track.mov"
    run_command([require_tool("ffmpeg"), "-y", "-f", "concat", "-safe", "0", "-i", timeline.name,
                 "-vf", "fps=30", "-t", f"{info.duration:.6f}", "-c:v", "qtrle", caption_track.name],
                cwd=asset_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [require_tool("ffmpeg"), "-y", "-i", str(source.resolve()), "-i", str(caption_track.resolve()),
               "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1[vout]", "-map", "[vout]"]
    if info.has_audio:
        command.extend(["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"])
    else:
        command.append("-an")
    command.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-t",
                    f"{info.duration:.6f}", "-movflags", "+faststart", str(output.resolve())])
    run_command(command, cwd=asset_dir)
    return manifest
