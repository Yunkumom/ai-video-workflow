from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ProjectError(ValueError):
    """Raised when an input project cannot be processed safely."""


@dataclass(frozen=True)
class SubtitleCue:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Project:
    project_id: str
    root: Path
    input_dir: Path
    processing_dir: Path
    output_dir: Path
    videos: tuple[Path, ...]
    script_path: Path | None = None
    subtitle_paths: tuple[Path, ...] = ()
    settings: dict[str, Any] = field(default_factory=dict)
