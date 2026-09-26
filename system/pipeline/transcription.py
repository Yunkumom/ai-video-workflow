from __future__ import annotations

import json
import math
import os
import subprocess
import urllib.error
import urllib.request
import uuid
import tempfile
from pathlib import Path
from typing import Callable, Mapping

from .media import require_tool
from .models import ProjectError, SubtitleCue
from .planning import build_srt


GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def ensure_network_transcription_allowed(environment: Mapping[str, str] | None = None) -> str:
    env = os.environ if environment is None else environment
    if env.get("AI_VIDEO_ALLOW_NETWORK") != "1":
        raise ProjectError(
            "automatic transcription needs one scoped approval: "
            "set AI_VIDEO_ALLOW_NETWORK=1 for this run"
        )
    key = env.get("GROQ_API_KEY", "").strip()
    if not key:
        raise ProjectError("automatic transcription needs GROQ_API_KEY in the process environment")
    return key


def groq_payload_to_cues(payload: object) -> list[SubtitleCue]:
    if not isinstance(payload, dict):
        raise ProjectError("transcription response is not a JSON object")
    cues: list[SubtitleCue] = []
    for segment in payload.get("segments", []):
        if not isinstance(segment, dict):
            continue
        try:
            start = float(segment["start"])
            end = float(segment["end"])
            text = str(segment["text"]).strip()
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if text and math.isfinite(start) and math.isfinite(end) and 0 <= start < end:
            cues.append(SubtitleCue(start, end, text))
    if not cues:
        raise ProjectError("transcription response contains no timestamped speech")
    return cues


def _multipart(audio_path: Path, model: str) -> tuple[bytes, str]:
    boundary = f"----SHINE{uuid.uuid4().hex}"
    parts: list[bytes] = []

    def field(name: str, value: str) -> None:
        parts.extend(
            [
                f"--{boundary}".encode(),
                f'Content-Disposition: form-data; name="{name}"'.encode(),
                b"",
                value.encode("utf-8"),
            ]
        )

    field("model", model)
    field("response_format", "verbose_json")
    field("timestamp_granularities[]", "segment")
    field("language", "zh")
    parts.extend(
        [
            f"--{boundary}".encode(),
            b'Content-Disposition: form-data; name="file"; filename="audio.mp3"',
            b"Content-Type: audio/mpeg",
            b"",
            audio_path.read_bytes(),
            f"--{boundary}--".encode(),
            b"",
        ]
    )
    return b"\r\n".join(parts), f"multipart/form-data; boundary={boundary}"


def transcribe_groq(
    source: Path,
    output_srt: Path,
    processing_dir: Path,
    *,
    duration: float,
    environment: Mapping[str, str] | None = None,
    progress: Callable[[str], None] | None = None,
) -> Path:
    api_key = ensure_network_transcription_allowed(environment)
    processing_dir.mkdir(parents=True, exist_ok=True)
    windows = audio_windows(duration)
    cues: list[SubtitleCue] = []
    # Every window is visited; memory and upload sizes do not grow with duration.
    with tempfile.TemporaryDirectory(prefix='transcription-', dir=processing_dir) as directory:
        audio_path = Path(directory) / 'audio.mp3'
        for index, (start, length) in enumerate(windows):
            if progress: progress(f'完整辨識 {index + 1}/{len(windows)} 段（{round(start)}/{round(duration)} 秒）')
            extract = [require_tool('ffmpeg'), '-y', '-ss', str(start), '-i', str(source),
                       '-t', str(length), '-vn', '-ac', '1', '-ar', '16000', '-b:a', '32k', str(audio_path)]
            result = subprocess.run(extract, capture_output=True, text=True, check=False)
            if result.returncode != 0: raise ProjectError('音訊擷取失敗，未建立部分字幕。')
            for cue in _request_transcription(audio_path, api_key):
                begin = max(start, start + cue.start, cues[-1].end if cues else 0)
                end = min(start + length, start + cue.end)
                if end > begin: cues.append(SubtitleCue(begin, end, cue.text))
    if not cues: raise ProjectError('完整辨識完成，但沒有可用的語音字幕。')
    output_srt.parent.mkdir(parents=True, exist_ok=True)
    output_srt.write_text(build_srt(cues, duration=duration), encoding='utf-8')
    return output_srt


def audio_windows(duration: float) -> list[tuple[float, float]]:
    if not math.isfinite(duration) or duration <= 0 or duration > 172800:
        raise ProjectError('影片長度必須大於零且不超過 48 小時。')
    return [(float(start), min(600.0, duration - start)) for start in range(0, math.ceil(duration), 600)]


def _request_transcription(audio_path: Path, api_key: str) -> list[SubtitleCue]:
    body, content_type = _multipart(audio_path, "whisper-large-v3-turbo")
    request = urllib.request.Request(
        GROQ_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
            "Accept": "application/json",
            "User-Agent": "shine-video-workflow/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024: raise ProjectError('語音辨識回應過大。')
        payload = json.loads(raw.decode('utf-8'))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ProjectError('Groq 語音辨識失敗，未建立部分字幕。') from None
    if isinstance(payload, dict) and payload.get('segments') == []: return []
    return groq_payload_to_cues(payload)
