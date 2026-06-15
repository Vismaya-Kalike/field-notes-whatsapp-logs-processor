from __future__ import annotations

import json

from src.alerts import queue_unmatched_alert


def test_no_file_when_no_unmatched(tmp_path):
    queue_unmatched_alert(tmp_path, chat_name="Facilitators", unmatched=[])
    assert list(tmp_path.glob("*.json")) == []


def test_writes_alert_json(tmp_path):
    queue_unmatched_alert(tmp_path, chat_name="Facilitators", unmatched=["Ravi K", "+91999"])
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text())
    assert payload["type"] == "unmatched_senders"
    assert payload["chat"] == "Facilitators"
    assert payload["senders"] == ["Ravi K", "+91999"]
    assert "message" in payload
