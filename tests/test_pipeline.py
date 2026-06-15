from __future__ import annotations

from dataclasses import dataclass

from src.pipeline import RunSummary, process_messages


@dataclass
class _Resolved:
    facilitator_id: str = "fac-1"
    learning_centre_id: str = "lc-1"
    name: str = "Ravi Kumar"


class _FakeLookup:
    def __init__(self, known: set[str]):
        self._known = known

    def resolve(self, sender: str):
        return _Resolved() if sender in self._known else None


class _FakeNotesSink:
    def __init__(self):
        self.notes = []

    def __call__(self, notes):
        self.notes.extend(notes)
        return len(notes)


def test_process_messages_collects_unmatched(sample_messages):
    lookup = _FakeLookup(known=set())  # nobody matches
    sink = _FakeNotesSink()

    summary = process_messages(
        sample_messages,
        lookup=lookup,
        process_images=lambda msgs, resolved: (0, []),
        insert_notes=sink,
        process_text=lambda msgs, resolved: [],
    )

    assert isinstance(summary, RunSummary)
    assert summary.unmatched_senders == ["Ravi Kumar"]
    assert summary.notes_stored == 0


def test_process_messages_stores_for_matched(sample_messages):
    lookup = _FakeLookup(known={"Ravi Kumar"})
    sink = _FakeNotesSink()

    def fake_process_text(msgs, resolved):
        return list(range(len(msgs)))  # one note per text message

    summary = process_messages(
        sample_messages,
        lookup=lookup,
        process_images=lambda msgs, resolved: (len(msgs), []),
        insert_notes=sink,
        process_text=fake_process_text,
    )

    assert summary.unmatched_senders == []
    assert summary.images_stored == 1
    assert summary.notes_stored == 1


def test_split_messages_image_with_caption_yields_both():
    from datetime import datetime

    from src.models import ParsedMessage
    from src.pipeline import split_messages

    msg = ParsedMessage(
        timestamp=datetime(2026, 6, 14, 9, 30),
        sender="Ravi Kumar",
        text="great work today",
        has_attachment=True,
        attachment_filename="IMG-20260614-WA0001.jpg",
    )
    text_msgs, image_msgs = split_messages([msg])
    assert image_msgs == [msg]
    assert text_msgs == [msg]
