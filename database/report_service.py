"""
Database service for report operations
ONLY handles database interactions for reports
"""

from typing import Optional, Dict, Any, List
from database.connection import DatabaseManager


class ReportService:
    """
    Pure database service for report operations
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def create_report(self, facilitator_id: str, learning_centre_id: str,
                     month: int, year: int, images_count: int,
                     messages_count: int, has_llm_analysis: bool = False) -> str:
        """
        Create a new report record in database

        Args:
            facilitator_id: UUID of facilitator
            learning_centre_id: UUID of learning centre
            month: Report month
            year: Report year
            images_count: Number of images
            messages_count: Number of messages
            has_llm_analysis: Whether report has LLM analysis

        Returns:
            Report ID (UUID)
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO generated_reports
                    (facilitator_id, learning_centre_id, month, year, images_count, messages_count, has_llm_analysis)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (facilitator_id, learning_centre_id, month, year, images_count, messages_count, has_llm_analysis)
                )
                report_id = cur.fetchone()[0]
                conn.commit()
                return report_id

    def update_report_llm_status(self, report_id: str, has_llm_analysis: bool = True):
        """
        Update report to indicate LLM analysis is available

        Args:
            report_id: Report UUID
            has_llm_analysis: LLM analysis status
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE generated_reports SET has_llm_analysis = %s WHERE id = %s",
                    (has_llm_analysis, report_id)
                )
                conn.commit()

    def get_report_by_id(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Get report by ID

        Args:
            report_id: Report UUID

        Returns:
            Report data or None
        """
        query = "SELECT * FROM generated_reports WHERE id = %s"
        result = self.db_manager.execute_query(query, (report_id,))
        return dict(result[0]) if result else None

    def get_reports_by_facilitator(self, facilitator_id: str) -> list:
        """
        Get all reports for a facilitator

        Args:
            facilitator_id: Facilitator UUID

        Returns:
            List of report records
        """
        query = """
            SELECT * FROM generated_reports
            WHERE facilitator_id = %s
            ORDER BY year DESC, month DESC
        """
        return self.db_manager.execute_query(query, (facilitator_id,))

    def get_report_by_id(self, report_id: str) -> Optional[tuple]:
        """
        Get a single report by ID

        Args:
            report_id: Report UUID

        Returns:
            Report tuple or None
        """
        query = "SELECT * FROM generated_reports WHERE id = %s"
        results = self.db_manager.execute_query(query, (report_id,))
        return results[0] if results else None

    def get_existing_report(self, facilitator_id: str, month: int, year: int) -> Optional[str]:
        """
        Check if a report already exists for the facilitator in the given month/year

        Args:
            facilitator_id: Facilitator UUID
            month: Month number
            year: Year number

        Returns:
            Report ID if exists, None otherwise
        """
        query = """
            SELECT id FROM generated_reports
            WHERE facilitator_id = %s AND month = %s AND year = %s
        """
        results = self.db_manager.execute_query(query, (facilitator_id, month, year))
        return results[0][0] if results else None

    def delete_report(self, report_id: str) -> bool:
        """
        Delete a report and all associated data

        Args:
            report_id: Report UUID

        Returns:
            True if successful
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Delete in order of dependencies
                    cur.execute("DELETE FROM generated_report_llm_analysis WHERE generated_report_id = %s", (report_id,))
                    cur.execute("DELETE FROM generated_report_images WHERE generated_report_id = %s", (report_id,))
                    cur.execute("DELETE FROM generated_report_messages WHERE generated_report_id = %s", (report_id,))
                    cur.execute("DELETE FROM generated_reports WHERE id = %s", (report_id,))
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error deleting report: {e}")
            return False

    def update_report_analysis_status(self, report_id: str, has_analysis: bool) -> bool:
        """
        Update the analysis status of a report

        Args:
            report_id: Report UUID
            has_analysis: Whether the report has LLM analysis

        Returns:
            True if successful
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE generated_reports SET has_llm_analysis = %s WHERE id = %s",
                        (has_analysis, report_id)
                    )
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error updating report analysis status: {e}")
            return False

    def count_reports_by_date(self, month: Optional[int] = None, year: Optional[int] = None) -> int:
        """
        Count reports by date filter

        Args:
            month: Optional month filter
            year: Optional year filter

        Returns:
            Count of matching reports
        """
        where_clause = ""
        params = []
        if month is not None and year is not None:
            where_clause = "WHERE month = %s AND year = %s"
            params = [month, year]
        elif year is not None:
            where_clause = "WHERE year = %s"
            params = [year]

        query = f"SELECT COUNT(*) FROM generated_reports {where_clause}"
        result = self.db_manager.execute_query(query, params)
        return result[0][0] if result else 0

    def get_report_ids_by_date(self, month: Optional[int] = None, year: Optional[int] = None) -> List[str]:
        """
        Get report IDs by date filter

        Args:
            month: Optional month filter
            year: Optional year filter

        Returns:
            List of report IDs
        """
        where_clause = ""
        params = []
        if month is not None and year is not None:
            where_clause = "WHERE month = %s AND year = %s"
            params = [month, year]
        elif year is not None:
            where_clause = "WHERE year = %s"
            params = [year]

        query = f"SELECT id FROM generated_reports {where_clause}"
        results = self.db_manager.execute_query(query, params)
        return [row[0] for row in results] if results else []

    def delete_reports_by_date(self, month: Optional[int] = None, year: Optional[int] = None) -> int:
        """
        Delete reports by date filter

        Args:
            month: Optional month filter
            year: Optional year filter

        Returns:
            Number of reports deleted
        """
        try:
            where_clause = ""
            params = []
            if month is not None and year is not None:
                where_clause = "WHERE month = %s AND year = %s"
                params = [month, year]
            elif year is not None:
                where_clause = "WHERE year = %s"
                params = [year]

            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"DELETE FROM generated_reports {where_clause}", params)
                    deleted_count = cur.rowcount
                    conn.commit()
                    return deleted_count
        except Exception as e:
            print(f"Error deleting reports: {e}")
            return 0