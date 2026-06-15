from __future__ import annotations

from datetime import datetime
from pathlib import Path

import ingest_live
from src.pipeline import RunSummary


def _write_chat(chat_dir: Path) -> None:
    chat_dir.mkdir(parents=True, exist_ok=True)
    (chat_dir / "_chat.txt").write_text(
        "14/06/26, 09:30 - Ravi Kumar: Attendance was good\n"
        "14/06/26, 09:31 - Ravi Kumar: Kids enjoyed the songs\n",
        encoding="utf-8",
    )


def test_second_run_ingests_nothing(tmp_path, monkeypatch):
    chat_dir = tmp_path / "Facilitators"
    _write_chat(chat_dir)
    outbox = tmp_path / "outbox"

    ingested: list[int] = []

    def fake_process_messages(messages, **kwargs):
        ingested.append(len(messages))
        return RunSummary(notes_stored=len(messages))

    monkeypatch.setattr(ingest_live, "process_messages", fake_process_messages)
    monkeypatch.setattr(ingest_live, "create_supabase_client", lambda *a, **k: object())
    monkeypatch.setattr(ingest_live, "FacilitatorLookup", lambda c: object())
    monkeypatch.setattr(ingest_live, "S3Uploader", lambda *a, **k: object())
    monkeypatch.setattr(ingest_live, "OpenAI", lambda **k: object())
    monkeypatch.setattr(ingest_live.Settings, "from_env", classmethod(lambda cls: _settings()))

    ingest_live.ingest_chat(chat_dir, outbox, skip_ai=True)
    ingest_live.ingest_chat(chat_dir, outbox, skip_ai=True)

    assert ingested == [2]  # first run processes 2, second processes 0 (no call)


def _settings():
    from src.config import Settings
    return Settings(
        supabase_url="x", supabase_secret_key="x",
        aws_access_key_id="x", aws_secret_access_key="x",
        aws_region="ap-south-1", s3_bucket_name="x", openai_api_key="x",
    )
