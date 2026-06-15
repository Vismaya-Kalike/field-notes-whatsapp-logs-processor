from __future__ import annotations

import logging

from supabase import Client

from src.models import ProcessedImage

logger = logging.getLogger(__name__)


def insert_batch(client: Client, images: list[ProcessedImage]) -> int:
    if not images:
        return 0

    rows = [
        {
            "facilitator_id": img.facilitator_id,
            "learning_centre_id": img.learning_centre_id,
            "photo_url": img.photo_url,
            "sent_at": img.sent_at.isoformat(),
        }
        for img in images
    ]

    try:
        resp = client.table("field_images").insert(rows).execute()
        count = len(resp.data) if resp.data else 0
        logger.info("Inserted %d field images", count)
        return count
    except Exception:
        logger.exception("Failed to insert field images batch")
        return 0
