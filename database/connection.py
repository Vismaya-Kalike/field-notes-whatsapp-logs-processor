"""
Database connection utilities for WhatsApp processing
Handles PostgreSQL connections and basic database operations
"""

import os
import time
from typing import Optional
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from database.constants import (
    DEFAULT_TIMEOUT,
    MAX_RETRIES,
    RETRY_DELAY,
    DATABASE_URL_ENV,
    TABLES
)

load_dotenv()


class DatabaseManager:
    """
    Manages database connections and basic operations
    """

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database manager

        Args:
            database_url: Database connection URL. If None, reads from environment
        """
        self.database_url = database_url or os.getenv(DATABASE_URL_ENV)
        if not self.database_url:
            raise ValueError(f"Database URL not found. Set {DATABASE_URL_ENV} environment variable.")

    def get_connection(self):
        """
        Create and return a database connection

        Returns:
            psycopg2 connection object
        """
        return psycopg2.connect(self.database_url)

    def test_connection(self) -> bool:
        """
        Test database connection

        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except Exception as e:
            print(f"Database connection test failed: {e}")
            return False

    def get_database_info(self) -> dict:
        """
        Get basic database information

        Returns:
            Dictionary with database info
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # Get PostgreSQL version
                    cur.execute("SELECT version()")
                    version = cur.fetchone()[0]

                    # Get database name
                    cur.execute("SELECT current_database()")
                    db_name = cur.fetchone()[0]

                    # Get table count
                    cur.execute("""
                        SELECT COUNT(*)
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                    """)
                    table_count = cur.fetchone()[0]

                    return {
                        'version': version,
                        'database_name': db_name,
                        'table_count': table_count,
                        'connection_url': self.database_url.split('@')[1].split('/')[0] if '@' in self.database_url else 'Unknown'
                    }
        except Exception as e:
            return {'error': str(e)}

    def list_tables(self) -> list:
        """
        List all tables in the public schema

        Returns:
            List of table names
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                        ORDER BY table_name
                    """)
                    return [row[0] for row in cur.fetchall()]
        except Exception as e:
            print(f"Error listing tables: {e}")
            return []

    def execute_query(self, query: str, params: tuple = None) -> list:
        """
        Execute a SELECT query and return results

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of query results
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    return cur.fetchall()
        except Exception as e:
            print(f"Error executing query: {e}")
            return []

    def execute_insert(self, query: str, params: tuple = None) -> bool:
        """
        Execute an INSERT/UPDATE/DELETE query

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error executing insert: {e}")
            return False

    def check_table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = %s
            )
        """
        result = self.execute_query(query, (table_name,))
        return result[0][0] if result else False


def get_database_manager() -> DatabaseManager:
    """
    Get a database manager instance

    Returns:
        DatabaseManager instance
    """
    return DatabaseManager()