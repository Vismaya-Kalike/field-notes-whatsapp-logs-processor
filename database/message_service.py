"""
Database service for field note operations.

Field notes are stored independently of generated reports, so the service
queries rely on facilitator/learning-centre context plus the report month/year.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from database.connection import DatabaseManager

if TYPE_CHECKING:
    from database.child_service import ChildService


def _note_timestamp_alias() -> str:
    """Shared SQL snippet to reference the effective timestamp for a note."""
    return "COALESCE(fn.sent_at, fn.created_at)"


class MessageService:
    """Pure database service for field note operations."""

    def __init__(self, db_manager: DatabaseManager, child_service: Optional["ChildService"] = None):
        self.db_manager = db_manager
        self.child_service = child_service

    def store_message(
        self,
        facilitator_id: str,
        learning_centre_id: str,
        text: str,
        sent_at: Optional[datetime],
    ) -> bool:
        """
        Store a single field note.

        Args:
            facilitator_id: Facilitator UUID.
            learning_centre_id: Learning centre UUID.
            text: Already anonymised note text.
            sent_at: Timestamp when the note was sent (optional).
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO field_notes
                        (facilitator_id, learning_centre_id, text, sent_at)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (facilitator_id, learning_centre_id, text, sent_at),
                    )
                    conn.commit()
                    return True
        except Exception as exc:
            print(f"Error storing message: {exc}")
            return False

    def store_messages_batch(self, messages: List[Dict[str, Any]]) -> List[str]:
        """
        Store multiple field notes.

        Each dict must include facilitator_id, learning_centre_id, text, and
        sent_at.

        Returns:
            List of newly created field note IDs in insertion order.
        """
        if not messages:
            return []

        field_note_ids: List[str] = []
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for msg in messages:
                        cur.execute(
                            """
                            INSERT INTO field_notes
                            (facilitator_id, learning_centre_id, text, sent_at)
                            VALUES (%s, %s, %s, %s)
                            RETURNING id
                            """,
                            (
                                msg["facilitator_id"],
                                msg["learning_centre_id"],
                                msg["text"],
                                msg.get("sent_at"),
                            ),
                        )
                        inserted_id = cur.fetchone()[0]
                        field_note_ids.append(inserted_id)
                    conn.commit()
        except Exception as exc:
            print(f"Error storing message batch: {exc}")

        return field_note_ids

    def _build_report_join_clause(self) -> str:
        """Shared join clause between field_notes and generated_reports."""
        ts_alias = _note_timestamp_alias()
        return f"""
            fn.facilitator_id = gr.facilitator_id
            AND fn.learning_centre_id = gr.learning_centre_id
            AND EXTRACT(MONTH FROM {ts_alias}) = gr.month
            AND EXTRACT(YEAR FROM {ts_alias}) = gr.year
        """

    def _get_field_note_ids_for_report(self, report_id: str) -> List[str]:
        """Fetch field note IDs associated with a single report."""
        join_clause = self._build_report_join_clause()
        query = f"""
            SELECT fn.id
            FROM field_notes fn
            JOIN generated_reports gr
                ON {join_clause}
            WHERE gr.id = %s
        """
        results = self.db_manager.execute_query(query, (report_id,))
        return [row[0] for row in results] if results else []

    def _get_field_note_ids_for_reports(self, report_ids: List[str]) -> List[str]:
        """Fetch field note IDs associated with multiple reports."""
        if not report_ids:
            return []
        placeholders = ",".join(["%s"] * len(report_ids))
        join_clause = self._build_report_join_clause()
        query = f"""
            SELECT fn.id
            FROM field_notes fn
            JOIN generated_reports gr
                ON {join_clause}
            WHERE gr.id IN ({placeholders})
        """
        results = self.db_manager.execute_query(query, report_ids)
        return [row[0] for row in results] if results else []

    def get_field_note_ids_for_reports(self, report_ids: List[str]) -> List[str]:
        """Public helper to fetch field note IDs for the provided report IDs."""
        return self._get_field_note_ids_for_reports(report_ids)

    def get_messages_by_report(self, report_id: str) -> List[Dict[str, Any]]:
        """Fetch field notes associated with a generated report."""
        join_clause = self._build_report_join_clause()
        ts_alias = _note_timestamp_alias()
        query = f"""
            SELECT fn.id, fn.text, fn.sent_at, fn.created_at
            FROM field_notes fn
            JOIN generated_reports gr
                ON {join_clause}
            WHERE gr.id = %s
            ORDER BY {ts_alias}
        """
        results = self.db_manager.execute_query(query, (report_id,))

        messages: List[Dict[str, Any]] = []
        for row in results:
            messages.append(
                {
                    "id": row[0],
                    "text": row[1],
                    "sent_at": row[2],
                    "created_at": row[3],
                }
            )

        return messages

    def delete_messages_by_report(self, report_id: str) -> int:
        """
        Delete field notes that align with the facilitator/month window for the
        supplied report. Child relationships are removed prior to deletion when
        a ChildService is available.
        """
        note_ids = self._get_field_note_ids_for_report(report_id)
        if note_ids and self.child_service:
            self.child_service.delete_links_by_field_note_ids(note_ids)

        join_clause = self._build_report_join_clause()
        query = f"""
            DELETE FROM field_notes fn
            USING generated_reports gr
            WHERE gr.id = %s
              AND {join_clause}
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (report_id,))
                    deleted_count = cur.rowcount
                    conn.commit()
                    return deleted_count
        except Exception as exc:
            print(f"Error deleting messages: {exc}")
            return 0

    def count_messages_by_report(self, report_id: str) -> int:
        """Count field notes for a given report scope."""
        join_clause = self._build_report_join_clause()
        query = f"""
            SELECT COUNT(*)
            FROM field_notes fn
            JOIN generated_reports gr
                ON {join_clause}
            WHERE gr.id = %s
        """
        result = self.db_manager.execute_query(query, (report_id,))
        return result[0][0] if result else 0

    def count_messages_by_report_ids(self, report_ids: List[str]) -> int:
        """Count field notes across multiple reports."""
        if not report_ids:
            return 0

        placeholders = ",".join(["%s"] * len(report_ids))
        join_clause = self._build_report_join_clause()
        query = f"""
            SELECT COUNT(*)
            FROM field_notes fn
            JOIN generated_reports gr
                ON {join_clause}
            WHERE gr.id IN ({placeholders})
        """
        result = self.db_manager.execute_query(query, report_ids)
        return result[0][0] if result else 0

    def delete_messages_by_report_ids(self, report_ids: List[str]) -> int:
        """Bulk delete field notes for multiple reports."""
        if not report_ids:
            return 0

        note_ids = self._get_field_note_ids_for_reports(report_ids)
        if note_ids and self.child_service:
            self.child_service.delete_links_by_field_note_ids(note_ids)

        placeholders = ",".join(["%s"] * len(report_ids))
        join_clause = self._build_report_join_clause()
        query = f"""
            DELETE FROM field_notes fn
            USING generated_reports gr
            WHERE gr.id IN ({placeholders})
              AND {join_clause}
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, report_ids)
                    deleted_count = cur.rowcount
                    conn.commit()
                    return deleted_count
        except Exception as exc:
            print(f"Error deleting messages: {exc}")
            return 0
