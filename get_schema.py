#!/usr/bin/env python3
"""Script to extract the current database schema."""

import argparse
import sys
from pathlib import Path

from database.connection import DatabaseManager


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Dump database schema to a file.")
    parser.add_argument(
        "-o",
        "--output",
        default="schema_dump.txt",
        help="Path to write the schema dump (default: schema_dump.txt).",
    )
    return parser

def get_table_schema(db_manager, table_name):
    """Get detailed schema for a specific table"""
    with db_manager.get_connection() as conn:
        with conn.cursor() as cur:
            # Get columns information
            cur.execute("""
                SELECT
                    column_name,
                    data_type,
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = %s
                ORDER BY ordinal_position;
            """, (table_name,))
            columns = cur.fetchall()

            # Get primary key
            cur.execute("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass
                AND i.indisprimary;
            """, (table_name,))
            pk_columns = [row[0] for row in cur.fetchall()]

            # Get foreign keys
            cur.execute("""
                SELECT
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_name = %s;
            """, (table_name,))
            foreign_keys = cur.fetchall()

            # Get indexes
            cur.execute("""
                SELECT
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE tablename = %s
                AND schemaname = 'public';
            """, (table_name,))
            indexes = cur.fetchall()

            return {
                'columns': columns,
                'primary_keys': pk_columns,
                'foreign_keys': foreign_keys,
                'indexes': indexes
            }

def format_schema():
    """Generate the complete database schema text dump."""
    db_manager = DatabaseManager()

    # Test connection
    if not db_manager.test_connection():
        print("❌ Failed to connect to database")
        sys.exit(1)

    lines = ["✅ Connected to database", ""]

    # Get database info
    db_info = db_manager.get_database_info()
    lines.append(f"Database: {db_info['database_name']}")
    lines.append(f"Server: {db_info['connection_url']}")
    lines.append(f"Version: {db_info['version']}")
    lines.append("=" * 80)

    # Get all tables
    tables = db_manager.list_tables()
    lines.append("")
    lines.append(f"Found {len(tables)} tables")

    for table_name in tables:
        lines.append("")
        lines.append("=" * 80)
        lines.append(f"TABLE: {table_name}")
        lines.append("=" * 80)

        schema = get_table_schema(db_manager, table_name)

        # Print columns
        lines.append("")
        lines.append("COLUMNS:")
        lines.append("-" * 80)
        for col in schema['columns']:
            col_name, data_type, max_length, nullable, default = col
            pk_marker = " [PK]" if col_name in schema['primary_keys'] else ""
            length_info = f"({max_length})" if max_length else ""
            nullable_info = "NULL" if nullable == "YES" else "NOT NULL"
            default_info = f" DEFAULT {default}" if default else ""

            lines.append(f"  {col_name}{pk_marker}")
            lines.append(f"    Type: {data_type}{length_info}")
            lines.append(f"    Nullable: {nullable_info}{default_info}")

        # Print foreign keys
        if schema['foreign_keys']:
            lines.append("")
            lines.append("FOREIGN KEYS:")
            lines.append("-" * 80)
            for fk in schema['foreign_keys']:
                col_name, ref_table, ref_col = fk
                lines.append(f"  {col_name} -> {ref_table}({ref_col})")

        # Print indexes
        if schema['indexes']:
            lines.append("")
            lines.append("INDEXES:")
            lines.append("-" * 80)
            for idx in schema['indexes']:
                idx_name, idx_def = idx
                lines.append(f"  {idx_name}")
                lines.append(f"    {idx_def}")

    return "\n".join(lines) + "\n"


def dump_schema(output_path: Path) -> None:
    """Write schema dump to file."""
    schema_text = format_schema()
    output_path.write_text(schema_text, encoding="utf-8")
    print(f"Schema written to {output_path.resolve()}")

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    dump_schema(Path(args.output))
