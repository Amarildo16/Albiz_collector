from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import settings


def build_storage_path(source_name: str, suffix: str, filename: str) -> Path:
    now = datetime.utcnow()
    directory = (
        settings.raw_storage_dir
        / source_name
        / now.strftime("%Y")
        / now.strftime("%m")
        / now.strftime("%d")
        / suffix
    )
    directory.mkdir(parents=True, exist_ok=True)
    return directory / filename


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
