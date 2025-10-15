"""
Database service for message operations
ONLY handles database interactions for messages
"""

from typing import List, Dict, Any
from datetime import datetime
from database.connection import DatabaseManager


class MessageService:
    """
    Pure database service for message operations
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def store_message(self, report_id: str, text: str, sent_at: datetime) -> bool:
        """
        Store a single message in database

        Args:
            report_id: Report UUID
            text: Message text (already anonymized)
            sent_at: When message was sent

        Returns:
            True if successful
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO generated_report_messages
                        (generated_report_id, text, sent_at)
                        VALUES (%s, %s, %s)
                        """,
                        (report_id, text, sent_at)
                    )
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error storing message: {e}")
            return False

    def store_messages_batch(self, messages: List[Dict[str, Any]]) -> int:
        """
        Store multiple messages in batch

        Args:
            messages: List of message dicts with keys: report_id, text, sent_at

        Returns:
            Number of messages successfully stored
        """
        stored_count = 0
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for msg in messages:
                        cur.execute(
                            """
                            INSERT INTO generated_report_messages
                            (generated_report_id, text, sent_at)
                            VALUES (%s, %s, %s)
                            """,
                            (msg['report_id'], msg['text'], msg['sent_at'])
                        )
                        stored_count += 1
                    conn.commit()
        except Exception as e:
            print(f"Error storing message batch: {e}")

        return stored_count

    def get_messages_by_report(self, report_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages for a report

        Args:
            report_id: Report UUID

        Returns:
            List of message records
        """
        query = """
            SELECT id, text, sent_at, created_at
            FROM generated_report_messages
            WHERE generated_report_id = %s
            ORDER BY sent_at
        """
        results = self.db_manager.execute_query(query, (report_id,))

        messages = []
        for row in results:
            messages.append({
                'id': row[0],
                'text': row[1],
                'sent_at': row[2],
                'created_at': row[3]
            })

        return messages

    def delete_messages_by_report(self, report_id: str) -> int:
        """
        Delete all messages for a report

        Args:
            report_id: Report UUID

        Returns:
            Number of messages deleted
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM generated_report_messages WHERE generated_report_id = %s",
                        (report_id,)
                    )
                    deleted_count = cur.rowcount
                    conn.commit()
                    return deleted_count
        except Exception as e:
            print(f"Error deleting messages: {e}")
            return 0

    def count_messages_by_report(self, report_id: str) -> int:
        """
        Count messages for a report

        Args:
            report_id: Report UUID

        Returns:
            Number of messages
        """
        query = "SELECT COUNT(*) FROM generated_report_messages WHERE generated_report_id = %s"
        result = self.db_manager.execute_query(query, (report_id,))
        return result[0][0] if result else 0

    def count_messages_by_report_ids(self, report_ids: List[str]) -> int:
        """
        Count messages for specific report IDs

        Args:
            report_ids: List of report UUIDs

        Returns:
            Number of messages
        """
        if not report_ids:
            return 0

        placeholders = ','.join(['%s'] * len(report_ids))
        query = f"SELECT COUNT(*) FROM generated_report_messages WHERE generated_report_id IN ({placeholders})"
        result = self.db_manager.execute_query(query, report_ids)
        return result[0][0] if result else 0

    def delete_messages_by_report_ids(self, report_ids: List[str]) -> int:
        """
        Delete all messages for specific report IDs

        Args:
            report_ids: List of report UUIDs

        Returns:
            Number of messages deleted
        """
        if not report_ids:
            return 0

        try:
            placeholders = ','.join(['%s'] * len(report_ids))
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM generated_report_messages WHERE generated_report_id IN ({placeholders})",
                        report_ids
                    )
                    deleted_count = cur.rowcount
                    conn.commit()
                    return deleted_count
        except Exception as e:
            print(f"Error deleting messages: {e}")
            return 0