from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from src.models import ParsedMessage

MIN_MESSAGE_LENGTH = 3
SKIP_TEXTS = {"media omitted", "<media omitted>", "‎media omitted"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


class _Resolved(Protocol):
    facilitator_id: str
    learning_centre_id: str
    name: str


class _Lookup(Protocol):
    def resolve(self, sender: str): ...


@dataclass
class RunSummary:
    notes_stored: int = 0
    images_stored: int = 0
    unmatched_senders: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def split_messages(
    messages: list[ParsedMessage],
) -> tuple[list[ParsedMessage], list[ParsedMessage]]:
    text_msgs: list[ParsedMessage] = []
    image_msgs: list[ParsedMessage] = []
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


def process_messages(
    messages: list[ParsedMessage],
    *,
    lookup: _Lookup,
    process_images: Callable[[list[ParsedMessage], object], tuple[int, list[str]]],
    process_text: Callable[[list[ParsedMessage], object], list],
    insert_notes: Callable[[list], int],
    skip_images: bool = False,
) -> RunSummary:
    from src.parser.grouper import group_by_sender

    summary = RunSummary()
    sender_groups = group_by_sender(messages)

    for sender, sender_msgs in sender_groups.items():
        resolved = lookup.resolve(sender)
        if not resolved:
            summary.unmatched_senders.append(sender)
            continue

        text_msgs, image_msgs = split_messages(sender_msgs)

        if not skip_images:
            stored, errors = process_images(image_msgs, resolved)
            summary.images_stored += stored
            summary.errors.extend(errors)

        notes = process_text(text_msgs, resolved)
        summary.notes_stored += insert_notes(notes)

    return summary
