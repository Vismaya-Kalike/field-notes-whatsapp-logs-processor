from __future__ import annotations

from collections import defaultdict

from src.models import ParsedMessage


def group_by_sender(messages: list[ParsedMessage]) -> dict[str, list[ParsedMessage]]:
    groups: dict[str, list[ParsedMessage]] = defaultdict(list)
    for msg in messages:
        groups[msg.sender].append(msg)
    return dict(groups)
