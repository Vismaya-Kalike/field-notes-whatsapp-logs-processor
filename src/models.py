from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ParsedMessage:
    timestamp: datetime
    sender: str
    text: str
    has_attachment: bool
    attachment_filename: str | None


@dataclass
class ProcessedNote:
    facilitator_id: str
    learning_centre_id: str
    text: str
    sanitized_text: str | None
    sent_at: datetime
    is_visible: bool
    ai_commentary: str | None


@dataclass
class ProcessedImage:
    facilitator_id: str
    learning_centre_id: str
    photo_url: str
    sent_at: datetime
