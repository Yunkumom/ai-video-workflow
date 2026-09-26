from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import ProjectError


REQUIRED_FIELDS = {
    "id",
    "title",
    "provider",
    "source_url",
    "mood",
    "pace",
    "duration",
    "instrumental",
    "commercial_use",
    "attribution_required",
    "license_url",
    "license_evidence",
}


def load_catalog(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectError(f"invalid music catalog: {exc}") from exc
    tracks = payload.get("tracks") if isinstance(payload, dict) else None
    if not isinstance(tracks, list):
        raise ProjectError("music catalog must contain a tracks list")
    validated: list[dict[str, Any]] = []
    for track in tracks:
        if not isinstance(track, dict) or not REQUIRED_FIELDS.issubset(track):
            raise ProjectError("music catalog track is missing required fields")
        if not isinstance(track["mood"], list) or not all(
            isinstance(item, str) for item in track["mood"]
        ):
            raise ProjectError("music catalog mood must be a list of strings")
        validated.append(dict(track))
    return validated


def _approved(track: Mapping[str, Any]) -> bool:
    return bool(
        track.get("commercial_use") is True
        and track.get("attribution_required") is False
        and str(track.get("license_url", "")).strip()
        and str(track.get("license_evidence", "")).strip()
    )


def select_track(
    tracks: Sequence[Mapping[str, Any]],
    *,
    project_text: str,
    mode: str,
    duration: float,
    used_ids: set[str] | None = None,
) -> dict[str, Any]:
    used = used_ids or set()
    tokens = {token.casefold() for token in project_text.split() if token.strip()}
    candidates = [dict(track) for track in tracks if _approved(track)]
    if not candidates:
        raise ProjectError("no approved music track is available")

    def score(track: Mapping[str, Any]) -> tuple[int, int, int, int, str]:
        moods = {str(item).casefold() for item in track.get("mood", [])}
        mood_score = len(tokens & moods)
        duration_score = 2 if float(track.get("duration", 0)) >= duration else 0
        instrumental_score = 2 if track.get("instrumental") is True else 0
        mode_score = 1 if mode == "silent-footage" or instrumental_score else 0
        repeat_penalty = -3 if str(track.get("id")) in used else 0
        return (mood_score + duration_score + instrumental_score + mode_score + repeat_penalty,
                mood_score,
                duration_score,
                instrumental_score,
                str(track.get("id", "")))

    return max(candidates, key=score)


def _safe_suffix(track: Mapping[str, Any]) -> str:
    local_path = str(track.get("local_path", ""))
    suffix = Path(local_path).suffix.lower()
    if suffix not in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}:
        suffix = ".mp3"
    return suffix


def download_track(track: Mapping[str, Any], destination: Path) -> Path:
    if not _approved(track):
        raise ProjectError("music track license is not approved")
    track_id = str(track.get("id", "")).strip()
    if not track_id or "/" in track_id or "\\" in track_id:
        raise ProjectError("music track id is unsafe")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"{track_id}{_safe_suffix(track)}"
    if target.exists():
        return target
    local_path = str(track.get("local_path", "")).strip()
    if local_path:
        source = Path(local_path)
        if not source.is_file():
            raise ProjectError(f"music source file does not exist: {source}")
        shutil.copy2(source, target)
        return target
    download_url = str(track.get("download_url", "")).strip()
    if not download_url.startswith(("https://", "http://")):
        raise ProjectError("music track has no approved local_path or download_url")
    try:
        with urllib.request.urlopen(download_url, timeout=20) as response, target.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except (OSError, ValueError) as exc:
        target.unlink(missing_ok=True)
        raise ProjectError(f"music download failed: {exc}") from exc
    if target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise ProjectError("music download returned an empty file")
    return target


def build_license_record(track: Mapping[str, Any], downloaded_path: Path) -> dict[str, Any]:
    digest = hashlib.sha256(downloaded_path.read_bytes()).hexdigest()
    return {
        "schema": "shine.video.music-license.v1",
        "trackId": str(track["id"]),
        "title": str(track["title"]),
        "provider": str(track["provider"]),
        "sourceUrl": str(track["source_url"]),
        "licenseUrl": str(track["license_url"]),
        "licenseEvidence": str(track["license_evidence"]),
        "commercialUse": True,
        "attributionRequired": False,
        "downloadedFile": downloaded_path.name,
        "sha256": digest,
        "retrievedAt": datetime.now(timezone.utc).isoformat(),
    }
