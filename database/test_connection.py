#!/usr/bin/env python3
"""
Test script for database connection using the database module
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import DatabaseManager

def test_connection():
    """Test database connection using the database module"""
    print("🧪 Testing database connection...")

    try:
        # Initialize database manager
        db_manager = DatabaseManager()

        # Get database info
        db_info = db_manager.get_database_info()

        if 'error' in db_info:
            print(f"❌ Connection failed: {db_info['error']}")
            return False

        print(f"🔗 Connected to: {db_info['connection_url']}")
        print(f"✅ Connection successful!")
        print(f"📊 PostgreSQL version: {db_info['version']}")
        print(f"🗃️  Database: {db_info['database_name']}")

        # List tables
        tables = db_manager.list_tables()
        if tables:
            print(f"📋 Found {len(tables)} tables in public schema:")
            for table in tables:
                print(f"   - {table}")
        else:
            print("📋 No tables found in public schema")

        return True

    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_connection()
    if success:
        print("\n🎉 Connection test passed!")
    else:
        print("\n💥 Connection test failed!")