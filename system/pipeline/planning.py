from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Sequence

from .models import Project, ProjectError, SubtitleCue


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS
VALID_MODES = {"auto", "tutorial", "silent-footage"}
_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;，,])")
_SRT_TIME = re.compile(
    r"(?P<sh>\d+):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{3})"
    r"\s*-->\s*"
    r"(?P<eh>\d+):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{3})"
)


def discover_project(root: Path, project_id: str) -> Project:
    """Read one shallow input project without consulting environment files."""
    root = root.resolve()
    if not project_id or project_id in {".", ".."} or "/" in project_id or "\\" in project_id:
        raise ProjectError("project_id must be one folder name")

    input_root = (root / "1_input").resolve()
    input_dir = (input_root / project_id).resolve()
    if input_dir.parent != input_root:
        raise ProjectError("project_id escapes 1_input")
    if not input_dir.is_dir():
        raise ProjectError(f"input project does not exist: {project_id}")

    videos = tuple(
        sorted(
            (
                path
                for path in input_dir.iterdir()
                if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS
            ),
            key=lambda path: path.name.casefold(),
        )
    )
    if not videos:
        raise ProjectError(f"input project contains no supported media: {input_dir}")

    settings_path = input_dir / "settings.json"
    settings: dict[str, object] = {}
    if settings_path.exists():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectError(f"invalid settings.json: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ProjectError("settings.json must contain a JSON object")
        settings = loaded

    script_path = input_dir / "script.md"
    subtitle_paths = tuple(
        sorted(
            (path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() == ".srt"),
            key=lambda path: path.name.casefold(),
        )
    )
    return Project(
        project_id=project_id,
        root=root,
        input_dir=input_dir,
        processing_dir=root / "2_processing" / project_id,
        output_dir=root / "3_output" / project_id,
        videos=videos,
        script_path=script_path if script_path.is_file() else None,
        subtitle_paths=subtitle_paths,
        settings=dict(settings),
    )


def order_project_sources(
    sources: Sequence[Path], settings: dict[str, object]
) -> tuple[Path, ...]:
    """Apply an explicit safe filename order when the project provides one."""
    requested = settings.get("source_order")
    if requested is None:
        return tuple(sources)
    if not isinstance(requested, list) or not all(isinstance(item, str) for item in requested):
        raise ProjectError("source_order must be a list of filenames")
    available = {path.name for path in sources}
    if len(requested) != len(sources) or set(requested) != available:
        raise ProjectError("source_order must list every discovered media file exactly once")
    by_name = {path.name: path for path in sources}
    return tuple(by_name[name] for name in requested)


def select_mode(
    explicit: str | None,
    *,
    has_subtitles: bool,
    has_script: bool,
    has_audio: bool,
) -> str:
    requested = explicit or "auto"
    if requested not in VALID_MODES:
        raise ProjectError(f"unsupported mode: {requested}")
    if requested != "auto":
        return requested
    if has_subtitles:
        return "tutorial"
    if has_script:
        return "silent-footage"
    if has_audio:
        return "tutorial"
    return "silent-footage"


def split_script(text: str, max_chars: int = 28) -> list[str]:
    """Split prose into readable, bounded caption blocks."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    normalized = re.sub(r"[\t\r\n ]+", "", text.strip())
    if not normalized:
        return []

    units = [part for part in _SENTENCE_BOUNDARY.split(normalized) if part]
    blocks: list[str] = []
    current = ""
    for unit in units:
        while len(unit) > max_chars:
            if current:
                blocks.append(current)
                current = ""
            blocks.append(unit[:max_chars])
            unit = unit[max_chars:]
        if not unit:
            continue
        if current and len(current) + len(unit) > max_chars:
            blocks.append(current)
            current = unit
        else:
            current += unit
    if current:
        blocks.append(current)
    return blocks


def _format_timestamp(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _parse_timestamp(match: re.Match[str], prefix: str) -> float:
    return (
        int(match.group(f"{prefix}h")) * 3600
        + int(match.group(f"{prefix}m")) * 60
        + int(match.group(f"{prefix}s"))
        + int(match.group(f"{prefix}ms")) / 1000
    )


def build_srt(
    blocks_or_cues: Sequence[str] | Sequence[SubtitleCue],
    *,
    duration: float,
) -> str:
    if duration <= 0:
        raise ValueError("duration must be positive")
    if not blocks_or_cues:
        return ""

    first = blocks_or_cues[0]
    if isinstance(first, SubtitleCue):
        cues = list(blocks_or_cues)  # type: ignore[arg-type]
    else:
        blocks = [str(block) for block in blocks_or_cues]
        weights = [max(1, len(block.replace("\n", ""))) for block in blocks]
        total_weight = sum(weights)
        cues: list[SubtitleCue] = []
        elapsed_weight = 0
        for index, (block, weight) in enumerate(zip(blocks, weights)):
            start = duration * elapsed_weight / total_weight
            elapsed_weight += weight
            end = duration if index == len(blocks) - 1 else duration * elapsed_weight / total_weight
            cues.append(SubtitleCue(start, end, block))

    lines: list[str] = []
    for index, cue in enumerate(cues, start=1):
        if cue.end <= cue.start:
            raise ValueError("subtitle cue end must be after start")
        lines.extend(
            [
                str(index),
                f"{_format_timestamp(cue.start)} --> {_format_timestamp(cue.end)}",
                cue.text,
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def parse_srt(text: str) -> list[SubtitleCue]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    cues: list[SubtitleCue] = []
    for block in re.split(r"\n{2,}", normalized):
        lines = block.splitlines()
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            raise ValueError("subtitle block is missing a timestamp")
        match = _SRT_TIME.fullmatch(lines[time_index].strip())
        if not match:
            raise ValueError(f"invalid subtitle timestamp: {lines[time_index]}")
        text_lines = lines[time_index + 1 :]
        if not text_lines:
            raise ValueError("subtitle block is missing text")
        start = _parse_timestamp(match, "s")
        end = _parse_timestamp(match, "e")
        if end <= start:
            raise ValueError("subtitle cue end must be after start")
        if cues and start < cues[-1].start:
            raise ValueError("subtitle cues are not monotonic")
        cues.append(SubtitleCue(start, end, "\n".join(text_lines)))
    return cues


def next_output_path(output_dir: Path, project_id: str) -> Path:
    pattern = re.compile(rf"{re.escape(project_id)}_v(\d+)\.mp4")
    versions = [
        int(match.group(1))
        for path in output_dir.glob(f"{project_id}_v*.mp4")
        if (match := pattern.fullmatch(path.name))
    ] if output_dir.exists() else []
    return output_dir / f"{project_id}_v{max(versions, default=0) + 1}.mp4"


def versioned_output_path(output_dir: Path, project_id: str, version: int) -> Path:
    if version < 1:
        raise ProjectError("version must be a positive integer")
    output = output_dir / f"{project_id}_v{version}.mp4"
    if output.exists():
        raise ProjectError(f"output already exists: {output.name}")
    return output


def _normalize_spoken_text(text: str) -> str:
    return re.sub(r"[^\w\u3400-\u9fff]+", "", text, flags=re.UNICODE).casefold()


def find_exact_retake_cuts(
    cues: Sequence[SubtitleCue],
    *,
    max_gap: float = 1.5,
    min_chars: int = 4,
) -> list[tuple[float, float]]:
    """Conservatively remove only exact adjacent retakes, keeping the later take."""
    cuts: list[tuple[float, float]] = []
    for earlier, later in zip(cues, cues[1:]):
        earlier_text = _normalize_spoken_text(earlier.text)
        later_text = _normalize_spoken_text(later.text)
        if (
            len(earlier_text) >= min_chars
            and earlier_text == later_text
            and 0 <= later.start - earlier.end <= max_gap
        ):
            cuts.append((earlier.start, earlier.end))
    return cuts


def _removed_before(time_value: float, cuts: Sequence[tuple[float, float]]) -> float:
    removed = 0.0
    for start, end in cuts:
        if time_value >= end:
            removed += end - start
        elif time_value > start:
            removed += time_value - start
    return removed


def remap_cues_after_cuts(
    cues: Sequence[SubtitleCue],
    cuts: Sequence[tuple[float, float]],
) -> list[SubtitleCue]:
    ordered_cuts = sorted(cuts)
    remapped: list[SubtitleCue] = []
    for cue in cues:
        fully_removed = any(start <= cue.start and end >= cue.end for start, end in ordered_cuts)
        if fully_removed:
            continue
        new_start = cue.start - _removed_before(cue.start, ordered_cuts)
        new_end = cue.end - _removed_before(cue.end, ordered_cuts)
        if new_end - new_start < 0.05:
            continue
        remapped.append(SubtitleCue(max(0.0, new_start), max(0.0, new_end), cue.text))
    return remapped


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
