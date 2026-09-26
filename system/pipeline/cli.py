from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path

from .media import build_silence_cuts, detect_silences, merge_cuts, probe_media
from .models import ProjectError
from .planning import (
    build_srt,
    discover_project,
    find_exact_retake_cuts,
    next_output_path,
    order_project_sources,
    parse_srt,
    remap_cues_after_cuts,
    select_mode,
    split_script,
    versioned_output_path,
    write_json,
)
from .music import build_license_record, download_track, load_catalog, select_track
from .render import (
    concatenate_sources,
    render_cut_timeline,
    render_plain,
    render_with_music,
    render_with_subtitles,
)
from .review import review_path_for_output, write_review_html
from .transcription import transcribe_groq
from .subtitle_templates import (
    caption_limit,
    get_template,
    resegment_cues,
    segment_caption_text,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_defaults(root: Path) -> dict[str, object]:
    config_path = root / "system/config/defaults.json"
    if not config_path.is_file():
        config_path = _repo_root() / "system/config/defaults.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


def _choose_sidecar(project, requested_name: str | None = None) -> Path | None:
    if not project.subtitle_paths:
        return None
    if requested_name:
        requested = project.input_dir / requested_name
        if requested not in project.subtitle_paths:
            raise ProjectError(f"requested subtitle file is not in the project: {requested_name}")
        return requested
    if len(project.videos) == 1:
        exact = project.input_dir / f"{project.videos[0].stem}.srt"
        if exact in project.subtitle_paths:
            return exact
    if len(project.subtitle_paths) == 1:
        return project.subtitle_paths[0]
    raise ProjectError("multiple subtitle files are ambiguous; match the SRT name to the video")


def _report(
    report_path: Path,
    *,
    mode: str,
    output: Path,
    subtitle: Path | None,
    cuts: list[tuple[float, float]],
    music: Path | None,
    music_reason: str | None,
) -> None:
    lines = [
        "# Video Result / 影片成果",
        "",
        f"- Mode / 模式: `{mode}`",
        "- Aspect ratio / 畫面比例: `original`",
        f"- Output / 輸出: `{output.name}`",
        f"- Subtitle / 字幕: `{subtitle.name}`" if subtitle else "- Subtitle / 字幕: none / 無",
        f"- Automatic cuts / 自動裁切: {len(cuts)}",
        f"- Background music / 背景音樂: `{music.name}`" if music else "- Background music / 背景音樂: none / 無",
        f"- Music note / 音樂備註: {music_reason}" if music_reason else "- Music note / 音樂備註: verified / 已驗證",
        "- AI narration / AI 語音: disabled / 停用",
        "",
        "Ambiguous speech was preserved. / 無法確定的語音內容已保留。",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _tutorial(
    project,
    info,
    defaults: dict[str, object],
    output: Path,
    subtitle_file: str | None = None,
) -> tuple[Path, list[tuple[float, float]]]:
    if len(project.videos) != 1:
        raise ProjectError("tutorial mode currently accepts one source video per project")
    source = project.videos[0]
    sidecar = _choose_sidecar(project, subtitle_file)
    working_srt = project.processing_dir / "subtitles-source.srt"
    if sidecar:
        shutil.copy2(sidecar, working_srt)
    else:
        transcribe_groq(
            source,
            working_srt,
            project.processing_dir,
            duration=info.duration,
            environment=os.environ,
        )
    cues = parse_srt(working_srt.read_text(encoding="utf-8-sig"))
    subtitle_defaults = defaults.get("subtitles", {})
    assert isinstance(subtitle_defaults, dict)
    template_id = str(
        getattr(project, "settings", {}).get(
            "subtitle_template", subtitle_defaults.get("default_template", "S01")
        )
    )
    get_template(template_id)
    cues = resegment_cues(
        cues,
        max_chars_per_line=caption_limit(width=info.width, height=info.height),
        max_lines=int(subtitle_defaults.get("max_lines", 2)),
    )

    tutorial_defaults = defaults["tutorial"]
    assert isinstance(tutorial_defaults, dict)
    silences = detect_silences(
        source,
        threshold_db=float(tutorial_defaults["silence_threshold_db"]),
        min_silence=float(tutorial_defaults["min_silence_seconds"]),
    )
    cuts = build_silence_cuts(
        silences,
        duration=info.duration,
        min_silence=float(tutorial_defaults["min_silence_seconds"]),
        keep_pause=float(tutorial_defaults["keep_pause_seconds"]),
    )
    cuts = merge_cuts([*cuts, *find_exact_retake_cuts(cues)])
    timeline_source = source
    timeline_info = info
    if cuts:
        timeline_source = project.processing_dir / "edited-timeline.mp4"
        render_cut_timeline(source, timeline_source, info=info, cuts=cuts)
        new_duration = info.duration - sum(end - start for start, end in cuts)
        timeline_info = type(info)(new_duration, info.width, info.height, info.has_audio)
        cues = remap_cues_after_cuts(cues, cuts)

    final_srt = output.with_suffix(".srt")
    final_srt.parent.mkdir(parents=True, exist_ok=True)
    final_srt.write_text(build_srt(cues, duration=timeline_info.duration), encoding="utf-8")
    render_with_subtitles(
        timeline_source,
        final_srt,
        output,
        processing_dir=project.processing_dir,
        info=timeline_info,
        normalize_audio=True,
        template_id=template_id,
    )
    return final_srt, cuts


def _prepare_music(project, defaults: dict[str, object], *, mode: str, duration: float) -> tuple[Path | None, dict[str, object] | None, str | None]:
    if getattr(project, "settings", {}).get("background_music") is False:
        return None, None, "background music is disabled for this project"
    music_defaults = defaults.get("music", {})
    if not isinstance(music_defaults, dict) or music_defaults.get("enabled") is False:
        return None, None, "background music is disabled"
    catalog_name = str(music_defaults.get("catalog_path", "system/config/music_catalog.json"))
    catalog_path = (project.root / catalog_name).resolve()
    try:
        tracks = load_catalog(catalog_path)
        project_text = project.project_id
        if project.script_path:
            project_text += " " + project.script_path.read_text(encoding="utf-8-sig")
        track = select_track(
            tracks,
            project_text=project_text,
            mode=mode,
            duration=duration,
        )
        music_dir = project.input_dir / "music"
        downloaded = download_track(track, music_dir)
        record = build_license_record(track, downloaded)
        (music_dir / "music-license.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return downloaded, record, None
    except (ProjectError, OSError, UnicodeError) as exc:
        return None, None, str(exc)


def _apply_music(output: Path, project, *, mode: str, music: Path | None) -> tuple[Path | None, str | None]:
    if music is None:
        return None, "no approved track was selected"
    try:
        info = probe_media(output, still_duration=1.0)
        mixed = project.processing_dir / f"{output.stem}-with-music.mp4"
        render_with_music(
            output,
            music,
            mixed,
            info=info,
            duck_voice=mode == "tutorial",
        )
        mixed.replace(output)
        return music, None
    except (ProjectError, OSError) as exc:
        return None, f"music mix failed: {exc}"


def _silent_footage(
    project,
    infos,
    defaults: dict[str, object],
    output: Path,
    subtitle_file: str | None = None,
) -> tuple[Path | None, list[tuple[float, float]]]:
    source, combined_info = concatenate_sources(list(zip(project.videos, infos)), project.processing_dir)
    final_srt: Path | None = None
    subtitle_defaults = defaults.get("subtitles", {})
    assert isinstance(subtitle_defaults, dict)
    template_id = str(
        getattr(project, "settings", {}).get(
            "subtitle_template", subtitle_defaults.get("default_template", "S01")
        )
    )
    get_template(template_id)
    max_chars = caption_limit(width=combined_info.width, height=combined_info.height)
    max_lines = int(subtitle_defaults.get("max_lines", 2))
    sidecar = _choose_sidecar(project, subtitle_file)
    if sidecar:
        final_srt = output.with_suffix(".srt")
        final_srt.parent.mkdir(parents=True, exist_ok=True)
        cues = resegment_cues(
            parse_srt(sidecar.read_text(encoding="utf-8-sig")),
            max_chars_per_line=max_chars,
            max_lines=max_lines,
        )
        final_srt.write_text(
            build_srt(cues, duration=combined_info.duration), encoding="utf-8"
        )
    elif project.script_path:
        blocks = segment_caption_text(
            project.script_path.read_text(encoding="utf-8-sig"),
            max_chars_per_line=max_chars,
            max_lines=max_lines,
        )
        if blocks:
            final_srt = output.with_suffix(".srt")
            final_srt.parent.mkdir(parents=True, exist_ok=True)
            final_srt.write_text(build_srt(blocks, duration=combined_info.duration), encoding="utf-8")
    if final_srt:
        render_with_subtitles(
            source,
            final_srt,
            output,
            processing_dir=project.processing_dir,
            info=combined_info,
            normalize_audio=False,
            template_id=template_id,
        )
    else:
        render_plain(source, output, has_audio=combined_info.has_audio)
    return final_srt, []


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SHINE macOS video workflow: 1_input -> 2_processing -> 3_output"
    )
    parser.add_argument("project_id")
    parser.add_argument("--mode", choices=["auto", "tutorial", "silent-footage"], default="auto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--version", type=int, help="write <project>_vN.mp4 without overwriting existing output")
    parser.add_argument("--subtitle-file", help="select a specific input SRT when multiple drafts exist")
    parser.add_argument("--root", type=Path, default=_repo_root(), help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        root = args.root.resolve()
        project = discover_project(root, args.project_id)
        defaults = _load_defaults(root)
        silent_defaults = defaults["silent_footage"]
        assert isinstance(silent_defaults, dict)
        still_duration = float(silent_defaults["still_image_seconds"])
        sources = order_project_sources(project.videos, project.settings)
        infos = [probe_media(path, still_duration=still_duration) for path in sources]
        configured_mode = project.settings.get("mode", "auto")
        requested_mode = args.mode if args.mode != "auto" else str(configured_mode)
        mode = select_mode(
            requested_mode,
            has_subtitles=bool(project.subtitle_paths),
            has_script=project.script_path is not None,
            has_audio=any(info.has_audio for info in infos),
        )
        plan = {
            "schema": "shine.video.plan.v1",
            "projectId": project.project_id,
            "mode": mode,
            "aspectRatio": "original",
            "audioMode": "original-audio" if mode == "tutorial" else "source-or-silence",
            "aiNarration": False,
            "backgroundMusic": {"status": "pending"},
            "videos": [
                {
                    "name": path.name,
                    "duration": info.duration,
                    "width": info.width,
                    "height": info.height,
                    "hasAudio": info.has_audio,
                    "kind": "photo" if info.is_still else "video",
                }
                for path, info in zip(sources, infos)
            ],
        }
        write_json(project.processing_dir / "plan.json", plan)
        print(f"[PLAN] {project.project_id}: {mode}, aspect ratio original")
        if args.dry_run:
            print(f"[OK] Dry run / 試跑完成: {project.processing_dir / 'plan.json'}")
            return 0

        project = replace(project, videos=sources)
        output = (
            versioned_output_path(project.output_dir, project.project_id, args.version)
            if args.version is not None
            else next_output_path(project.output_dir, project.project_id)
        )
        if mode == "tutorial":
            subtitle, cuts = _tutorial(project, infos[0], defaults, output, args.subtitle_file)
        else:
            subtitle, cuts = _silent_footage(project, infos, defaults, output, args.subtitle_file)
        music, music_record, music_reason = _prepare_music(
            project,
            defaults,
            mode=mode,
            duration=probe_media(output, still_duration=1.0).duration,
        )
        applied_music, apply_reason = _apply_music(output, project, mode=mode, music=music)
        if apply_reason:
            music_reason = apply_reason if music_reason is None else f"{music_reason}; {apply_reason}"
        plan["backgroundMusic"] = (
            {
                "status": "applied" if applied_music else "skipped",
                "file": str(applied_music.relative_to(project.root)) if applied_music else None,
                "license": music_record,
                "reason": music_reason,
            }
        )
        report_path = output.with_name(f"{output.stem}_report.md")
        _report(
            report_path,
            mode=mode,
            output=output,
            subtitle=subtitle,
            cuts=cuts,
            music=applied_music,
            music_reason=music_reason,
        )
        review_path = review_path_for_output(output)
        write_review_html(
            review_path,
            project_id=project.project_id,
            output_name=output.name,
            sources=list(zip(project.videos, infos)),
        )
        plan["output"] = str(output.relative_to(root))
        plan["review"] = str(review_path.relative_to(root))
        plan["status"] = "complete"
        write_json(project.processing_dir / "plan.json", plan)
        print(f"[OK] Output / 輸出: {output}")
        return 0
    except ProjectError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
