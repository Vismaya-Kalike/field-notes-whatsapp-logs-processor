from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import OpenAI
from pydantic import BaseModel

from src.ai.prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
    COMMENTARY_SYSTEM_PROMPT,
    SANITIZATION_SYSTEM_PROMPT,
    build_classification_prompt,
    build_commentary_prompt,
    build_sanitization_prompt,
)
from src.models import ParsedMessage

logger = logging.getLogger(__name__)


def _get_parsed(resp):
    for item in resp.output:
        if item.type == "message" and item.content:
            return item.content[0].parsed
    return None


class VisibilityItem(BaseModel):
    is_visible: bool


class ClassificationBatch(BaseModel):
    results: list[VisibilityItem]


class CommentaryResponse(BaseModel):
    commentary: str


class SanitizationResponse(BaseModel):
    sanitized_text: str


@dataclass
class ClassificationResult:
    is_visible: bool
    ai_commentary: str | None
    sanitized_text: str | None


def _classify_batch(
    client: OpenAI,
    model: str,
    messages: list[ParsedMessage],
) -> list[bool]:
    batch_input = [{"text": m.text} for m in messages]
    user_prompt = build_classification_prompt(batch_input)

    try:
        resp = client.responses.parse(
            model=model,
            instructions=CLASSIFICATION_SYSTEM_PROMPT,
            input=user_prompt,
            text_format=ClassificationBatch,
        )

        parsed = _get_parsed(resp)
        if parsed:
            return [
                item.is_visible if i < len(parsed.results) else False
                for i, item in enumerate(parsed.results)
            ] + [False] * max(0, len(messages) - len(parsed.results))

        return [False] * len(messages)
    except Exception:
        logger.exception("Classification batch failed — defaulting all to hidden")
        return [False] * len(messages)


def _generate_commentary(
    client: OpenAI,
    model: str,
    text: str,
) -> str | None:
    user_prompt = build_commentary_prompt(text)

    try:
        resp = client.responses.parse(
            model=model,
            instructions=COMMENTARY_SYSTEM_PROMPT,
            input=user_prompt,
            text_format=CommentaryResponse,
        )

        parsed = _get_parsed(resp)
        if parsed and parsed.commentary.strip():
            return parsed.commentary
        return None
    except Exception:
        logger.exception("Commentary generation failed")
        return None


def _sanitize_text(
    client: OpenAI,
    model: str,
    text: str,
) -> str | None:
    user_prompt = build_sanitization_prompt(text)

    try:
        resp = client.responses.parse(
            model=model,
            instructions=SANITIZATION_SYSTEM_PROMPT,
            input=user_prompt,
            text_format=SanitizationResponse,
        )

        parsed = _get_parsed(resp)
        return parsed.sanitized_text if parsed else None
    except Exception:
        logger.exception("Sanitization failed")
        return None


def classify_messages(
    client: OpenAI,
    classification_model: str,
    commentary_model: str,
    messages: list[ParsedMessage],
    batch_size: int = 20,
) -> list[ClassificationResult]:
    visibility: list[bool] = []
    for start in range(0, len(messages), batch_size):
        batch = messages[start : start + batch_size]
        logger.info(
            "Classifying messages %d-%d of %d",
            start + 1, start + len(batch), len(messages),
        )
        visibility.extend(_classify_batch(client, classification_model, batch))

    visible_count = sum(visibility)
    logger.info("%d of %d messages classified as visible", visible_count, len(messages))

    results: list[ClassificationResult] = []
    visible_idx = 0
    for i, msg in enumerate(messages):
        if visibility[i]:
            visible_idx += 1
            logger.info(
                "Processing visible message %d/%d from %s",
                visible_idx, visible_count, msg.sender,
            )
            sanitized = _sanitize_text(client, commentary_model, msg.text)
            commentary = _generate_commentary(client, commentary_model, sanitized or msg.text)
            results.append(ClassificationResult(
                is_visible=True,
                ai_commentary=commentary,
                sanitized_text=sanitized,
            ))
        else:
            results.append(ClassificationResult(
                is_visible=False,
                ai_commentary=None,
                sanitized_text=None,
            ))

    return results
