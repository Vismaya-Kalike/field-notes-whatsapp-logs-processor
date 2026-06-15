from __future__ import annotations

from datetime import datetime

from src.watermark import read_watermark, write_watermark


def test_read_missing_returns_none(tmp_path):
    assert read_watermark(tmp_path / "chatA") is None


def test_write_then_read_roundtrip(tmp_path):
    chat = tmp_path / "chatA"
    ts = datetime(2026, 6, 14, 9, 31, 0)
    write_watermark(chat, ts)
    assert read_watermark(chat) == ts
