from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .models import ProjectError


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    width: int
    height: int
    has_audio: bool
    is_still: bool = False


def require_tool(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise ProjectError(f"required macOS command is unavailable: {name}")
    return resolved


def probe_media(path: Path, *, still_duration: float = 5.0) -> MediaInfo:
    command = [
        require_tool("ffprobe"),
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ProjectError(f"ffprobe failed for {path.name}: {result.stderr[-400:]}")
    is_still = path.suffix.lower() in IMAGE_EXTENSIONS
    try:
        payload = json.loads(result.stdout)
        streams = payload.get("streams", [])
        video = next(stream for stream in streams if stream.get("codec_type") == "video")
        duration = (
            still_duration
            if is_still
            else float(payload.get("format", {}).get("duration") or video.get("duration"))
        )
        width = int(video["width"])
        height = int(video["height"])
        rotation = video.get("tags", {}).get("rotate", 0)
        for side_data in video.get("side_data_list", []):
            if "rotation" in side_data:
                rotation = side_data["rotation"]
                break
        try:
            if abs(float(rotation)) % 180 == 90:
                width, height = height, width
        except (TypeError, ValueError):
            pass
    except (StopIteration, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProjectError(f"invalid ffprobe metadata for {path.name}") from exc
    return MediaInfo(
        duration=duration,
        width=width,
        height=height,
        has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
        is_still=is_still,
    )


def parse_silence_log(log: str) -> list[tuple[float, float]]:
    starts: list[float] = []
    intervals: list[tuple[float, float]] = []
    for line in log.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            starts.append(float(start_match.group(1)))
            continue
        end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end_match and starts:
            intervals.append((starts.pop(0), float(end_match.group(1))))
    return intervals


def detect_silences(path: Path, *, threshold_db: float, min_silence: float) -> list[tuple[float, float]]:
    command = [
        require_tool("ffmpeg"),
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-af",
        f"silencedetect=noise={threshold_db}dB:d={min_silence}",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode not in {0, 1}:
        raise ProjectError(f"silence detection failed: {result.stderr[-400:]}")
    return parse_silence_log(result.stderr)


def build_silence_cuts(
    silences: Sequence[tuple[float, float]],
    *,
    duration: float,
    min_silence: float,
    keep_pause: float,
) -> list[tuple[float, float]]:
    cuts: list[tuple[float, float]] = []
    edge = keep_pause / 2
    for start, end in silences:
        start = max(0.0, start)
        end = min(duration, end)
        if end - start < min_silence:
            continue
        cut_start = start + (edge if start > 0 else 0.0)
        cut_end = end - (edge if end < duration else 0.0)
        if cut_end > cut_start:
            cuts.append((round(cut_start, 6), round(cut_end, 6)))
    return merge_cuts(cuts)


def merge_cuts(cuts: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(cuts):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def kept_intervals(duration: float, cuts: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in merge_cuts(cuts):
        if start > cursor:
            keep.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        keep.append((cursor, duration))
    return [(start, end) for start, end in keep if end - start >= 0.05]
