#!/usr/bin/env python3
"""
Simple script to test Supabase database connection
"""
import os
import psycopg2
from dotenv import load_dotenv

def test_connection():
    # Load environment variables
    load_dotenv()

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        return False

    print(f"🔗 Testing connection to: {database_url.split('@')[1].split('/')[0]}")

    try:
        # Test basic connection
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        # Test a simple query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✅ Connection successful!")
        print(f"📊 PostgreSQL version: {version[0]}")

        # Test listing tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()

        if tables:
            print(f"📋 Found {len(tables)} tables in public schema:")
            for table in tables:
                print(f"   - {table[0]}")
        else:
            print("📋 No tables found in public schema")

        cursor.close()
        conn.close()
        return True

    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Supabase connection...")
    success = test_connection()
    if success:
        print("\n🎉 Connection test passed!")
    else:
        print("\n💥 Connection test failed!")