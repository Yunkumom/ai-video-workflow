"""Batch in-place renaming tool with dry-run preview manifest and rollback support."""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
from pathlib import Path
from typing import Sequence

from .media_naming import (
    SUPPORTED_MEDIA_EXTENSIONS,
    VIDEO_EXTENSIONS,
    PHOTO_EXTENSIONS,
    extract_media_datetime,
    format_media_date,
    generate_media_names,
    slugify_subject,
)

MANIFEST_SCHEMA = "shine.media-rename-manifest.v1"
ALREADY_STANDARDIZED_RE = re.compile(r"^\d{8}_[a-z0-9_]+_\d{3}\.[a-zA-Z0-9]+$")


def build_rename_manifest(
    folder_path: Path,
    *,
    subject: str | None = None,
    include_sidecars: bool = True,
) -> dict:
    """Generate a dry-run preview manifest for files in a folder without altering disk files."""
    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        raise ValueError(f"目標資料夾不存在：{folder}")

    # Gather media files
    candidates = []
    existing_standard_names = set()

    for p in sorted(folder.iterdir(), key=lambda x: x.name.casefold()):
        if not p.is_file() or p.name.startswith("."):
            continue
        ext = p.suffix.lower()
        if ext in SUPPORTED_MEDIA_EXTENSIONS:
            if ALREADY_STANDARDIZED_RE.match(p.name):
                existing_standard_names.add(p.name)
            else:
                candidates.append(p)

    subject_slug = slugify_subject(subject or folder.name)

    named_items = generate_media_names(
        candidates,
        subject=subject_slug,
        existing_names=existing_standard_names,
    )

    manifest_items = []
    for item in named_items:
        orig = item["original_path"]
        new_name = item["new_name"]
        new_path = folder / new_name

        # Find matching sidecars (e.g. .srt, .vtt, .json, .txt with same stem)
        sidecars = []
        if include_sidecars:
            stem = orig.stem
            for f in folder.iterdir():
                if f.is_file() and f.name.startswith(stem) and f.suffix.lower() in {".srt", ".vtt", ".json", ".txt"}:
                    # e.g. IMG_0001.srt -> 20191203_campus_entrance_001.srt
                    # or IMG_0001_zh.srt -> 20191203_campus_entrance_001_zh.srt
                    extra_suffix = f.name[len(stem):]
                    new_sidecar_name = Path(new_name).stem + extra_suffix
                    sidecars.append({
                        "original_path": str(f),
                        "original_name": f.name,
                        "new_name": new_sidecar_name,
                        "new_path": str(folder / new_sidecar_name),
                    })

        manifest_items.append({
            "original_path": str(orig),
            "original_name": item["original_name"],
            "new_name": new_name,
            "new_path": str(new_path),
            "date": item["date"],
            "subject": item["subject"],
            "index": item["index"],
            "timestamp": item["timestamp"],
            "date_source": item["date_source"],
            "sidecars": sidecars,
        })

    return {
        "schema": MANIFEST_SCHEMA,
        "folder": str(folder),
        "subject": subject_slug,
        "created_at": datetime.datetime.now().isoformat(),
        "total_media_count": len(manifest_items),
        "items": manifest_items,
    }


def execute_rename_manifest(manifest: dict, *, history_file: Path | None = None) -> dict:
    """Execute the renames recorded in the manifest. Writes a rollback history file."""
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("清單格式不符。")

    items = manifest.get("items", [])
    if not items:
        return {"status": "no_changes", "renamed_count": 0}

    folder = Path(manifest["folder"])
    # 1. Pre-flight check: ensure all source files exist and no destination conflicts
    for item in items:
        p_orig = Path(item["original_path"])
        p_new = Path(item["new_path"])
        if not p_orig.is_file():
            raise FileNotFoundError(f"原始檔案已不存在：{p_orig}")
        if p_new.exists() and p_new != p_orig:
            raise FileExistsError(f"目標檔案已存在，防止覆蓋：{p_new}")
        for sc in item.get("sidecars", []):
            sc_orig = Path(sc["original_path"])
            sc_new = Path(sc["new_path"])
            if not sc_orig.is_file():
                raise FileNotFoundError(f"原始附檔已不存在：{sc_orig}")
            if sc_new.exists() and sc_new != sc_orig:
                raise FileExistsError(f"目標附檔已存在：{sc_new}")

    # 2. Perform renames
    renamed = []
    try:
        for item in items:
            p_orig = Path(item["original_path"])
            p_new = Path(item["new_path"])
            os.rename(p_orig, p_new)
            renamed.append({"from": str(p_orig), "to": str(p_new)})

            for sc in item.get("sidecars", []):
                sc_orig = Path(sc["original_path"])
                sc_new = Path(sc["new_path"])
                os.rename(sc_orig, sc_new)
                renamed.append({"from": str(sc_orig), "to": str(sc_new)})
    except Exception as e:
        # Revert what was renamed so far
        for step in reversed(renamed):
            try:
                os.rename(step["to"], step["from"])
            except Exception:
                pass
        raise RuntimeError(f"更名中斷，已嘗試自動還原：{e}") from e

    # 3. Save rollback record
    history_record = {
        "schema": "shine.media-rename-rollback.v1",
        "folder": str(folder),
        "executed_at": datetime.datetime.now().isoformat(),
        "renamed_operations": renamed,
    }
    if not history_file:
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        history_file = folder / f".rename_rollback_{timestamp_str}.json"
    history_file.write_text(json.dumps(history_record, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "status": "success",
        "renamed_count": len(renamed),
        "rollback_file": str(history_file),
    }


def rollback_renames(history_file: Path) -> dict:
    """Roll back previous renames using a rollback history file."""
    history = json.loads(Path(history_file).read_text(encoding="utf-8"))
    if history.get("schema") != "shine.media-rename-rollback.v1":
        raise ValueError("還原紀錄格式不正確。")

    operations = history.get("renamed_operations", [])
    reverted = []
    for step in reversed(operations):
        curr_path = Path(step["to"])
        orig_path = Path(step["from"])
        if curr_path.exists():
            os.rename(curr_path, orig_path)
            reverted.append({"from": str(curr_path), "to": str(orig_path)})

    return {
        "status": "rolled_back",
        "reverted_count": len(reverted),
    }


def main():
    parser = argparse.ArgumentParser(description="Media Batch Renamer with Dry-run & Rollback")
    parser.add_argument("--preview", type=str, help="Folder path to generate dry-run preview manifest")
    parser.add_argument("--subject", type=str, default=None, help="Optional subject slug override")
    parser.add_argument("--apply", type=str, help="Manifest JSON file to apply")
    parser.add_argument("--rollback", type=str, help="Rollback history JSON file to revert")
    args = parser.parse_args()

    if args.preview:
        manifest = build_rename_manifest(Path(args.preview), subject=args.subject)
        out_file = Path(args.preview) / ".rename_manifest.json"
        out_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"預覽清單已生成：{out_file} (共 {manifest['total_media_count']} 項)")
        for it in manifest["items"]:
            print(f"  {it['original_name']} -> {it['new_name']} ({it['date_source']})")
    elif args.apply:
        manifest = json.loads(Path(args.apply).read_text(encoding="utf-8"))
        res = execute_rename_manifest(manifest)
        print(f"更名完成：{res}")
    elif args.rollback:
        res = rollback_renames(Path(args.rollback))
        print(f"已還原：{res}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
