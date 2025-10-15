"""
Database service for facilitator operations
ONLY handles database interactions for facilitators
"""

from typing import Optional, List, Dict, Any
from database.connection import DatabaseManager


class FacilitatorService:
    """
    Pure database service for facilitator operations
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def find_facilitator_by_sender(self, sender_name: str) -> Optional[str]:
        """
        Find facilitator by matching sender name

        Args:
            sender_name: Name from WhatsApp message

        Returns:
            Facilitator UUID if found, None otherwise
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Try exact name match first
                cur.execute(
                    "SELECT id FROM facilitators WHERE name = %s",
                    (sender_name,)
                )
                result = cur.fetchone()
                if result:
                    return result[0]

                # Try alias match (alias is an array column)
                cur.execute(
                    "SELECT id FROM facilitators WHERE %s = ANY(alias)",
                    (sender_name,)
                )
                result = cur.fetchone()
                if result:
                    return result[0]

                # Try contact number match (for cases where sender is a phone number)
                cur.execute(
                    "SELECT id FROM facilitators WHERE contact_number = %s",
                    (sender_name,)
                )
                result = cur.fetchone()
                if result:
                    return result[0]

                return None

    def get_facilitator_by_id(self, facilitator_id: str) -> Optional[Dict[str, Any]]:
        """
        Get facilitator details by ID

        Args:
            facilitator_id: Facilitator UUID

        Returns:
            Facilitator record or None
        """
        query = "SELECT * FROM facilitators WHERE id = %s"
        results = self.db_manager.execute_query(query, (facilitator_id,))

        if results:
            # Convert to dict (assuming column order matches)
            return {
                'id': results[0][0],
                'name': results[0][1],
                'alias': results[0][2] if len(results[0]) > 2 else None,
                'contact_number': results[0][3] if len(results[0]) > 3 else None
            }
        return None

    def get_learning_centre_by_facilitator(self, facilitator_id: str) -> Optional[str]:
        """
        Get learning centre ID for a facilitator

        Args:
            facilitator_id: Facilitator UUID

        Returns:
            Learning centre UUID or None
        """
        query = """
            SELECT learning_centre_id
            FROM learning_centre_facilitators
            WHERE facilitator_id = %s
            LIMIT 1
        """
        results = self.db_manager.execute_query(query, (facilitator_id,))
        return results[0][0] if results else None

    def create_learning_centre_if_needed(self, centre_name: str = "Unknown Centre") -> str:
        """
        Create a learning centre if it doesn't exist

        Args:
            centre_name: Name of the centre

        Returns:
            Learning centre UUID
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Check if centre exists
                cur.execute(
                    "SELECT id FROM learning_centres WHERE name = %s",
                    (centre_name,)
                )
                result = cur.fetchone()
                if result:
                    return result[0]

                # Create new centre
                cur.execute(
                    """
                    INSERT INTO learning_centres
                    (name, district, state, created_at)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (centre_name, "Unknown District", "Karnataka", "NOW()")
                )
                centre_id = cur.fetchone()[0]
                conn.commit()
                return centre_id

    def get_all_facilitators(self) -> List[Dict[str, Any]]:
        """
        Get all facilitators

        Returns:
            List of facilitator records
        """
        query = "SELECT id, name, alias, contact_number FROM facilitators ORDER BY name"
        results = self.db_manager.execute_query(query)

        facilitators = []
        for row in results:
            facilitators.append({
                'id': row[0],
                'name': row[1],
                'alias': row[2],
                'contact_number': row[3]
            })

        return facilitators

    def get_unmatched_senders(self, sender_names: List[str]) -> List[str]:
        """
        Get list of sender names that don't match any facilitator

        Args:
            sender_names: List of sender names from messages

        Returns:
            List of unmatched sender names
        """
        unmatched = []
        for sender in sender_names:
            if self.find_facilitator_by_sender(sender) is None:
                unmatched.append(sender)
        return unmatched