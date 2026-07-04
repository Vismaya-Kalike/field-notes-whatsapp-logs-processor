from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.parser.whatsapp import parse_chat_file


def test_parser_reads_bridge_formatted_lines(tmp_path):
    chat = tmp_path / "_chat.txt"
    chat.write_text(
        "14/06/26, 09:30 - Ravi Kumar: Attendance good\n"
        "14/06/26, 09:31 - Ravi Kumar: IMG-20260614-WA0001.jpg (file attached)\n"
        "great day\n",
        encoding="utf-8",
    )
    msgs = parse_chat_file(chat)

    assert msgs[0].sender == "Ravi Kumar"
    assert msgs[0].text == "Attendance good"
    assert msgs[0].timestamp == datetime(2026, 6, 14, 9, 30)

    assert msgs[1].has_attachment is True
    assert msgs[1].attachment_filename == "IMG-20260614-WA0001.jpg"
    assert msgs[1].text == "great day"
