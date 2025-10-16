"""
Database service for coordinator field notes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from database.connection import DatabaseManager


class CoordinatorNoteService:
    """Encapsulates CRUD logic for coordinator_field_notes table."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def create_note(
        self,
        coordinator_id: str,
        learning_centre_id: str,
        noted_at: datetime,
        note_text: str,
    ) -> str:
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO coordinator_field_notes
                    (coordinator_id, learning_centre_id, noted_at, note_text)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (coordinator_id, learning_centre_id, noted_at, note_text),
                )
                note_id = cur.fetchone()[0]
                conn.commit()
        return note_id

    def find_existing_note(
        self,
        coordinator_id: str,
        learning_centre_id: str,
        noted_at: datetime,
    ) -> Optional[str]:
        query = """
            SELECT id
            FROM coordinator_field_notes
            WHERE coordinator_id = %s
              AND learning_centre_id = %s
              AND DATE(noted_at) = DATE(%s)
            LIMIT 1
        """
        results = self.db_manager.execute_query(query, (coordinator_id, learning_centre_id, noted_at))
        return results[0][0] if results else None
