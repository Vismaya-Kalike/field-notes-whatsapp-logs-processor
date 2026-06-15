from __future__ import annotations

import argparse
import logging
import os
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
from src.parser.grouper import group_by_sender
from src.parser.whatsapp import filter_by_date_range, parse_chat_file
from src.privacy.face_detector import is_image_safe
from src.storage.s3 import S3Uploader

logger = logging.getLogger(__name__)

MIN_MESSAGE_LENGTH = 3

SKIP_TEXTS = {"media omitted", "<media omitted>", "\u200emedia omitted"}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


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


def _split_messages(
    messages: list[ParsedMessage],
) -> tuple[list[ParsedMessage], list[ParsedMessage]]:
    text_msgs = []
    image_msgs = []
    for m in messages:
        if m.has_attachment and m.attachment_filename:
            ext = Path(m.attachment_filename).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                image_msgs.append(m)
                if m.text and len(m.text) >= MIN_MESSAGE_LENGTH and m.text.strip().lower() not in SKIP_TEXTS:
                    text_msgs.append(m)
                continue
        if m.text and len(m.text) >= MIN_MESSAGE_LENGTH and m.text.strip().lower() not in SKIP_TEXTS:
            text_msgs.append(m)
    return text_msgs, image_msgs


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


def run(args: argparse.Namespace) -> None:
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

    sender_groups = group_by_sender(messages)
    logger.info("Senders: %d", len(sender_groups))

    if args.sender:
        sender_groups = {k: v for k, v in sender_groups.items() if args.sender.lower() in k.lower()}
        if not sender_groups:
            print(f"No sender matching '{args.sender}' found")
            return
        logger.info("Filtered to %d sender(s) matching '%s'", len(sender_groups), args.sender)

    supabase = create_supabase_client(settings.supabase_url, settings.supabase_secret_key)
    lookup = FacilitatorLookup(supabase)

    uploader = S3Uploader(
        settings.aws_access_key_id,
        settings.aws_secret_access_key,
        settings.aws_region,
        settings.s3_bucket_name,
    )

    openai_client = None if args.skip_ai else OpenAI(api_key=settings.openai_api_key)

    summary: dict[str, dict] = {}
    all_errors: list[str] = []

    for sender, sender_msgs in sender_groups.items():
        resolved = lookup.resolve(sender)
        if not resolved:
            logger.warning("Unmatched sender: %s (%d messages)", sender, len(sender_msgs))
            all_errors.append(f"Unmatched sender: {sender}")
            continue

        text_msgs, image_msgs = _split_messages(sender_msgs)
        sender_result = {
            "facilitator": resolved.name,
            "total": len(sender_msgs),
            "images_stored": 0,
            "notes_stored": 0,
            "notes_visible": 0,
            "notes_hidden": 0,
            "errors": [],
        }

        if args.dry_run:
            sender_result["images_found"] = len(image_msgs)
            sender_result["text_found"] = len(text_msgs)
            print(f"[DRY RUN] {sender} -> {resolved.name} | "
                  f"text={len(text_msgs)} images={len(image_msgs)}")
            summary[sender] = sender_result
            continue

        if not args.skip_images:
            images, img_errors = _process_images(image_msgs, media_dir, uploader, resolved)
            sender_result["errors"].extend(img_errors)
            all_errors.extend(img_errors)

            stored = insert_images(supabase, images)
            sender_result["images_stored"] = stored

        notes, text_errors = _process_text(
            text_msgs, resolved,
            openai_client, settings if openai_client else None,
        )
        sender_result["errors"].extend(text_errors)
        all_errors.extend(text_errors)

        stored = insert_notes(supabase, notes)
        sender_result["notes_stored"] = stored
        sender_result["notes_visible"] = sum(1 for n in notes if n.is_visible)
        sender_result["notes_hidden"] = sum(1 for n in notes if not n.is_visible)

        logger.info(
            "%s: %d notes (%d visible, %d hidden), %d images",
            resolved.name,
            sender_result["notes_stored"],
            sender_result["notes_visible"],
            sender_result["notes_hidden"],
            sender_result["images_stored"],
        )

        summary[sender] = sender_result

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for sender, result in summary.items():
        status = "[DRY RUN] " if args.dry_run else ""
        print(f"\n{status}{sender} -> {result['facilitator']}")
        if args.dry_run:
            print(f"  Text messages: {result.get('text_found', 0)}")
            print(f"  Image messages: {result.get('images_found', 0)}")
        else:
            print(f"  Notes stored: {result['notes_stored']} "
                  f"(visible={result['notes_visible']}, hidden={result['notes_hidden']})")
            print(f"  Images stored: {result['images_stored']}")
        if result.get("errors"):
            for err in result["errors"]:
                print(f"  ERROR: {err}")

    if all_errors:
        print(f"\nTotal errors: {len(all_errors)}")


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
