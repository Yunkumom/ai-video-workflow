from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .models import ProjectError, SubtitleCue


CATALOG_SCHEMA = "shine.subtitle.catalog.v1"
VALID_STATUSES = {"mature", "testing"}
VALID_BACKGROUNDS = {"fitted-line", "transparent"}
VALID_WEIGHTS = {"regular", "bold", "heavy"}
VALID_MOTIONS = {"none", "impact", "keyword-punch", "split-reveal"}
_STYLE_ID = re.compile(r"S\d{2}")
_CLAUSE_BOUNDARY = re.compile(r".+?(?:[。！？!?；;，,]|$)", re.DOTALL)
_PROTECTED_TOKEN = re.compile(
    r"[A-Za-z][A-Za-z0-9._/+:-]*"
    r"|\d+(?:[.,×xX:/-]\d+)*(?:[%％℃°年月日時分秒個支張台公尺分]*)"
    r"|.",
    re.DOTALL,
)


@dataclass(frozen=True)
class SubtitleTemplate:
    id: str
    name_zh_tw: str
    slug: str
    version: int
    status: str
    background: str
    outline: bool
    weight: str
    accent: str | None
    motion: str


@dataclass(frozen=True)
class CaptionRenderOptions:
    show_background: bool
    fit_background: bool
    outline: bool
    heavy_text: bool


def _catalog_path() -> Path:
    return Path(__file__).resolve().parents[2] / "templates" / "catalog.json"


def _exact_keys(payload: dict[str, object], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ProjectError(f"{label} fields are invalid")


def validate_catalog(payload: object) -> tuple[SubtitleTemplate, ...]:
    if not isinstance(payload, dict):
        raise ProjectError("subtitle catalog must be an object")
    _exact_keys(payload, {"schema", "styles"}, "subtitle catalog")
    if payload.get("schema") != CATALOG_SCHEMA:
        raise ProjectError("unsupported subtitle catalog schema")
    rows = payload.get("styles")
    if not isinstance(rows, list) or not rows:
        raise ProjectError("subtitle catalog needs styles")

    styles: list[SubtitleTemplate] = []
    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ProjectError("subtitle style must be an object")
        _exact_keys(
            row,
            {
                "id",
                "name_zh_tw",
                "slug",
                "version",
                "status",
                "appearance",
                "motion",
            },
            "subtitle style",
        )
        appearance = row.get("appearance")
        if not isinstance(appearance, dict):
            raise ProjectError("subtitle appearance must be an object")
        _exact_keys(
            appearance,
            {"background", "outline", "weight", "accent"},
            "subtitle appearance",
        )

        style_id = row.get("id")
        name = row.get("name_zh_tw")
        slug = row.get("slug")
        version = row.get("version")
        status = row.get("status")
        background = appearance.get("background")
        outline = appearance.get("outline")
        weight = appearance.get("weight")
        accent = appearance.get("accent")
        motion = row.get("motion")
        if not isinstance(style_id, str) or not _STYLE_ID.fullmatch(style_id):
            raise ProjectError("invalid subtitle style ID")
        if style_id in seen_ids:
            raise ProjectError("duplicate subtitle style ID")
        if not isinstance(name, str) or not name.strip():
            raise ProjectError("subtitle style name is required")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ProjectError("invalid subtitle style slug")
        if slug in seen_slugs:
            raise ProjectError("duplicate subtitle style slug")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ProjectError("subtitle style version must be positive")
        if status not in VALID_STATUSES:
            raise ProjectError("invalid subtitle style status")
        if background not in VALID_BACKGROUNDS:
            raise ProjectError("invalid subtitle background")
        if not isinstance(outline, bool):
            raise ProjectError("subtitle outline must be boolean")
        if weight not in VALID_WEIGHTS:
            raise ProjectError("invalid subtitle weight")
        if accent is not None and (
            not isinstance(accent, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent)
        ):
            raise ProjectError("invalid subtitle accent")
        if motion not in VALID_MOTIONS:
            raise ProjectError("invalid subtitle motion")

        styles.append(
            SubtitleTemplate(
                id=style_id,
                name_zh_tw=name.strip(),
                slug=slug,
                version=version,
                status=status,
                background=background,
                outline=outline,
                weight=weight,
                accent=accent,
                motion=motion,
            )
        )
        seen_ids.add(style_id)
        seen_slugs.add(slug)
    return tuple(styles)


def load_catalog(path: Path | None = None) -> tuple[SubtitleTemplate, ...]:
    catalog_path = path or _catalog_path()
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectError(f"invalid subtitle catalog: {exc}") from exc
    return validate_catalog(payload)


def get_template(template_id: str, path: Path | None = None) -> SubtitleTemplate:
    for template in load_catalog(path):
        if template.id == template_id:
            return template
    raise ProjectError(f"unknown subtitle template: {template_id}")


def caption_render_options(
    template_id: str, path: Path | None = None
) -> CaptionRenderOptions:
    template = get_template(template_id, path)
    return CaptionRenderOptions(
        show_background=template.background == "fitted-line",
        fit_background=template.background == "fitted-line",
        outline=template.outline,
        heavy_text=template.weight == "heavy",
    )


def caption_limit(*, width: int, height: int) -> int:
    if width <= 0 or height <= 0:
        raise ValueError("caption dimensions must be positive")
    return 10 if height >= width else 16


def _wrap_clause(clause: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for match in _PROTECTED_TOKEN.finditer(clause):
        token = match.group(0)
        if current and len(current) + len(token) > max_chars:
            lines.append(current)
            current = ""
        if not current and len(token) > max_chars:
            lines.append(token)
        else:
            current += token
    if current:
        lines.append(current)
    return lines


def segment_caption_text(
    text: str,
    *,
    max_chars_per_line: int,
    max_lines: int = 2,
) -> list[str]:
    if max_chars_per_line < 1 or max_lines < 1:
        raise ValueError("caption limits must be positive")
    normalized = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", "")
    if not normalized:
        return []

    clauses = [match.group(0) for match in _CLAUSE_BOUNDARY.finditer(normalized)]
    lines: list[str] = []
    current = ""
    for clause in clauses:
        if len(clause) <= max_chars_per_line:
            if current and len(current) + len(clause) > max_chars_per_line:
                lines.append(current)
                current = clause
            else:
                current += clause
            continue
        if current:
            lines.append(current)
            current = ""
        lines.extend(_wrap_clause(clause, max_chars_per_line))
    if current:
        lines.append(current)

    return [
        "\n".join(lines[index : index + max_lines])
        for index in range(0, len(lines), max_lines)
    ]


def resegment_cues(
    cues: Sequence[SubtitleCue],
    *,
    max_chars_per_line: int,
    max_lines: int = 2,
) -> list[SubtitleCue]:
    result: list[SubtitleCue] = []
    for cue in cues:
        if cue.end <= cue.start:
            raise ValueError("subtitle cue end must be after start")
        blocks = segment_caption_text(
            cue.text,
            max_chars_per_line=max_chars_per_line,
            max_lines=max_lines,
        )
        if not blocks:
            continue
        weights = [max(1, len(block.replace("\n", ""))) for block in blocks]
        total = sum(weights)
        elapsed = 0
        for index, (block, weight) in enumerate(zip(blocks, weights)):
            start = cue.start + (cue.end - cue.start) * elapsed / total
            elapsed += weight
            end = (
                cue.end
                if index == len(blocks) - 1
                else cue.start + (cue.end - cue.start) * elapsed / total
            )
            result.append(SubtitleCue(start, end, block))
    return result
