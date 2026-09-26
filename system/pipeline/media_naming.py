"""Standardized media renaming engine for photos and videos (YYYYMMDD_subject_001 format)."""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Iterable, Sequence

# Known folder and topic translations to clean English snake_case slugs
FOLDER_SUBJECT_MAP = {
    "0831秘境咖啡廳": "secret_cafe",
    "0901萬丹森林": "wandan_forest",
    "壽山遊客中心": "shoushan_visitor_center",
    "0903佛光山": "foguangshan",
    "0829草間彌生特展": "yayoi_kusama_exhibition",
    "5月台南奇美": "tainan_chimei",
    "新竹一日遊": "hsinchu_day_trip",
    "佛光山麥積山": "maijishan",
    "萬丹": "wandan",
    "萬丹鄉河堤北路": "wandan_riverbank",
    "英文學習方法": "english_learning",
    "複製貼上進階工具": "clipboard_tools",
    "0901mochaTODOCTOR": "mocha_to_doctor",
    "晩餐歌": "dinner_song",
    "Timeline 1": "timeline_one",
    "20250305_classroom_lecture_001": "classroom_lecture",
    "roast_pig_to_crocodile": "roast_pig_to_crocodile",
    "永大丟魚網": "fish_net_casting",
    "萬德服良食": "good_food",
    "烤乳豬轉鱷魚肉": "roast_pig_to_crocodile",
    "0912": "desktop_tutorial",
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".dng", ".webp", ".tiff"}
SUPPORTED_MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | PHOTO_EXTENSIONS


def slugify_subject(text: str) -> str:
    """Normalize a subject or project name into a clean lowercase snake_case identifier."""
    if not text:
        return "clip"
    clean = text.strip()
    # Check known translation map first
    if clean in FOLDER_SUBJECT_MAP:
        return FOLDER_SUBJECT_MAP[clean]
    # Remove leading dates (e.g. 20250305_, 0901_)
    clean = re.sub(r"^\d{4,8}[_-]?", "", clean)
    clean = re.sub(r"^\d{1,2}月", "", clean)
    clean = clean.strip(" _-")
    if clean in FOLDER_SUBJECT_MAP:
        return FOLDER_SUBJECT_MAP[clean]

    # Convert known Chinese words or phrases if present
    for k, v in FOLDER_SUBJECT_MAP.items():
        if k in text:
            return v

    # Convert Latin characters to snake_case
    s = unicodedata.normalize("NFKD", clean)
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s-]+", "_", s).strip("_").lower()
    # If string is entirely non-ascii or empty after strip, produce a fallback identifier
    if not s or not re.search(r"[a-z0-9]", s):
        # Hex hash / numeric fallback
        encoded = clean.encode("utf-8").hex()[:10]
        return f"media_{encoded}"
    return s[:40]


def parse_iso_datetime(date_str: str) -> datetime.datetime | None:
    """Attempt to parse ISO 8601 or common timestamp formats."""
    if not date_str or not isinstance(date_str, str):
        return None
    cleaned = date_str.strip()
    # Handle YYYY:MM:DD HH:MM:SS (EXIF format)
    exif_match = re.match(r"^(\d{4}):(\d{2}):(\d{2})\s+(\d{2}):(\d{2}):(\d{2})", cleaned)
    if exif_match:
        try:
            return datetime.datetime(
                int(exif_match.group(1)), int(exif_match.group(2)), int(exif_match.group(3)),
                int(exif_match.group(4)), int(exif_match.group(5)), int(exif_match.group(6))
            )
        except ValueError:
            pass
    # ISO formats like 2026-09-12T01:22:15.000000Z or 2026-09-12 01:22:15 +0000
    cleaned = re.sub(r"\.\d+", "", cleaned)  # strip microseconds
    cleaned = re.sub(r"Z$", "+00:00", cleaned)
    cleaned = re.sub(r"\s+\+\d{4}$", "", cleaned)
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y%m%d_%H%M%S",
        "%Y%m%d%H%M%S",
    ):
        try:
            dt = datetime.datetime.strptime(cleaned, fmt)
            if dt.tzinfo is not None:
                dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return dt
        except ValueError:
            continue
    return None


def extract_media_datetime(path: Path) -> tuple[datetime.datetime, str]:
    """Extract capture or creation datetime from media tags, EXIF, or filesystem."""
    path = Path(path)
    suffix = path.suffix.lower()

    # 1. QuickTime / MP4 video tags via ffprobe
    if suffix in VIDEO_EXTENSIONS:
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            try:
                proc = subprocess.run(
                    [
                        ffprobe, "-v", "error",
                        "-show_entries", "format_tags:stream_tags",
                        "-of", "json", str(path),
                    ],
                    capture_output=True, text=True, check=False, timeout=10,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    data = json.loads(proc.stdout)
                    tags = data.get("format", {}).get("tags", {})
                    for stream in data.get("streams", []):
                        tags.update(stream.get("tags", {}))
                    for tag_key in (
                        "creation_time",
                        "com.apple.quicktime.creationdate",
                        "date",
                        "DateTimeOriginal",
                    ):
                        val = tags.get(tag_key)
                        if val:
                            parsed = parse_iso_datetime(str(val))
                            if parsed and 2000 <= parsed.year <= 2099:
                                return parsed, f"ffprobe_{tag_key}"
            except Exception:
                pass

    # 2. Photos via sips on macOS
    if suffix in PHOTO_EXTENSIONS:
        sips = shutil.which("sips")
        if sips:
            try:
                proc = subprocess.run(
                    [sips, "-g", "creation", str(path)],
                    capture_output=True, text=True, check=False, timeout=5,
                )
                if proc.returncode == 0 and proc.stdout:
                    for line in proc.stdout.splitlines():
                        if "creation:" in line:
                            val = line.split("creation:", 1)[1].strip()
                            parsed = parse_iso_datetime(val)
                            if parsed and 2000 <= parsed.year <= 2099:
                                return parsed, "sips_creation"
            except Exception:
                pass

    # 3. Infer date from parent folder or filename pattern (e.g. 20191203, 20250305, 0831)
    combined = f"{path.parent.name}_{path.stem}"
    date_match = re.search(r"(?<!\d)(20\d{2})([01]\d)([0-3]\d)(?!\d)", combined)
    if date_match:
        try:
            parsed = datetime.datetime(
                int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)),
                12, 0, 0
            )
            return parsed, "path_pattern_yyyymmdd"
        except ValueError:
            pass

    # 4. macOS mdls metadata command
    mdls = shutil.which("mdls")
    if mdls:
        try:
            proc = subprocess.run(
                [mdls, "-name", "kMDItemContentCreationDate", str(path)],
                capture_output=True, text=True, check=False, timeout=5,
            )
            if proc.returncode == 0 and proc.stdout and "=" in proc.stdout:
                val = proc.stdout.split("=", 1)[1].strip()
                if val and val != "(null)":
                    parsed = parse_iso_datetime(val)
                    if parsed and 2000 <= parsed.year <= 2099:
                        return parsed, "mdls_creation"
        except Exception:
            pass

    # 5. File birthtime / mtime from filesystem
    try:
        st = path.stat()
        birth = getattr(st, "st_birthtime", None)
        timestamp = birth if birth and birth > 0 else st.st_mtime
        if timestamp and timestamp > 0:
            dt = datetime.datetime.fromtimestamp(timestamp)
            if 2000 <= dt.year <= 2099:
                return dt, "filesystem_timestamp"
    except Exception:
        pass

    # 6. Fallback to today
    return datetime.datetime.now(), "current_fallback"


def format_media_date(dt: datetime.datetime) -> str:
    """Format datetime as YYYYMMDD string."""
    return dt.strftime("%Y%m%d")


def generate_standard_name(
    path: Path,
    *,
    subject: str,
    index: int,
    date_str: str | None = None,
) -> str:
    """Generate a single standardized media filename: YYYYMMDD_subject_001.ext."""
    path = Path(path)
    if not date_str:
        dt, _ = extract_media_datetime(path)
        date_str = format_media_date(dt)
    slug = slugify_subject(subject)
    ext = path.suffix.lower()
    return f"{date_str}_{slug}_{index:03d}{ext}"


def generate_media_names(
    paths: Sequence[Path],
    *,
    subject: str | None = None,
    existing_names: Iterable[str] = (),
    start_index: int = 1,
) -> list[dict]:
    """
    Chronologically sort media paths and generate standardized names.
    Collision avoidance ensures new indexes don't conflict with existing_names.
    """
    existing_set = set(existing_names)
    items = []

    # First collect datetimes for all files
    for p in paths:
        path = Path(p)
        dt, source = extract_media_datetime(path)
        date_str = format_media_date(dt)
        items.append({
            "path": path,
            "datetime": dt,
            "date_str": date_str,
            "source": source,
        })

    # Sort chronologically by (datetime, path.name)
    items.sort(key=lambda x: (x["datetime"], x["path"].name.casefold()))

    # Determine subject slug
    default_subject = subject or (items[0]["path"].parent.name if items else "media")
    slug = slugify_subject(default_subject)

    # Track used indices per date_str to avoid collisions
    results = []
    index_counters: dict[str, int] = {}

    for item in items:
        date_str = item["date_str"]
        ext = item["path"].suffix.lower()
        if date_str not in index_counters:
            # Find the highest existing index for this date and slug in existing_names
            highest = 0
            prefix = f"{date_str}_{slug}_"
            for name in existing_set:
                if name.startswith(prefix):
                    match = re.search(rf"^{re.escape(prefix)}(\d{{3}})", name)
                    if match:
                        highest = max(highest, int(match.group(1)))
            index_counters[date_str] = max(highest, start_index - 1)

        index_counters[date_str] += 1
        curr_idx = index_counters[date_str]
        new_name = f"{date_str}_{slug}_{curr_idx:03d}{ext}"
        while new_name in existing_set:
            index_counters[date_str] += 1
            curr_idx = index_counters[date_str]
            new_name = f"{date_str}_{slug}_{curr_idx:03d}{ext}"

        existing_set.add(new_name)
        results.append({
            "original_path": item["path"],
            "original_name": item["path"].name,
            "new_name": new_name,
            "date": date_str,
            "subject": slug,
            "index": curr_idx,
            "timestamp": item["datetime"].isoformat(),
            "date_source": item["source"],
        })

    return results
