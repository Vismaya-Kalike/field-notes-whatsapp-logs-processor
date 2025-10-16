#!/usr/bin/env python3
"""
Inspect field notes to ensure referenced children have aliases and proper links.

The script scans facilitator and coordinator field notes, detects child names
using the GPT-based logic from NameAnonymizer, then verifies:

1. Each detected name corresponds to a stored child alias (per learning centre).
2. The corresponding child is linked to the note via child_field_note_links.

When requested, it will also create missing child↔note link records.
Results and any automated fixes are reported in text or JSON form.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from database.connection import DatabaseManager
    from database.child_service import ChildService
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    DatabaseManager = None  # type: ignore
    ChildService = None  # type: ignore
    MISSING_DEPENDENCY = exc.name
else:
    MISSING_DEPENDENCY = None

try:
    from anonymizer import name_anonymizer
except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
    name_anonymizer = None  # type: ignore
    ANONYMIZER_DEPENDENCY = exc.name
else:
    ANONYMIZER_DEPENDENCY = None


@dataclass
class NoteRecord:
    note_id: str
    note_type: str  # "field" or "coordinator"
    learning_centre_id: Optional[str]
    learning_centre_name: Optional[str]
    owner_id: Optional[str]  # facilitator_id or coordinator_id
    text: str


@dataclass
class AliasMatch:
    child_id: str
    display_name: str
    source: str  # "alias" or "name"


def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def fetch_learning_centres(db_manager: DatabaseManager) -> Dict[str, str]:
    query = "SELECT id, centre_name FROM learning_centres"
    rows = db_manager.execute_query(query)
    return {row[0]: row[1] for row in rows}


def fetch_children_alias_map(db_manager: DatabaseManager) -> Dict[str, Dict[str, List[AliasMatch]]]:
    """
    Return per-centre mapping of normalised alias/name -> matching child records.
    """
    query = """
        SELECT
            id,
            learning_centre_id,
            name,
            COALESCE(alias, ARRAY[]::text[])
        FROM children
    """
    rows = db_manager.execute_query(query)
    alias_map: Dict[str, Dict[str, List[AliasMatch]]] = {}

    for child_id, centre_id, name, aliases in rows:
        if not centre_id:
            # Skip children without an associated centre to avoid misclassification.
            continue

        centre_lookup = alias_map.setdefault(centre_id, {})

        if name:
            canonical_norm = normalize(name)
            centre_lookup.setdefault(canonical_norm, []).append(
                AliasMatch(child_id=child_id, display_name=name, source="name")
            )

        for alias in aliases or []:
            if not alias:
                continue
            alias_norm = normalize(alias)
            centre_lookup.setdefault(alias_norm, []).append(
                AliasMatch(child_id=child_id, display_name=alias, source="alias")
            )

    return alias_map


def fetch_field_notes(db_manager: DatabaseManager) -> Iterable[NoteRecord]:
    query = """
        SELECT id, text, learning_centre_id, facilitator_id
        FROM field_notes
    """
    rows = db_manager.execute_query(query)
    for note_id, text, centre_id, facilitator_id in rows:
        yield NoteRecord(
            note_id=note_id,
            note_type="field",
            learning_centre_id=centre_id,
            learning_centre_name=None,  # populated later
            owner_id=facilitator_id,
            text=text or "",
        )


def fetch_coordinator_notes(db_manager: DatabaseManager) -> Iterable[NoteRecord]:
    query = """
        SELECT id, note_text, learning_centre_id, coordinator_id
        FROM coordinator_field_notes
    """
    rows = db_manager.execute_query(query)
    for note_id, text, centre_id, coordinator_id in rows:
        yield NoteRecord(
            note_id=note_id,
            note_type="coordinator",
            learning_centre_id=centre_id,
            learning_centre_name=None,  # populated later
            owner_id=coordinator_id,
            text=text or "",
        )


def detect_names(anonymizer: "name_anonymizer.NameAnonymizer", text: str, context_id: Optional[str]) -> Sequence[str]:
    if not text.strip():
        return []
    # Using GPT-driven detection via NameAnonymizer's helper.
    mapping = anonymizer.generate_alternate_names(text, context_id or "unknown-context")
    return list(mapping.keys())


def build_default_alias_map(centre_alias_map: Dict[str, Dict[str, List[AliasMatch]]]) -> Dict[str, List[AliasMatch]]:
    """
    Aggregate aliases across all centres for notes missing a learning_centre_id.
    """
    aggregate: Dict[str, List[AliasMatch]] = {}
    for centre_aliases in centre_alias_map.values():
        for alias_norm, matches in centre_aliases.items():
            aggregate.setdefault(alias_norm, []).extend(matches)
    return aggregate


def fetch_note_links(db_manager: DatabaseManager) -> Dict[str, Dict[str, Set[str]]]:
    """
    Return mapping of note_id -> linked child_ids for both note types.
    """
    query = """
        SELECT child_id, field_note_id, coordinator_field_note_id
        FROM child_field_note_links
    """
    rows = db_manager.execute_query(query)
    field_links: Dict[str, Set[str]] = {}
    coordinator_links: Dict[str, Set[str]] = {}

    for child_id, field_note_id, coordinator_field_note_id in rows:
        if field_note_id:
            field_links.setdefault(field_note_id, set()).add(child_id)
        if coordinator_field_note_id:
            coordinator_links.setdefault(coordinator_field_note_id, set()).add(child_id)

    return {"field": field_links, "coordinator": coordinator_links}


def analyse_notes(
    anonymizer: "name_anonymizer.NameAnonymizer",
    notes: Iterable[NoteRecord],
    centre_alias_map: Dict[str, Dict[str, List[AliasMatch]]],
    default_alias_map: Dict[str, List[AliasMatch]],
    note_links: Dict[str, Dict[str, Set[str]]],
    child_service: ChildService,
    fix_links: bool,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    findings: List[Dict[str, object]] = []
    linked_actions: List[Dict[str, object]] = []

    for note in notes:
        names = detect_names(anonymizer, note.text, note.owner_id)
        if not names:
            continue

        alias_map = centre_alias_map.get(note.learning_centre_id) or default_alias_map
        linked_child_ids = set(note_links.get(note.note_type, {}).get(note.note_id, set()))
        unknown: List[str] = []
        missing_links: List[Dict[str, object]] = []

        for name in names:
            norm = normalize(name)
            matches = alias_map.get(norm)
            if not matches:
                unknown.append(name)
                continue

            match_ids = {match.child_id for match in matches}

            if any(child_id in linked_child_ids for child_id in match_ids):
                continue

            if fix_links and len(match_ids) == 1:
                child_id = next(iter(match_ids))
                if note.note_type == "field":
                    child_service.link_child_to_field_note(child_id, note.note_id)
                else:
                    child_service.link_child_to_coordinator_note(child_id, note.note_id)
                linked_child_ids.add(child_id)
                note_links.setdefault(note.note_type, {}).setdefault(note.note_id, set()).add(child_id)
                linked_actions.append(
                    {
                        "note_id": note.note_id,
                        "note_type": note.note_type,
                        "child_id": child_id,
                        "name": name,
                    }
                )
                continue

            missing_links.append(
                {
                    "name": name,
                    "expected_child_ids": list(match_ids),
                    "reason": (
                        "ambiguous matches" if len(match_ids) > 1 else "no existing link"
                    ),
                }
            )

        if unknown or missing_links:
            findings.append(
                {
                    "note_id": note.note_id,
                    "note_type": note.note_type,
                    "learning_centre_id": note.learning_centre_id,
                    "learning_centre_name": note.learning_centre_name,
                    "detected_names": names,
                    "unknown_names": unknown,
                    "unlinked_children": missing_links,
                }
            )
    return findings, linked_actions


def enrich_centre_names(
    notes: Iterable[NoteRecord],
    centre_lookup: Dict[str, str],
) -> None:
    for note in notes:
        if note.learning_centre_id and note.learning_centre_id in centre_lookup:
            note.learning_centre_name = centre_lookup[note.learning_centre_id]
        else:
            note.learning_centre_name = None


def print_text_report(findings: List[Dict[str, object]], linked_actions: List[Dict[str, object]]) -> None:
    if not findings:
        print("All detected names have aliases and correct child mappings.")
        if linked_actions:
            print(
                f"Linked {len(linked_actions)} child↔note relationships during the run."
            )
        return

    print(f"Found {len(findings)} notes with alias or linkage issues:\n")
    for entry in findings:
        centre = entry.get("learning_centre_name") or entry.get("learning_centre_id") or "Unknown centre"
        problems: List[str] = []

        unknown = entry.get("unknown_names") or []
        if unknown:
            problems.append(f"unknown names => {', '.join(unknown)}")

        unlinked = entry.get("unlinked_children") or []
        if unlinked:
            formatted = ", ".join(
                f"{item['name']} (expected child ids: {', '.join(item['expected_child_ids']) or 'unknown'}; reason: {item.get('reason')})"
                for item in unlinked
            )
            problems.append(f"unlinked aliases => {formatted}")

        problem_str = "; ".join(problems)
        print(f"- [{entry['note_type']}] Note {entry['note_id']} in {centre}: {problem_str}")

    if linked_actions:
        print("\nAutomated link creations:")
        for action in linked_actions:
            print(
                f"  • Linked child {action['child_id']} to "
                f"{action['note_type']} note {action['note_id']} (name: {action['name']})"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flag field notes whose child names are not backed by child aliases.",
    )
    parser.add_argument(
        "--format",
        choices={"text", "json"},
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--note-type",
        choices={"field", "coordinator", "both"},
        default="both",
        help="Limit analysis to a note type (default: both).",
    )
    parser.add_argument(
        "--fix-links",
        action="store_true",
        help="Automatically create missing child↔note links when aliases match unlinked children.",
    )
    args = parser.parse_args()

    if MISSING_DEPENDENCY:
        raise SystemExit(
            f"Missing dependency '{MISSING_DEPENDENCY}'. Install project requirements first."
        )
    if ANONYMIZER_DEPENDENCY:
        raise SystemExit(
            f"Missing dependency '{ANONYMIZER_DEPENDENCY}'. Ensure the anonymizer package is available."
        )
    if name_anonymizer.OpenAI is None:  # type: ignore[attr-defined]
        raise SystemExit(
            "OpenAI client not available. Install the openai package and configure credentials to use GPT detection."
        )

    db_manager = DatabaseManager()
    child_service = ChildService(db_manager)
    anonymizer = name_anonymizer.NameAnonymizer(child_service)

    centre_lookup = fetch_learning_centres(db_manager)
    centre_alias_map = fetch_children_alias_map(db_manager)
    default_alias_map = build_default_alias_map(centre_alias_map)
    note_links = fetch_note_links(db_manager)

    field_notes = list(fetch_field_notes(db_manager)) if args.note_type in {"field", "both"} else []
    coordinator_notes = (
        list(fetch_coordinator_notes(db_manager)) if args.note_type in {"coordinator", "both"} else []
    )

    enrich_centre_names(field_notes, centre_lookup)
    enrich_centre_names(coordinator_notes, centre_lookup)

    findings: List[Dict[str, object]] = []
    linked_actions: List[Dict[str, object]] = []

    if field_notes:
        field_findings, field_actions = analyse_notes(
            anonymizer,
            field_notes,
            centre_alias_map,
            default_alias_map,
            note_links,
            child_service,
            args.fix_links,
        )
        findings.extend(field_findings)
        linked_actions.extend(field_actions)
    if coordinator_notes:
        coord_findings, coord_actions = analyse_notes(
            anonymizer,
            coordinator_notes,
            centre_alias_map,
            default_alias_map,
            note_links,
            child_service,
            args.fix_links,
        )
        findings.extend(coord_findings)
        linked_actions.extend(coord_actions)

    if args.format == "json":
        payload = {"issues": findings, "linked": linked_actions}
        print(json.dumps(payload, indent=2))
    else:
        print_text_report(findings, linked_actions)


if __name__ == "__main__":
    main()
