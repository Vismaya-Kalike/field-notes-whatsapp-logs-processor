from __future__ import annotations

import argparse
import logging
import sys

from openai import OpenAI

from src.ai.classifier import (
    _classify_batch,
    _generate_commentary,
    _sanitize_text,
)
from src.ai.prompts import CLASSIFICATION_SYSTEM_PROMPT, build_classification_prompt
from src.config import Settings
from src.db.client import create_supabase_client
from src.models import ParsedMessage

logger = logging.getLogger(__name__)


def _fetch_visible_notes(client, page_size: int = 1000) -> list[dict]:
    all_notes = []
    offset = 0
    while True:
        resp = (
            client.table("field_notes")
            .select("id, text, is_visible, sanitized_text, ai_commentary")
            .eq("is_visible", True)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not resp.data:
            break
        all_notes.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size
    return all_notes


def _reclassify_batch(
    openai_client: OpenAI,
    model: str,
    notes: list[dict],
    batch_size: int,
) -> dict[str, bool]:
    results: dict[str, bool] = {}

    for start in range(0, len(notes), batch_size):
        batch = notes[start : start + batch_size]
        logger.info(
            "Classifying %d-%d of %d",
            start + 1, start + len(batch), len(notes),
        )

        msgs = [
            ParsedMessage(
                timestamp=None,
                sender="",
                text=n["text"],
                has_attachment=False,
                attachment_filename=None,
            )
            for n in batch
        ]
        visibility = _classify_batch(openai_client, model, msgs)

        for note, is_visible in zip(batch, visibility):
            results[note["id"]] = is_visible

    return results


def run(args: argparse.Namespace) -> None:
    settings = Settings.from_env()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    supabase = create_supabase_client(settings.supabase_url, settings.supabase_secret_key)
    openai_client = OpenAI(api_key=settings.openai_api_key)

    logger.info("Fetching visible field notes...")
    notes = _fetch_visible_notes(supabase)
    logger.info("Fetched %d visible notes", len(notes))

    if not notes:
        print("No notes to reprocess.")
        return

    logger.info("Reclassifying with %s...", settings.classification_model)
    visibility = _reclassify_batch(
        openai_client, settings.classification_model, notes, settings.ai_batch_size,
    )

    visible_count = sum(visibility.values())
    hidden_count = len(notes) - visible_count
    logger.info("Classification: %d visible, %d hidden", visible_count, hidden_count)

    if args.dry_run:
        print(f"\n[DRY RUN] Would update {len(notes)} notes:")
        print(f"  Visible: {visible_count}")
        print(f"  Hidden: {hidden_count}")
        return

    updated = 0
    errors = 0

    for i, note in enumerate(notes):
        note_id = note["id"]
        is_visible = visibility[note_id]

        if not is_visible:
            try:
                supabase.table("field_notes").update({
                    "is_visible": False,
                    "sanitized_text": None,
                    "ai_commentary": None,
                }).eq("id", note_id).execute()
                updated += 1
            except Exception:
                logger.exception("Failed to update note %s", note_id)
                errors += 1
            continue

        logger.info(
            "Processing visible note %d/%d (id=%s)",
            i + 1, len(notes), note_id[:8],
        )

        sanitized = _sanitize_text(openai_client, settings.commentary_model, note["text"])
        commentary = _generate_commentary(
            openai_client, settings.commentary_model, sanitized or note["text"],
        )

        try:
            supabase.table("field_notes").update({
                "is_visible": True,
                "sanitized_text": sanitized,
                "ai_commentary": commentary,
            }).eq("id", note_id).execute()
            updated += 1
        except Exception:
            logger.exception("Failed to update note %s", note_id)
            errors += 1

    print(f"\n{'=' * 60}")
    print("REPROCESS SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total visible notes: {len(notes)}")
    print(f"Still visible: {visible_count}")
    print(f"Newly hidden: {hidden_count}")
    print(f"Updated: {updated}")
    if errors:
        print(f"Errors: {errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocess AI fields on existing field notes")
    parser.add_argument("--dry-run", action="store_true", help="Classify only, don't update DB")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
