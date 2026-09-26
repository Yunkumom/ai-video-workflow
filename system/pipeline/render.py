from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Sequence

from .media import MediaInfo, kept_intervals, require_tool
from .models import ProjectError
from .planning import parse_srt
from .subtitle_templates import caption_render_options


def build_subtitle_command(
    *,
    source: Path,
    subtitle: Path,
    output: Path,
    has_audio: bool,
    normalize_audio: bool,
) -> list[str]:
    escaped_name = subtitle.name.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    video_filter = (
        f"subtitles=filename='{escaped_name}':"
        "force_style='FontName=Noto Sans CJK TC,FontSize=22,Bold=0,"
        "PrimaryColour=&H00FFFFFF,BackColour=&H2E000000,"
        "BorderStyle=4,Outline=0,Shadow=0,MarginL=60,MarginR=60,MarginV=48,Alignment=2'"
    )
    command = [
        require_tool("ffmpeg"),
        "-y",
        "-i",
        str(source.resolve()),
        "-vf",
        video_filter,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
    ]
    if has_audio:
        if normalize_audio:
            command.extend(["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"])
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    else:
        command.append("-an")
    command.extend(["-movflags", "+faststart", str(output.resolve())])
    return command


def run_command(command: Sequence[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ProjectError(f"media render failed: {result.stderr[-800:]}")


def build_music_mix_command(
    *,
    source: Path,
    music: Path,
    output: Path,
    info: MediaInfo,
    duck_voice: bool,
) -> list[str]:
    duration = max(0.1, float(info.duration))
    fade_out = max(0.0, duration - 0.5)
    music_filter = (
        f"[1:a]aloop=loop=-1:size=2147483647,atrim=duration={duration:.6f},"
        f"afade=t=in:st=0:d=0.5,afade=t=out:st={fade_out:.6f}:d=0.5,volume=0.18[music]"
    )
    if info.has_audio:
        if duck_voice:
            audio_filter = (
                f"{music_filter};[music][0:a]sidechaincompress="
                "threshold=0.05:ratio=8:attack=20:release=300[ducked];"
                "[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
        else:
            audio_filter = f"{music_filter};[0:a][music]amix=inputs=2:duration=first[aout]"
    else:
        audio_filter = f"{music_filter};[music]anull[aout]"
    return [
        require_tool("ffmpeg"),
        "-y",
        "-i",
        str(source.resolve()),
        "-i",
        str(music.resolve()),
        "-filter_complex",
        audio_filter,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-t",
        f"{duration:.6f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output.resolve()),
    ]


def render_with_music(
    source: Path,
    music: Path,
    output: Path,
    *,
    info: MediaInfo,
    duck_voice: bool,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        build_music_mix_command(
            source=source,
            music=music,
            output=output,
            info=info,
            duck_voice=duck_voice,
        ),
        cwd=output.parent,
    )


def ffmpeg_has_filter(name: str) -> bool:
    result = subprocess.run(
        [require_tool("ffmpeg"), "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return any(line.split()[1:2] == [name] for line in result.stdout.splitlines() if line.split())


def _ffconcat_quote(name: str) -> str:
    return name.replace("'", "'\\''")


def _caption_timeline(
    subtitle: Path,
    processing_dir: Path,
    *,
    video_width: int,
    duration: float,
    template_id: str = "S01",
) -> Path:
    cues = parse_srt(subtitle.read_text(encoding="utf-8-sig"))
    caption_dir = processing_dir / "caption-images"
    caption_dir.mkdir(parents=True, exist_ok=True)
    payload_path = processing_dir / "caption-images.json"
    payload_path.write_text(
        json.dumps(
            [{"text": cue.text, "start": cue.start, "end": cue.end} for cue in cues],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    swift_script = Path(__file__).with_name("caption_images.swift")
    command = [
        require_tool("swift"),
        str(swift_script),
        "--input",
        str(payload_path),
        "--output-dir",
        str(caption_dir),
        "--video-width",
        str(video_width),
    ]
    options = caption_render_options(template_id)
    if not options.show_background:
        command.append("--plain")
    if options.fit_background:
        command.append("--fit-background")
    if options.outline:
        command.append("--outline")
    if options.heavy_text:
        command.append("--heavy-text")
    run_command(command)

    segments: list[tuple[str, float]] = []
    cursor = 0.0
    for index, cue in enumerate(cues, start=1):
        start = max(cursor, cue.start)
        end = min(duration, cue.end)
        if start > cursor:
            segments.append(("blank.png", start - cursor))
        if end > start:
            segments.append((f"caption-{index:04d}.png", end - start))
            cursor = end
    if cursor < duration:
        segments.append(("blank.png", duration - cursor))
    if not segments:
        segments.append(("blank.png", duration))

    timeline = caption_dir / "timeline.ffconcat"
    lines = ["ffconcat version 1.0"]
    for filename, segment_duration in segments:
        lines.append(f"file '{_ffconcat_quote(filename)}'")
        lines.append(f"duration {segment_duration:.6f}")
    lines.append(f"file '{_ffconcat_quote(segments[-1][0])}'")
    timeline.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return timeline


def render_with_caption_overlays(
    source: Path,
    subtitle: Path,
    output: Path,
    *,
    processing_dir: Path,
    info: MediaInfo,
    normalize_audio: bool,
    template_id: str = "S01",
) -> None:
    timeline = _caption_timeline(
        subtitle,
        processing_dir,
        video_width=info.width,
        duration=info.duration,
        template_id=template_id,
    )
    caption_track = timeline.parent / "caption-track.mov"
    track_command = [
        require_tool("ffmpeg"),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        timeline.name,
        "-vf",
        "fps=30",
        "-t",
        f"{info.duration:.6f}",
        "-c:v",
        "qtrle",
        caption_track.name,
    ]
    run_command(track_command, cwd=timeline.parent)
    command = [
        require_tool("ffmpeg"),
        "-y",
        "-i",
        str(source.resolve()),
        "-i",
        str(caption_track.resolve()),
        "-filter_complex",
        "[0:v][1:v]overlay=x=(W-w)/2:y=H-h-24:shortest=1[vout]",
        "-map",
        "[vout]",
    ]
    if info.has_audio:
        command.extend(["-map", "0:a?"])
        if normalize_audio:
            command.extend(["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"])
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    else:
        command.append("-an")
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-t",
            f"{info.duration:.6f}",
            "-movflags",
            "+faststart",
            str(output.resolve()),
        ]
    )
    run_command(command, cwd=timeline.parent)


def render_with_subtitles(
    source: Path,
    subtitle: Path,
    output: Path,
    *,
    processing_dir: Path,
    info: MediaInfo,
    normalize_audio: bool,
    template_id: str = "S01",
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    # Template rendering uses one AppKit measurement pass so S01 backgrounds and
    # glyphs cannot drift between independent renderers.
    if template_id or not ffmpeg_has_filter("subtitles"):
        render_with_caption_overlays(
            source,
            subtitle,
            output,
            processing_dir=processing_dir,
            info=info,
            normalize_audio=normalize_audio,
            template_id=template_id,
        )
        return
    command = build_subtitle_command(
        source=source,
        subtitle=subtitle,
        output=output,
        has_audio=info.has_audio,
        normalize_audio=normalize_audio,
    )
    run_command(command, cwd=subtitle.parent)


def render_plain(source: Path, output: Path, *, has_audio: bool, normalize_audio: bool = False) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        require_tool("ffmpeg"),
        "-y",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
    ]
    if has_audio:
        if normalize_audio:
            command.extend(["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"])
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    else:
        command.append("-an")
    command.extend(["-movflags", "+faststart", str(output)])
    run_command(command)


def render_cut_timeline(
    source: Path,
    output: Path,
    *,
    info: MediaInfo,
    cuts: Sequence[tuple[float, float]],
) -> None:
    intervals = kept_intervals(info.duration, cuts)
    if not intervals:
        raise ProjectError("edit plan would remove the entire video")
    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, (start, end) in enumerate(intervals):
        filters.append(f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{index}]")
        concat_inputs.append(f"[v{index}]")
        if info.has_audio:
            filters.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{index}]")
            concat_inputs.append(f"[a{index}]")
    outputs = "[vout][aout]" if info.has_audio else "[vout]"
    filters.append(
        "".join(concat_inputs)
        + f"concat=n={len(intervals)}:v=1:a={1 if info.has_audio else 0}{outputs}"
    )
    command = [
        require_tool("ffmpeg"),
        "-y",
        "-i",
        str(source),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[vout]",
    ]
    if info.has_audio:
        command.extend(["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    run_command(command)


def concatenate_sources(
    sources: Sequence[tuple[Path, MediaInfo]],
    processing_dir: Path,
) -> tuple[Path, MediaInfo]:
    if not sources:
        raise ProjectError("no source media were provided")
    if len(sources) == 1 and not sources[0][1].is_still:
        return sources[0]
    processing_dir.mkdir(parents=True, exist_ok=True)
    canvas_info = next((info for _, info in sources if not info.is_still), sources[0][1])
    target_width = canvas_info.width
    target_height = canvas_info.height
    normalized: list[Path] = []
    for index, (source, info) in enumerate(sources):
        target = processing_dir / f"normalized-{index:03d}.mp4"
        command = [require_tool("ffmpeg"), "-y"]
        if info.is_still:
            command.extend(
                ["-loop", "1", "-framerate", "30", "-t", f"{info.duration:.6f}"]
            )
        command.extend(["-i", str(source)])
        if not info.has_audio:
            command.extend(["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
        command.extend(
            [
                "-vf",
                (
                    f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                    f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30"
                ),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
            ]
        )
        if not info.has_audio:
            command.extend(["-shortest"])
        if info.is_still:
            command.extend(["-t", f"{info.duration:.6f}"])
        command.append(str(target))
        run_command(command)
        normalized.append(target)

    concat_list = processing_dir / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{path.name.replace("'", "'\\''")}'\n" for path in normalized),
        encoding="utf-8",
    )
    combined = processing_dir / "combined.mp4"
    run_command(
        [
            require_tool("ffmpeg"),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list.name,
            "-c",
            "copy",
            combined.name,
        ],
        cwd=processing_dir,
    )
    return combined, MediaInfo(
        duration=sum(info.duration for _, info in sources),
        width=target_width,
        height=target_height,
        has_audio=True,
        is_still=False,
    )
