"""
Database service for LLM analysis operations
ONLY handles database interactions for analysis
"""

from typing import Optional, Dict, Any, List
from database.connection import DatabaseManager


class AnalysisService:
    """
    Pure database service for LLM analysis operations
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def store_analysis(self, report_id: str, analysis_text: str) -> bool:
        """
        Store LLM analysis in database

        Args:
            report_id: Report UUID
            analysis_text: The analysis text (generated elsewhere)

        Returns:
            True if successful
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO generated_report_llm_analysis
                        (generated_report_id, text)
                        VALUES (%s, %s)
                        """,
                        (report_id, analysis_text)
                    )
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error storing analysis: {e}")
            return False

    def get_analysis_by_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Get LLM analysis for a report

        Args:
            report_id: Report UUID

        Returns:
            Analysis record or None
        """
        query = """
            SELECT id, text, created_at
            FROM generated_report_llm_analysis
            WHERE generated_report_id = %s
        """
        results = self.db_manager.execute_query(query, (report_id,))

        if results:
            row = results[0]
            return {
                'id': row[0],
                'text': row[1],
                'created_at': row[2]
            }
        return None

    def update_analysis(self, analysis_id: str, new_text: str) -> bool:
        """
        Update existing analysis

        Args:
            analysis_id: Analysis UUID
            new_text: New analysis text

        Returns:
            True if successful
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE generated_report_llm_analysis SET text = %s WHERE id = %s",
                        (new_text, analysis_id)
                    )
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error updating analysis: {e}")
            return False

    def delete_analysis_by_report(self, report_id: str) -> bool:
        """
        Delete analysis for a report

        Args:
            report_id: Report UUID

        Returns:
            True if successful
        """
        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM generated_report_llm_analysis WHERE generated_report_id = %s",
                        (report_id,)
                    )
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error deleting analysis: {e}")
            return False

    def analysis_exists(self, report_id: str) -> bool:
        """
        Check if analysis exists for a report

        Args:
            report_id: Report UUID

        Returns:
            True if analysis exists
        """
        query = """
            SELECT EXISTS(
                SELECT 1 FROM generated_report_llm_analysis
                WHERE generated_report_id = %s
            )
        """
        result = self.db_manager.execute_query(query, (report_id,))
        return result[0][0] if result else False

    def count_analyses_by_report_ids(self, report_ids: List[str]) -> int:
        """
        Count analyses for specific report IDs

        Args:
            report_ids: List of report UUIDs

        Returns:
            Number of analyses
        """
        if not report_ids:
            return 0

        placeholders = ','.join(['%s'] * len(report_ids))
        query = f"SELECT COUNT(*) FROM generated_report_llm_analysis WHERE generated_report_id IN ({placeholders})"
        result = self.db_manager.execute_query(query, report_ids)
        return result[0][0] if result else 0

    def delete_analyses_by_report_ids(self, report_ids: List[str]) -> int:
        """
        Delete all analyses for specific report IDs

        Args:
            report_ids: List of report UUIDs

        Returns:
            Number of analyses deleted
        """
        if not report_ids:
            return 0

        try:
            placeholders = ','.join(['%s'] * len(report_ids))
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM generated_report_llm_analysis WHERE generated_report_id IN ({placeholders})",
                        report_ids
                    )
                    deleted_count = cur.rowcount
                    conn.commit()
                    return deleted_count
        except Exception as e:
            print(f"Error deleting analyses: {e}")
            return 0