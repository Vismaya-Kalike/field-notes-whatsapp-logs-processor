from __future__ import annotations

import json
import uuid
from pathlib import Path


def queue_unmatched_alert(
    outbox_dir: str | Path,
    *,
    chat_name: str,
    unmatched: list[str],
) -> None:
    if not unmatched:
        return

    outbox = Path(outbox_dir)
    outbox.mkdir(parents=True, exist_ok=True)

    names = ", ".join(f"'{s}'" for s in unmatched)
    message = (
        f"⚠️ {len(unmatched)} unmatched sender(s) in '{chat_name}': "
        f"{names}. Add them to the JID map so their notes get ingested."
    )
    payload = {
        "type": "unmatched_senders",
        "chat": chat_name,
        "senders": unmatched,
        "message": message,
    }
    (outbox / f"{uuid.uuid4().hex}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
