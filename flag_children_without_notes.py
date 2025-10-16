#!/usr/bin/env python3
"""
List children that do not have any linked field notes or coordinator notes.

The script connects to the configured PostgreSQL database, searches for children
without entries in child_field_note_links, and prints the results to stdout in
either text or JSON form.
"""

from __future__ import annotations

import argparse
import json
from typing import Dict, List

try:
    from database.connection import DatabaseManager
except ModuleNotFoundError as exc:  # pragma: no cover - handled at runtime
    DatabaseManager = None  # type: ignore
    MISSING_DEPENDENCY = exc.name
else:
    MISSING_DEPENDENCY = None


def fetch_children_without_notes(db_manager: DatabaseManager) -> List[Dict[str, str]]:
    """Return a list of children that lack field or coordinator notes."""
    query = """
        SELECT
            c.id AS child_id,
            c.name AS child_name,
            c.learning_centre_id,
            COALESCE(lc.centre_name, '') AS learning_centre_name
        FROM children c
        LEFT JOIN learning_centres lc ON lc.id = c.learning_centre_id
        WHERE NOT EXISTS (
            SELECT 1
            FROM child_field_note_links l
            WHERE l.child_id = c.id
              AND (l.field_note_id IS NOT NULL OR l.coordinator_field_note_id IS NOT NULL)
        )
        ORDER BY lc.centre_name NULLS LAST, c.name
    """
    results = db_manager.execute_query(query)
    return [
        {
            "child_id": row[0],
            "child_name": row[1],
            "learning_centre_id": row[2],
            "learning_centre_name": row[3],
        }
        for row in results
    ]


def print_text_report(rows: List[Dict[str, str]]) -> None:
    if not rows:
        print("All children have at least one field or coordinator note.")
        return

    print(f"Found {len(rows)} children without any field or coordinator notes:\n")
    for entry in rows:
        centre = entry["learning_centre_name"] or "Unknown centre"
        print(
            f"- {entry['child_name']} ({entry['child_id']}) "
            f"in {centre} [{entry['learning_centre_id']}]"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flag children missing field notes or coordinator notes."
    )
    parser.add_argument(
        "--format",
        choices={"text", "json"},
        default="text",
        help="Output format. Defaults to text.",
    )
    args = parser.parse_args()

    if MISSING_DEPENDENCY:
        raise SystemExit(
            f"Unable to import required dependency '{MISSING_DEPENDENCY}'. "
            "Install project requirements before running this script."
        )

    db_manager = DatabaseManager()
    rows = fetch_children_without_notes(db_manager)

    if args.format == "json":
        print(json.dumps(rows, indent=2))
    else:
        print_text_report(rows)


if __name__ == "__main__":
    main()

