from __future__ import annotations

import logging

from supabase import Client

from src.models import ProcessedNote

logger = logging.getLogger(__name__)


def insert_batch(client: Client, notes: list[ProcessedNote]) -> int:
    if not notes:
        return 0

    rows = [
        {
            "facilitator_id": n.facilitator_id,
            "learning_centre_id": n.learning_centre_id,
            "text": n.text,
            "sanitized_text": n.sanitized_text,
            "sent_at": n.sent_at.isoformat(),
            "is_visible": n.is_visible,
            "ai_commentary": n.ai_commentary,
        }
        for n in notes
    ]

    try:
        resp = client.table("field_notes").insert(rows).execute()
        count = len(resp.data) if resp.data else 0
        logger.info("Inserted %d field notes", count)
        return count
    except Exception:
        logger.exception("Failed to insert field notes batch")
        return 0
