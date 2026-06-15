from __future__ import annotations

import argparse
import logging
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from src.ai.classifier import ClassificationResult, classify_messages
from src.config import Settings
from src.db.client import create_supabase_client
from src.db.facilitators import FacilitatorLookup, ResolvedFacilitator
from src.db.field_images import insert_batch as insert_images
from src.db.field_notes import insert_batch as insert_notes
from src.models import ParsedMessage, ProcessedImage, ProcessedNote
from src.parser.whatsapp import filter_by_date_range, parse_chat_file
from src.pipeline import RunSummary, process_messages
from src.privacy.face_detector import is_image_safe
from src.storage.s3 import S3Uploader

logger = logging.getLogger(__name__)


def _find_chat_file(input_path: Path) -> tuple[Path, Path]:
    if input_path.suffix == ".zip":
        extract_dir = input_path.parent / input_path.stem
        with zipfile.ZipFile(input_path, "r") as zf:
            zf.extractall(extract_dir)
        media_dir = extract_dir
    elif input_path.is_dir():
        media_dir = input_path
    else:
        return input_path, input_path.parent

    txt_files = list(media_dir.rglob("*.txt"))
    if not txt_files:
        print("No .txt chat file found in input", file=sys.stderr)
        sys.exit(1)

    return txt_files[0], media_dir


def _process_images(
    image_msgs: list[ParsedMessage],
    media_dir: Path,
    uploader: S3Uploader,
    resolved: ResolvedFacilitator,
) -> tuple[list[ProcessedImage], list[str]]:
    processed: list[ProcessedImage] = []
    errors: list[str] = []

    for msg in image_msgs:
        filename = msg.attachment_filename
        file_path = media_dir / filename

        if not file_path.exists():
            errors.append(f"Image not found: {filename}")
            continue

        if not is_image_safe(str(file_path)):
            logger.info("Image filtered by face detection: %s", filename)
            continue

        url = uploader.upload(
            str(file_path),
            year=msg.timestamp.year,
            month=msg.timestamp.month,
            facilitator_name=resolved.name,
            filename=filename,
        )
        if not url:
            errors.append(f"S3 upload failed: {filename}")
            continue

        processed.append(ProcessedImage(
            facilitator_id=resolved.facilitator_id,
            learning_centre_id=resolved.learning_centre_id,
            photo_url=url,
            sent_at=msg.timestamp,
        ))

    return processed, errors


def _process_text(
    text_msgs: list[ParsedMessage],
    resolved: ResolvedFacilitator,
    openai_client: OpenAI | None,
    settings: Settings | None,
) -> tuple[list[ProcessedNote], list[str]]:
    errors: list[str] = []

    if openai_client and settings:
        classifications = classify_messages(
            openai_client,
            settings.classification_model,
            settings.commentary_model,
            text_msgs,
            settings.ai_batch_size,
        )
    else:
        classifications = [
            ClassificationResult(is_visible=True, ai_commentary=None, sanitized_text=None)
            for _ in text_msgs
        ]

    notes: list[ProcessedNote] = []
    for msg, cls in zip(text_msgs, classifications):
        notes.append(ProcessedNote(
            facilitator_id=resolved.facilitator_id,
            learning_centre_id=resolved.learning_centre_id,
            text=msg.text,
            sanitized_text=cls.sanitized_text,
            sent_at=msg.timestamp,
            is_visible=cls.is_visible,
            ai_commentary=cls.ai_commentary,
        ))

    return notes, errors


def run(args: argparse.Namespace) -> RunSummary:
    settings = Settings.from_env()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    input_path = Path(args.input)
    chat_file, media_dir = _find_chat_file(input_path)
    logger.info("Chat file: %s", chat_file)
    logger.info("Media dir: %s", media_dir)

    messages = parse_chat_file(chat_file)
    logger.info("Parsed %d messages", len(messages))

    if args.date_from or args.date_to:
        date_from = datetime.strptime(args.date_from, "%Y-%m-%d") if args.date_from else None
        date_to = datetime.strptime(args.date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59) if args.date_to else None
        messages = filter_by_date_range(messages, date_from, date_to)
        logger.info("After date filter: %d messages", len(messages))

    if args.sender:
        messages = [m for m in messages if args.sender.lower() in m.sender.lower()]
        if not messages:
            print(f"No sender matching '{args.sender}' found")
            return RunSummary()
        logger.info("Filtered to %d message(s) from sender matching '%s'", len(messages), args.sender)

    supabase = create_supabase_client(settings.supabase_url, settings.supabase_secret_key)
    lookup = FacilitatorLookup(supabase)

    uploader = S3Uploader(
        settings.aws_access_key_id,
        settings.aws_secret_access_key,
        settings.aws_region,
        settings.s3_bucket_name,
    )

    openai_client = None if args.skip_ai else OpenAI(api_key=settings.openai_api_key)

    def _images(msgs, resolved):
        if args.dry_run:
            return len(msgs), []
        images, errs = _process_images(msgs, media_dir, uploader, resolved)
        return insert_images(supabase, images), errs

    def _text(msgs, resolved):
        if args.dry_run:
            return []
        return _process_text(msgs, resolved, openai_client, settings if openai_client else None)[0]

    def _insert(notes):
        if args.dry_run:
            return 0
        return insert_notes(supabase, notes)

    summary = process_messages(
        messages,
        lookup=lookup,
        process_images=_images,
        process_text=_text,
        insert_notes=_insert,
        skip_images=args.skip_images,
    )

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Notes stored: {summary.notes_stored}")
    print(f"Images stored: {summary.images_stored}")
    for sender in summary.unmatched_senders:
        print(f"  UNMATCHED: {sender}")
    for err in summary.errors:
        print(f"  ERROR: {err}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Vika WhatsApp ingestion pipeline")
    parser.add_argument("--input", required=True, help="Path to ZIP file or directory")
    parser.add_argument("--date-from", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--date-to", help="End date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and match only, don't write")
    parser.add_argument("--skip-ai", action="store_true", help="Skip AI classification, mark all visible")
    parser.add_argument("--skip-images", action="store_true", help="Skip image processing")
    parser.add_argument("--sender", help="Process only this sender (matched against WhatsApp name)")

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
