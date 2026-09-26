"""Validated, versioned subtitle-review documents with safe text style runs."""
from __future__ import annotations

import copy
import json
import math
import re
from typing import Any, Collection

from .models import ProjectError

SCHEMA_V1 = "shine.project-subtitle-review.v1"
SCHEMA_V2 = "shine.project-subtitle-review.v2"
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ROOT_FIELDS = {"schema", "revision", "source", "duration", "style", "cues"}
_STYLE_FIELDS = {"fontFamily", "sizePct", "weight", "color", "strokePct", "strokeColor", "bottomPct"}
_CUE_FIELDS = {"id", "start", "end", "text", "runs", "note", "original"}
_RUN_FIELDS = {"text", "style"}
_RUN_STYLE_FIELDS = {"fontFamily", "sizeScale", "color"}


def _number(value: object, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ProjectError(f"{label}必須是有限數值。")
    result = float(value)
    if not low <= result <= high:
        raise ProjectError(f"{label}超出允許範圍。")
    return result


def _font(value: object, available_fonts: Collection[str] | None) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ProjectError("字幕字體無效。")
    if available_fonts is not None and value not in available_fonts:
        raise ProjectError(f"字幕字體無法使用：{value}")
    return value


def _color(value: object) -> str:
    if not isinstance(value, str) or not _COLOR.fullmatch(value):
        raise ProjectError("字幕顏色必須使用 #RRGGBB。")
    return value.upper()


def migrate_review_document(document: object) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ProjectError("字幕工作檔必須是物件。")
    if document.get("schema") == SCHEMA_V2:
        return copy.deepcopy(document)
    if document.get("schema") != SCHEMA_V1 or set(document) != _ROOT_FIELDS:
        raise ProjectError("字幕工作檔版本或欄位無效。")
    old_style = document.get("style")
    if not isinstance(old_style, dict) or not {"font", "size", "weight", "stroke"}.issubset(old_style):
        raise ProjectError("舊版字幕樣式無效。")
    cues = []
    for cue in document.get("cues", []):
        if not isinstance(cue, dict) or not isinstance(cue.get("text"), str):
            raise ProjectError("舊版字幕內容無效。")
        migrated = {key: copy.deepcopy(value) for key, value in cue.items() if key in _CUE_FIELDS - {"runs"}}
        migrated["runs"] = [{"text": cue["text"], "style": {}}]
        cues.append(migrated)
    return {
        "schema": SCHEMA_V2,
        "revision": 2,
        "source": document.get("source"),
        "duration": float(document.get("duration")),
        "style": {
            "fontFamily": old_style["font"],
            "sizePct": float(old_style["size"]),
            "weight": int(old_style["weight"]),
            "color": "#FFFFFF",
            "strokePct": float(old_style["stroke"]),
            "strokeColor": "#000000",
            "bottomPct": 8.0,
        },
        "cues": cues,
    }


def validate_review_document(
    document: object, *, available_fonts: Collection[str] | None = None
) -> dict[str, Any]:
    document = migrate_review_document(document)
    try:
        encoded = json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProjectError("字幕工作檔包含無效數值。") from exc
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise ProjectError("字幕工作檔超過 8 MB。")
    if set(document) != _ROOT_FIELDS or document.get("schema") != SCHEMA_V2:
        raise ProjectError("字幕工作檔欄位無效。")
    if isinstance(document.get("revision"), bool) or not isinstance(document.get("revision"), int) or document["revision"] < 2:
        raise ProjectError("字幕工作檔修訂版號無效。")
    if not isinstance(document.get("source"), str) or not document["source"] or len(document["source"]) > 255:
        raise ProjectError("影片來源名稱無效。")
    duration = _number(document.get("duration"), "影片長度", 0.001, 86400.0)
    style = document.get("style")
    if not isinstance(style, dict) or set(style) != _STYLE_FIELDS:
        raise ProjectError("字幕預設樣式欄位無效。")
    _font(style["fontFamily"], available_fonts)
    _number(style["sizePct"], "字幕大小", 2.0, 20.0)
    _number(style["weight"], "字幕粗細", 100, 1000)
    _color(style["color"])
    _number(style["strokePct"], "字幕描邊", 0.0, 0.3)
    _color(style["strokeColor"])
    _number(style["bottomPct"], "字幕底部位置", 0.0, 40.0)
    cues = document.get("cues")
    if not isinstance(cues, list) or not cues:
        raise ProjectError("字幕工作檔沒有字幕。")
    previous_end = 0.0
    seen_ids: set[object] = set()
    for cue in cues:
        if not isinstance(cue, dict) or not set(cue).issubset(_CUE_FIELDS) or not {"id", "start", "end", "text", "runs"}.issubset(cue):
            raise ProjectError("字幕欄位無效。")
        if isinstance(cue["id"], bool) or not isinstance(cue["id"], (int, str)) or cue["id"] in seen_ids:
            raise ProjectError("字幕識別碼無效或重複。")
        seen_ids.add(cue["id"])
        start = _number(cue["start"], "字幕開始時間", 0.0, duration)
        end = _number(cue["end"], "字幕結束時間", 0.0, duration)
        if start < previous_end or end <= start:
            raise ProjectError("字幕時間重疊或順序無效。")
        previous_end = end
        if not isinstance(cue["text"], str) or not cue["text"].strip() or len(cue["text"]) > 2000:
            raise ProjectError("字幕文字無效。")
        runs = cue["runs"]
        if not isinstance(runs, list) or not runs:
            raise ProjectError("字幕文字格式不存在。")
        run_text = ""
        for run in runs:
            if not isinstance(run, dict) or set(run) != _RUN_FIELDS or not isinstance(run["text"], str) or not run["text"]:
                raise ProjectError("字幕文字格式區段無效。")
            run_style = run["style"]
            if not isinstance(run_style, dict) or not set(run_style).issubset(_RUN_STYLE_FIELDS):
                raise ProjectError("字幕局部樣式欄位無效。")
            if "fontFamily" in run_style:
                _font(run_style["fontFamily"], available_fonts)
            if "sizeScale" in run_style:
                _number(run_style["sizeScale"], "局部字幕大小", 0.5, 3.0)
            if "color" in run_style:
                _color(run_style["color"])
            run_text += run["text"]
        if run_text != cue["text"]:
            raise ProjectError("字幕文字與局部樣式內容不一致。")
        for optional in ("note", "original"):
            if optional in cue and (not isinstance(cue[optional], str) or len(cue[optional]) > 4000):
                raise ProjectError("字幕註解或原始辨識內容無效。")
    return document
