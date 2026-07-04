from __future__ import annotations

from datetime import datetime
from pathlib import Path

_FILENAME = ".watermark"


def _path(chat_dir: str | Path) -> Path:
    return Path(chat_dir) / _FILENAME


def read_watermark(chat_dir: str | Path) -> datetime | None:
    path = _path(chat_dir)
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    return datetime.fromisoformat(raw)


def write_watermark(chat_dir: str | Path, ts: datetime) -> None:
    path = _path(chat_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ts.isoformat(), encoding="utf-8")
