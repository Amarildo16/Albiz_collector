from __future__ import annotations

from pathlib import Path

from ..config import PROJECT_ROOT, settings
from .time import utc_now


def build_storage_path(source_name: str, suffix: str, filename: str) -> Path:
    now = utc_now()
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


def resolve_storage_path(storage_path: str | Path) -> Path:
    path = Path(storage_path)
    if path.is_absolute():
        return path

    candidates: list[Path] = []
    for candidate in (
        (PROJECT_ROOT / path).resolve(),
        (Path.cwd() / path).resolve(),
        (settings.raw_storage_dir / path).resolve(),
    ):
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def read_storage_bytes(storage_path: str | Path) -> bytes:
    return resolve_storage_path(storage_path).read_bytes()
