"""
Database service for image operations
ONLY handles database interactions for images
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from database.connection import DatabaseManager


class ImageService:
    """
    Pure database service for image operations
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def store_image(self, report_id: str, photo_url: str, caption: str,
                   sent_at: datetime) -> bool:
        """
        Store a single image record in database

        Args:
            report_id: Report UUID
            photo_url: S3 URL of the image
            caption: Image caption (already anonymized)
            sent_at: When image was sent

        Returns:
            True if successful
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO generated_report_images
                        (generated_report_id, photo_url, caption, sent_at)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (report_id, photo_url, caption, sent_at)
                    )
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error storing image: {e}")
            return False

    def store_images_batch(self, images: List[Dict[str, Any]]) -> int:
        """
        Store multiple images in batch

        Args:
            images: List of image dicts with keys: report_id, photo_url, caption, sent_at

        Returns:
            Number of images successfully stored
        """
        stored_count = 0
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for img in images:
                        cur.execute(
                            """
                            INSERT INTO generated_report_images
                            (generated_report_id, photo_url, caption, sent_at)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (img['report_id'], img['photo_url'], img['caption'], img['sent_at'])
                        )
                        stored_count += 1
                    conn.commit()
        except Exception as e:
            print(f"Error storing image batch: {e}")

        return stored_count

    def get_images_by_report(self, report_id: str) -> List[Dict[str, Any]]:
        """
        Get all images for a report

        Args:
            report_id: Report UUID

        Returns:
            List of image records
        """
        query = """
            SELECT id, photo_url, caption, sent_at, created_at
            FROM generated_report_images
            WHERE generated_report_id = %s
            ORDER BY sent_at
        """
        results = self.db_manager.execute_query(query, (report_id,))

        images = []
        for row in results:
            images.append({
                'id': row[0],
                'photo_url': row[1],
                'caption': row[2],
                'sent_at': row[3],
                'created_at': row[4]
            })

        return images

    def get_image_urls_by_report(self, report_id: str) -> List[str]:
        """
        Get all S3 image URLs for a report (for cleanup purposes)

        Args:
            report_id: Report UUID

        Returns:
            List of S3 URLs
        """
        query = """
            SELECT photo_url
            FROM generated_report_images
            WHERE generated_report_id = %s AND photo_url IS NOT NULL
        """
        results = self.db_manager.execute_query(query, (report_id,))
        return [row[0] for row in results]

    def delete_images_by_report(self, report_id: str) -> int:
        """
        Delete all image records for a report

        Args:
            report_id: Report UUID

        Returns:
            Number of images deleted
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM generated_report_images WHERE generated_report_id = %s",
                        (report_id,)
                    )
                    deleted_count = cur.rowcount
                    conn.commit()
                    return deleted_count
        except Exception as e:
            print(f"Error deleting images: {e}")
            return 0

    def count_images_by_report(self, report_id: str) -> int:
        """
        Count images for a report

        Args:
            report_id: Report UUID

        Returns:
            Number of images
        """
        query = "SELECT COUNT(*) FROM generated_report_images WHERE generated_report_id = %s"
        result = self.db_manager.execute_query(query, (report_id,))
        return result[0][0] if result else 0

    def update_image_caption(self, image_id: str, new_caption: str) -> bool:
        """
        Update image caption

        Args:
            image_id: Image UUID
            new_caption: New caption text

        Returns:
            True if successful
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE generated_report_images SET caption = %s WHERE id = %s",
                        (new_caption, image_id)
                    )
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error updating image caption: {e}")
            return False

    def count_images_by_report_ids(self, report_ids: List[str]) -> int:
        """
        Count images for specific report IDs

        Args:
            report_ids: List of report UUIDs

        Returns:
            Number of images
        """
        if not report_ids:
            return 0

        placeholders = ','.join(['%s'] * len(report_ids))
        query = f"SELECT COUNT(*) FROM generated_report_images WHERE generated_report_id IN ({placeholders})"
        result = self.db_manager.execute_query(query, report_ids)
        return result[0][0] if result else 0

    def get_image_urls_by_report_ids(self, report_ids: List[str]) -> List[str]:
        """
        Get S3 image URLs for specific report IDs

        Args:
            report_ids: List of report UUIDs

        Returns:
            List of S3 URLs
        """
        if not report_ids:
            return []

        placeholders = ','.join(['%s'] * len(report_ids))
        query = f"""
            SELECT photo_url FROM generated_report_images
            WHERE generated_report_id IN ({placeholders}) AND photo_url IS NOT NULL
        """
        results = self.db_manager.execute_query(query, report_ids)
        return [row[0] for row in results]

    def delete_images_by_report_ids(self, report_ids: List[str]) -> int:
        """
        Delete all image records for specific report IDs

        Args:
            report_ids: List of report UUIDs

        Returns:
            Number of images deleted
        """
        if not report_ids:
            return 0

        try:
            placeholders = ','.join(['%s'] * len(report_ids))
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM generated_report_images WHERE generated_report_id IN ({placeholders})",
                        report_ids
                    )
                    deleted_count = cur.rowcount
                    conn.commit()
                    return deleted_count
        except Exception as e:
            print(f"Error deleting images: {e}")
            return 0