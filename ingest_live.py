from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from src.config import Settings
from src.db.client import create_supabase_client
from src.db.facilitators import FacilitatorLookup
from src.db.field_images import insert_batch as insert_images
from src.db.field_notes import insert_batch as insert_notes
from src.main import _process_images, _process_text
from src.models import ParsedMessage
from src.parser.whatsapp import parse_chat_file
from src.pipeline import process_messages
from src.storage.s3 import S3Uploader
from src.watermark import read_watermark, write_watermark
from src.alerts import queue_unmatched_alert

logger = logging.getLogger(__name__)


def filter_after_watermark(
    messages: list[ParsedMessage], watermark: datetime | None
) -> list[ParsedMessage]:
    if watermark is None:
        return messages
    return [m for m in messages if m.timestamp > watermark]


def max_timestamp(messages: list[ParsedMessage]) -> datetime | None:
    if not messages:
        return None
    return max(m.timestamp for m in messages)


def _find_chat_txt(chat_dir: Path) -> Path:
    txt_files = list(chat_dir.rglob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"No .txt chat file in {chat_dir}")
    return txt_files[0]


def ingest_chat(chat_dir: Path, outbox_dir: Path, *, skip_ai: bool) -> None:
    settings = Settings.from_env()
    chat_file = _find_chat_txt(chat_dir)

    all_messages = parse_chat_file(chat_file)
    watermark = read_watermark(chat_dir)
    new_messages = filter_after_watermark(all_messages, watermark)
    logger.info(
        "%s: %d total, %d new (watermark=%s)",
        chat_dir.name, len(all_messages), len(new_messages), watermark,
    )
    if not new_messages:
        return

    supabase = create_supabase_client(settings.supabase_url, settings.supabase_secret_key)
    lookup = FacilitatorLookup(supabase)
    uploader = S3Uploader(
        settings.aws_access_key_id, settings.aws_secret_access_key,
        settings.aws_region, settings.s3_bucket_name,
    )
    openai_client = None if skip_ai else OpenAI(api_key=settings.openai_api_key)

    def _images(msgs, resolved):
        images, errs = _process_images(msgs, chat_dir, uploader, resolved)
        return insert_images(supabase, images), errs

    def _text(msgs, resolved):
        return _process_text(
            msgs, resolved, openai_client, settings if openai_client else None
        )[0]

    summary = process_messages(
        new_messages,
        lookup=lookup,
        process_images=_images,
        process_text=_text,
        insert_notes=lambda notes: insert_notes(supabase, notes),
    )

    logger.info(
        "%s: stored %d notes, %d images, %d unmatched",
        chat_dir.name, summary.notes_stored, summary.images_stored,
        len(summary.unmatched_senders),
    )

    queue_unmatched_alert(
        outbox_dir, chat_name=chat_dir.name, unmatched=summary.unmatched_senders
    )

    new_watermark = max_timestamp(new_messages)
    if new_watermark:
        write_watermark(chat_dir, new_watermark)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Incremental WhatsApp ingest")
    parser.add_argument("--live-dir", default=os.getenv("LIVE_DIR", "data/live"))
    parser.add_argument("--outbox-dir", default=os.getenv("OUTBOX_DIR", "data/live/outbox"))
    parser.add_argument("--skip-ai", action="store_true")
    args = parser.parse_args()

    live_dir = Path(args.live_dir)
    outbox_dir = Path(args.outbox_dir)
    chat_dirs = [d for d in live_dir.iterdir() if d.is_dir() and d.name != "outbox"]
    if not chat_dirs:
        logger.warning("No chat directories under %s", live_dir)
        return

    for chat_dir in chat_dirs:
        try:
            ingest_chat(chat_dir, outbox_dir, skip_ai=args.skip_ai)
        except Exception:
            logger.exception("Ingest failed for %s (watermark not advanced)", chat_dir)


if __name__ == "__main__":
    main()
