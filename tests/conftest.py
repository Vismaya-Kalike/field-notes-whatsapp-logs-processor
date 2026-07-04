from __future__ import annotations

from datetime import datetime

import pytest

from src.models import ParsedMessage


@pytest.fixture
def sample_messages() -> list[ParsedMessage]:
    return [
        ParsedMessage(
            timestamp=datetime(2026, 6, 14, 9, 30),
            sender="Ravi Kumar",
            text="Attendance was good today",
            has_attachment=False,
            attachment_filename=None,
        ),
        ParsedMessage(
            timestamp=datetime(2026, 6, 14, 9, 31),
            sender="Ravi Kumar",
            text="",
            has_attachment=True,
            attachment_filename="IMG-20260614-WA0001.jpg",
        ),
    ]
