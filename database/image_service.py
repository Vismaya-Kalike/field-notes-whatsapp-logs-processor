"""
Database service for field image operations.

The field_images table stores facilitator submissions independently of
generated reports, so all lookups use facilitator/centre context plus the
reporting month/year.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from database.connection import DatabaseManager


def _coalesce_timestamp_alias() -> str:
    """
    Helper to ensure we consistently coalesce sent_at/created_at inside SQL.

    Returns the SQL snippet used in JOIN / ORDER BY clauses.
    """
    return "COALESCE(fi.sent_at, fi.created_at)"


class ImageService:
    """Pure database service for field image operations."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def store_image(
        self,
        facilitator_id: str,
        learning_centre_id: str,
        photo_url: str,
        caption: Optional[str],
        sent_at: Optional[datetime],
    ) -> bool:
        """
        Store a single field image record.

        Args:
            facilitator_id: Facilitator UUID.
            learning_centre_id: Learning centre UUID.
            photo_url: S3 URL of the image.
            caption: Image caption (already anonymized).
            sent_at: When the image message was sent (optional).
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO field_images
                        (facilitator_id, learning_centre_id, photo_url, caption, sent_at)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            facilitator_id,
                            learning_centre_id,
                            photo_url,
                            caption,
                            sent_at,
                        ),
                    )
                    conn.commit()
                    return True
        except Exception as exc:
            print(f"Error storing image: {exc}")
            return False

    def store_images_batch(self, images: List[Dict[str, Any]]) -> int:
        """
        Store multiple field images.

        Each dict must include facilitator_id, learning_centre_id, photo_url,
        caption, and sent_at.
        """
        if not images:
            return 0

        stored_count = 0
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for img in images:
                        cur.execute(
                            """
                            INSERT INTO field_images
                            (facilitator_id, learning_centre_id, photo_url, caption, sent_at)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (
                                img["facilitator_id"],
                                img["learning_centre_id"],
                                img["photo_url"],
                                img.get("caption"),
                                img.get("sent_at"),
                            ),
                        )
                        stored_count += 1
                    conn.commit()
        except Exception as exc:
            print(f"Error storing image batch: {exc}")

        return stored_count

    def _build_report_join_clause(self) -> str:
        """Reuse the join conditions between field_images and generated_reports."""
        coalesce_ts = _coalesce_timestamp_alias()
        return f"""
            fi.facilitator_id = gr.facilitator_id
            AND fi.learning_centre_id = gr.learning_centre_id
            AND EXTRACT(MONTH FROM {coalesce_ts}) = gr.month
            AND EXTRACT(YEAR FROM {coalesce_ts}) = gr.year
        """

    def get_images_by_report(self, report_id: str) -> List[Dict[str, Any]]:
        """Return field images that fall within the report scope."""
        join_clause = self._build_report_join_clause()
        coalesce_ts = _coalesce_timestamp_alias()
        query = f"""
            SELECT fi.id, fi.photo_url, fi.caption, fi.sent_at, fi.created_at
            FROM field_images fi
            JOIN generated_reports gr
                ON {join_clause}
            WHERE gr.id = %s
            ORDER BY {coalesce_ts}
        """
        results = self.db_manager.execute_query(query, (report_id,))

        images: List[Dict[str, Any]] = []
        for row in results:
            images.append(
                {
                    "id": row[0],
                    "photo_url": row[1],
                    "caption": row[2],
                    "sent_at": row[3],
                    "created_at": row[4],
                }
            )
        return images

    def get_image_urls_by_report(self, report_id: str) -> List[str]:
        """Return S3 URLs for images tied to a report's facilitator/month context."""
        join_clause = self._build_report_join_clause()
        query = f"""
            SELECT fi.photo_url
            FROM field_images fi
            JOIN generated_reports gr
                ON {join_clause}
            WHERE gr.id = %s
              AND fi.photo_url IS NOT NULL
        """
        results = self.db_manager.execute_query(query, (report_id,))
        return [row[0] for row in results]

    def delete_images_by_report(self, report_id: str) -> int:
        """
        Delete field images that belong to the same facilitator/month window
        as the specified report.
        """
        join_clause = self._build_report_join_clause()
        query = f"""
            DELETE FROM field_images fi
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
            print(f"Error deleting images: {exc}")
            return 0

    def count_images_by_report(self, report_id: str) -> int:
        """Count field images associated with a report scope."""
        join_clause = self._build_report_join_clause()
        query = f"""
            SELECT COUNT(*)
            FROM field_images fi
            JOIN generated_reports gr
                ON {join_clause}
            WHERE gr.id = %s
        """
        result = self.db_manager.execute_query(query, (report_id,))
        return result[0][0] if result else 0

    def update_image_caption(self, image_id: str, new_caption: str) -> bool:
        """Update the caption for a specific field image."""
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE field_images SET caption = %s WHERE id = %s",
                        (new_caption, image_id),
                    )
                    conn.commit()
                    return True
        except Exception as exc:
            print(f"Error updating image caption: {exc}")
            return False

    def count_images_by_report_ids(self, report_ids: List[str]) -> int:
        """Count field images across multiple reports."""
        if not report_ids:
            return 0

        placeholders = ",".join(["%s"] * len(report_ids))
        join_clause = self._build_report_join_clause()
        query = f"""
            SELECT COUNT(*)
            FROM field_images fi
            JOIN generated_reports gr
                ON {join_clause}
            WHERE gr.id IN ({placeholders})
        """
        result = self.db_manager.execute_query(query, report_ids)
        return result[0][0] if result else 0

    def get_image_urls_by_report_ids(self, report_ids: List[str]) -> List[str]:
        """Collect S3 URLs for multiple reports."""
        if not report_ids:
            return []

        placeholders = ",".join(["%s"] * len(report_ids))
        join_clause = self._build_report_join_clause()
        query = f"""
            SELECT fi.photo_url
            FROM field_images fi
            JOIN generated_reports gr
                ON {join_clause}
            WHERE gr.id IN ({placeholders})
              AND fi.photo_url IS NOT NULL
        """
        results = self.db_manager.execute_query(query, report_ids)
        return [row[0] for row in results]

    def delete_images_by_report_ids(self, report_ids: List[str]) -> int:
        """Bulk delete field images for a collection of reports."""
        if not report_ids:
            return 0

        placeholders = ",".join(["%s"] * len(report_ids))
        join_clause = self._build_report_join_clause()
        query = f"""
            DELETE FROM field_images fi
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
            print(f"Error deleting images: {exc}")
            return 0
