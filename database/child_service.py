"""
Database service for child records and their relationships to field notes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from database.connection import DatabaseManager


def _normalize_name(name: str) -> str:
    """Normalize a child's name for case-insensitive comparisons."""
    return name.strip().lower()


class ChildService:
    """Service class encapsulating operations on children and related links."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    # --------------------------------------------------------------------- #
    # Child lookups and mutations
    # --------------------------------------------------------------------- #
    def get_children_for_learning_centre(self, learning_centre_id: str) -> List[Dict[str, Any]]:
        """Return all children for a given learning centre."""
        query = """
            SELECT id, name, alias
            FROM children
            WHERE learning_centre_id = %s
        """
        results = self.db_manager.execute_query(query, (learning_centre_id,))
        return [
            {
                "id": row[0],
                "name": row[1],
                "alias": row[2] or [],
            }
            for row in results
        ] if results else []

    def get_child_by_name(self, learning_centre_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Fetch a child by exact name (case-insensitive) within a centre."""
        query = """
            SELECT id, name, alias
            FROM children
            WHERE learning_centre_id = %s
              AND LOWER(name) = LOWER(%s)
            LIMIT 1
        """
        results = self.db_manager.execute_query(query, (learning_centre_id, name))
        if not results:
            return None

        row = results[0]
        return {"id": row[0], "name": row[1], "alias": row[2] or []}

    def create_child(
        self,
        learning_centre_id: str,
        name: str,
        aliases: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Create a child record and return the inserted entity."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO children (learning_centre_id, name, alias)
                    VALUES (%s, %s, %s)
                    RETURNING id, name, alias
                    """,
                    (
                        learning_centre_id,
                        name,
                        list(aliases) if aliases else None,
                    ),
                )
                row = cur.fetchone()
                conn.commit()

        return {"id": row[0], "name": row[1], "alias": row[2] or []}

    def update_aliases(self, child_id: str, aliases: Sequence[str]) -> None:
        """Replace the alias array for a child."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE children SET alias = %s, updated_at = NOW() WHERE id = %s",
                    (list(aliases), child_id),
                )
                conn.commit()

    def ensure_child_with_alias(
        self,
        learning_centre_id: str,
        original_name: str,
        suggested_alias: Optional[str],
    ) -> Dict[str, Any]:
        """
        Ensure a child exists and has at least one alias.

        Returns the child record augmented with a preferred alias to use for anonymization.
        """
        child = self.get_child_by_name(learning_centre_id, original_name)
        if child:
            aliases = child["alias"]
            alias_lookup = {_normalize_name(a): a for a in aliases}

            if suggested_alias:
                normalized_suggested = _normalize_name(suggested_alias)
                if normalized_suggested not in alias_lookup:
                    aliases.append(suggested_alias)
                    self.update_aliases(child["id"], aliases)
                    alias_lookup[normalized_suggested] = suggested_alias

            preferred_alias = aliases[0] if aliases else suggested_alias or original_name

            return {
                "id": child["id"],
                "name": child["name"],
                "alias": preferred_alias,
                "aliases": aliases,
            }

        aliases: List[str] = []
        if suggested_alias:
            aliases.append(suggested_alias)

        created = self.create_child(learning_centre_id, original_name, aliases)

        preferred_alias = aliases[0] if aliases else original_name
        return {
            "id": created["id"],
            "name": created["name"],
            "alias": preferred_alias,
            "aliases": aliases,
        }

    # --------------------------------------------------------------------- #
    # Child ↔ field note relationships
    # --------------------------------------------------------------------- #
    def link_child_to_field_note(self, child_id: str, field_note_id: str) -> None:
        """Create a relationship between a child and a field note if it does not already exist."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO child_field_note_links (child_id, field_note_id)
                    SELECT %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM child_field_note_links
                        WHERE child_id = %s AND field_note_id = %s
                    )
                    """,
                    (child_id, field_note_id, child_id, field_note_id),
                )
                conn.commit()

    def link_child_to_coordinator_note(self, child_id: str, coordinator_note_id: str) -> None:
        """Create a relationship between a child and a coordinator field note if it does not already exist."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO child_field_note_links (child_id, coordinator_field_note_id)
                    SELECT %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM child_field_note_links
                        WHERE child_id = %s AND coordinator_field_note_id = %s
                    )
                    """,
                    (child_id, coordinator_note_id, child_id, coordinator_note_id),
                )
                conn.commit()

    def delete_links_by_field_note_ids(self, field_note_ids: Sequence[str]) -> int:
        """Delete child links associated with the provided field note IDs."""
        if not field_note_ids:
            return 0

        placeholders = ",".join(["%s"] * len(field_note_ids))
        query = f"""
            DELETE FROM child_field_note_links
            WHERE field_note_id IN ({placeholders})
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(field_note_ids))
                deleted = cur.rowcount
                conn.commit()
        return deleted

    def delete_links_by_coordinator_note_ids(self, coordinator_note_ids: Sequence[str]) -> int:
        """Delete child links associated with coordinator field note IDs."""
        if not coordinator_note_ids:
            return 0

        placeholders = ",".join(["%s"] * len(coordinator_note_ids))
        query = f"""
            DELETE FROM child_field_note_links
            WHERE coordinator_field_note_id IN ({placeholders})
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(coordinator_note_ids))
                deleted = cur.rowcount
                conn.commit()
        return deleted

    def delete_links_by_child_ids(self, child_ids: Sequence[str]) -> int:
        """Delete child links for the provided child IDs."""
        if not child_ids:
            return 0

        placeholders = ",".join(["%s"] * len(child_ids))
        query = f"""
            DELETE FROM child_field_note_links
            WHERE child_id IN ({placeholders})
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(child_ids))
                deleted = cur.rowcount
                conn.commit()
        return deleted

    def get_child_ids_by_field_note_ids(self, field_note_ids: Sequence[str]) -> List[str]:
        """Return distinct child IDs associated with a set of field notes."""
        if not field_note_ids:
            return []

        placeholders = ",".join(["%s"] * len(field_note_ids))
        query = f"""
            SELECT DISTINCT child_id
            FROM child_field_note_links
            WHERE field_note_id IN ({placeholders})
        """
        results = self.db_manager.execute_query(query, field_note_ids)
        return [row[0] for row in results] if results else []

    def count_links_by_field_note_ids(self, field_note_ids: Sequence[str]) -> int:
        """Count how many child → field note links exist for the supplied notes."""
        if not field_note_ids:
            return 0

        placeholders = ",".join(["%s"] * len(field_note_ids))
        query = f"""
            SELECT COUNT(*)
            FROM child_field_note_links
            WHERE field_note_id IN ({placeholders})
        """
        result = self.db_manager.execute_query(query, field_note_ids)
        return result[0][0] if result else 0

    def delete_children_by_ids(self, child_ids: Sequence[str]) -> int:
        """Delete child records by ID."""
        if not child_ids:
            return 0

        placeholders = ",".join(["%s"] * len(child_ids))
        query = f"DELETE FROM children WHERE id IN ({placeholders})"
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(child_ids))
                deleted = cur.rowcount
                conn.commit()
        return deleted

    def get_child_ids_by_coordinator_note_ids(self, coordinator_note_ids: Sequence[str]) -> List[str]:
        """Return distinct child IDs associated with coordinator field notes."""
        if not coordinator_note_ids:
            return []

        placeholders = ",".join(["%s"] * len(coordinator_note_ids))
        query = f"""
            SELECT DISTINCT child_id
            FROM child_field_note_links
            WHERE coordinator_field_note_id IN ({placeholders})
        """
        results = self.db_manager.execute_query(query, coordinator_note_ids)
        return [row[0] for row in results] if results else []

    def count_links_by_coordinator_note_ids(self, coordinator_note_ids: Sequence[str]) -> int:
        """Count how many child links exist for coordinator notes."""
        if not coordinator_note_ids:
            return 0

        placeholders = ",".join(["%s"] * len(coordinator_note_ids))
        query = f"""
            SELECT COUNT(*)
            FROM child_field_note_links
            WHERE coordinator_field_note_id IN ({placeholders})
        """
        result = self.db_manager.execute_query(query, coordinator_note_ids)
        return result[0][0] if result else 0
