from __future__ import annotations

from datetime import datetime

from ingest_live import filter_after_watermark, max_timestamp
from src.models import ParsedMessage


def _msg(minute: int) -> ParsedMessage:
    return ParsedMessage(
        timestamp=datetime(2026, 6, 14, 9, minute),
        sender="Ravi Kumar",
        text=f"msg {minute}",
        has_attachment=False,
        attachment_filename=None,
    )


def test_filter_none_watermark_returns_all():
    msgs = [_msg(30), _msg(31)]
    assert filter_after_watermark(msgs, None) == msgs


def test_filter_is_strictly_greater():
    msgs = [_msg(30), _msg(31), _msg(32)]
    result = filter_after_watermark(msgs, datetime(2026, 6, 14, 9, 31))
    assert [m.timestamp.minute for m in result] == [32]


def test_max_timestamp_of_empty_is_none():
    assert max_timestamp([]) is None


def test_max_timestamp_picks_latest():
    assert max_timestamp([_msg(30), _msg(32), _msg(31)]) == datetime(2026, 6, 14, 9, 32)
