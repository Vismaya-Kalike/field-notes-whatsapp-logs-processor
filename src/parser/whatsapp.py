from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from src.models import ParsedMessage

logger = logging.getLogger(__name__)

NEW_MSG_RE = re.compile(
    r"(\d{2}/\d{2}/\d{2}), (\d{2}:\d{2}) - ([^:]+): ?(.*)"
)

OLD_MSG_RE = re.compile(
    r"(?:\u200e)?\[(\d{1,2}/\d{1,2}/\d{2}), "
    r"(\d{1,2}:\d{2}:\d{2}[\u202f\s](?:AM|PM))\] "
    r"([^:]+): (?:\u200e)?(.*)"
)

NEW_ATTACHMENT_RE = re.compile(
    r"(.+\.(?:jpg|jpeg|png|gif|webp|mp4|mov|avi|webm|mp3|wav|ogg|m4a|opus|pdf|doc|docx))"
    r" \(file attached\)"
)
OLD_ATTACHMENT_RE = re.compile(r"(?:\u200e)?<attached: ([^>]+)>")

SYSTEM_PHRASES = (
    "Messages and calls are end-to-end encrypted",
    "added",
    "created group",
    "changed this group",
    "changed the group",
    "changed the subject",
    "left",
    "removed",
    "joined using this group",
    "security code changed",
    "this message was deleted",
    "You deleted this message",
    "missed voice call",
    "missed video call",
    "<media omitted>",
    "media omitted",
)


def _is_system_message(sender: str, text: str) -> bool:
    full = f"{sender}: {text}"
    return any(phrase in full for phrase in SYSTEM_PHRASES)


def _parse_new_timestamp(date_str: str, time_str: str) -> datetime:
    ts = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%y %H:%M")
    if ts.year < 2000:
        ts = ts.replace(year=ts.year + 100)
    return ts


def _parse_old_timestamp(date_str: str, time_str: str) -> datetime:
    clean_time = time_str.replace("\u202f", " ")
    ts = datetime.strptime(f"{date_str} {clean_time}", "%m/%d/%y %I:%M:%S %p")
    if ts.year < 2000:
        ts = ts.replace(year=ts.year + 100)
    return ts


def _extract_attachment(text: str) -> tuple[str, bool, str | None]:
    match = NEW_ATTACHMENT_RE.search(text)
    if match:
        clean = NEW_ATTACHMENT_RE.sub("", text).strip()
        return clean, True, match.group(1)

    match = OLD_ATTACHMENT_RE.search(text)
    if match:
        clean = OLD_ATTACHMENT_RE.sub("", text).strip()
        return clean, True, match.group(1)

    return text, False, None


def parse_chat_file(file_path: str | Path) -> list[ParsedMessage]:
    path = Path(file_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    messages: list[ParsedMessage] = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        timestamp = None
        sender = None
        text = None

        match = NEW_MSG_RE.match(line)
        if match:
            date_str, time_str, sender, text = match.groups()
            try:
                timestamp = _parse_new_timestamp(date_str, time_str)
            except ValueError:
                logger.warning("Unparseable line %d: %s", i + 1, line[:80])
                i += 1
                continue
        else:
            match = OLD_MSG_RE.match(line)
            if match:
                date_str, time_str, sender, text = match.groups()
                try:
                    timestamp = _parse_old_timestamp(date_str, time_str)
                except ValueError:
                    logger.warning("Unparseable line %d: %s", i + 1, line[:80])
                    i += 1
                    continue

        if timestamp is None:
            i += 1
            continue

        sender = sender.replace("\u202f", " ").strip()

        j = i + 1
        while j < len(lines):
            next_line = lines[j].strip()
            if not next_line:
                j += 1
                continue
            if NEW_MSG_RE.match(next_line) or OLD_MSG_RE.match(next_line):
                break
            text += " " + next_line
            j += 1

        i = j

        if _is_system_message(sender, text):
            continue

        clean_text, has_attachment, attachment_filename = _extract_attachment(text)

        messages.append(ParsedMessage(
            timestamp=timestamp,
            sender=sender,
            text=clean_text,
            has_attachment=has_attachment,
            attachment_filename=attachment_filename,
        ))

    messages.sort(key=lambda m: m.timestamp)
    return messages


def filter_by_date_range(
    messages: list[ParsedMessage],
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[ParsedMessage]:
    filtered = messages
    if date_from:
        filtered = [m for m in filtered if m.timestamp >= date_from]
    if date_to:
        filtered = [m for m in filtered if m.timestamp <= date_to]
    return filtered
