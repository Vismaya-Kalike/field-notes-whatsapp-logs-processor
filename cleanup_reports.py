#!/usr/bin/env python3
"""
Cleanup Script - Clears all generated reports, images, messages, and analysis.
Use this when you need to rerun the WhatsApp processing scripts from scratch.
"""

import os
import sys
import boto3
import psycopg2
import json
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()


class ReportCleanup:
    def __init__(self, delete_s3: bool = False):
        """
        Initialize the cleanup tool.

        Args:
            delete_s3 (bool): If True, also delete files from S3 bucket. 
                            This is dangerous and may cost storage egress fees.
        """
        # Database configuration
        self.db_url = os.getenv('DATABASE_URL')
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable is required")

        self.delete_s3 = delete_s3

        # S3 configuration (only needed if deleting from S3)
        if self.delete_s3:
            self.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
            self.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
            self.aws_region = os.getenv('AWS_REGION')
            self.s3_bucket = os.getenv('S3_BUCKET_NAME')

            if not all([self.aws_access_key, self.aws_secret_key, self.aws_region, self.s3_bucket]):
                raise ValueError(
                    "AWS S3 configuration is incomplete. Check AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, and S3_BUCKET_NAME")

            # Initialize S3 client
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
                region_name=self.aws_region
            )
            print(f"S3 deletion enabled for bucket: {self.s3_bucket}")
        else:
            print("S3 deletion disabled (files will remain in S3)")

        # Name anonymization mapping file
        self.name_mapping_file = "name_anonymization_mapping.json"

    def get_db_connection(self):
        """Create and return a database connection."""
        return psycopg2.connect(self.db_url)

    def count_records(self) -> dict:
        """Count all records that will be deleted."""
        counts = {}

        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Count generated reports
                cur.execute("SELECT COUNT(*) FROM generated_reports")
                counts['reports'] = cur.fetchone()[0]

                # Count images
                cur.execute("SELECT COUNT(*) FROM generated_report_images")
                counts['images'] = cur.fetchone()[0]

                # Count messages
                cur.execute("SELECT COUNT(*) FROM generated_report_messages")
                counts['messages'] = cur.fetchone()[0]

                # Count LLM analyses
                cur.execute(
                    "SELECT COUNT(*) FROM generated_report_llm_analysis")
                counts['llm_analyses'] = cur.fetchone()[0]

        return counts

    def get_s3_image_urls(self) -> List[str]:
        """Get all S3 image URLs from the database."""
        urls = []

        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT photo_url FROM generated_report_images WHERE photo_url IS NOT NULL")
                results = cur.fetchall()
                urls = [row[0] for row in results]

        return urls

    def delete_from_s3(self, s3_urls: List[str]) -> int:
        """Delete files from S3 bucket."""
        if not self.delete_s3:
            return 0

        deleted_count = 0
        errors = []

        for url in s3_urls:
            try:
                # Extract S3 key from URL
                # Format: https://bucket.s3.region.amazonaws.com/key
                if self.s3_bucket in url:
                    key = url.split(
                        f"{self.s3_bucket}.s3.{self.aws_region}.amazonaws.com/")[1]

                    # Delete the file
                    self.s3_client.delete_object(
                        Bucket=self.s3_bucket, Key=key)
                    deleted_count += 1

                    if deleted_count % 50 == 0:
                        print(
                            f"   Deleted {deleted_count}/{len(s3_urls)} files from S3...")
            except Exception as e:
                errors.append(f"Error deleting {url}: {str(e)}")

        if errors:
            print("\n⚠️  Some S3 deletions failed:")
            for error in errors[:10]:  # Show first 10 errors
                print(f"   {error}")
            if len(errors) > 10:
                print(f"   ... and {len(errors) - 10} more errors")

        return deleted_count

    def delete_database_records(self):
        """Delete all records from database tables (in correct order)."""
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Delete in order of foreign key dependencies
                print("   Deleting LLM analyses...")
                cur.execute("DELETE FROM generated_report_llm_analysis")
                llm_deleted = cur.rowcount

                print("   Deleting report images...")
                cur.execute("DELETE FROM generated_report_images")
                images_deleted = cur.rowcount

                print("   Deleting report messages...")
                cur.execute("DELETE FROM generated_report_messages")
                messages_deleted = cur.rowcount

                print("   Deleting generated reports...")
                cur.execute("DELETE FROM generated_reports")
                reports_deleted = cur.rowcount

                conn.commit()

                return {
                    'reports': reports_deleted,
                    'images': images_deleted,
                    'messages': messages_deleted,
                    'llm_analyses': llm_deleted
                }

    def clear_name_mappings(self):
        """Clear the name anonymization mappings file."""
        if os.path.exists(self.name_mapping_file):
            # Backup before clearing
            backup_file = f"{self.name_mapping_file}.backup"
            if os.path.exists(backup_file):
                # If backup exists, rename with timestamp
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = f"{self.name_mapping_file}.backup_{timestamp}"

            # Copy to backup
            with open(self.name_mapping_file, 'r') as f:
                content = f.read()
            with open(backup_file, 'w') as f:
                f.write(content)

            # Clear the file
            with open(self.name_mapping_file, 'w') as f:
                json.dump({}, f)

            print(f"   Name mappings cleared (backup saved to {backup_file})")
            return True
        else:
            print("   No name mappings file found")
            return False

    def cleanup(self, clear_name_mappings: bool = True):
        """
        Perform the full cleanup operation.

        Args:
            clear_name_mappings (bool): If True, also clear the name anonymization mappings
        """
        print("\n" + "=" * 70)
        print("🧹 REPORT CLEANUP TOOL")
        print("=" * 70)

        # Count records
        print("\n📊 Counting records to be deleted...")
        counts = self.count_records()

        print(f"\n   Reports: {counts['reports']}")
        print(f"   Images: {counts['images']}")
        print(f"   Messages: {counts['messages']}")
        print(f"   LLM Analyses: {counts['llm_analyses']}")

        if counts['reports'] == 0:
            print("\n✅ No records found. Database is already clean!")
            return

        # Get S3 URLs if needed
        s3_urls = []
        if self.delete_s3 and counts['images'] > 0:
            print("\n📸 Getting S3 image URLs...")
            s3_urls = self.get_s3_image_urls()
            print(f"   Found {len(s3_urls)} images in S3")

        # Confirm deletion
        print("\n⚠️  WARNING: This will permanently delete:")
        print(f"   • {counts['reports']} generated reports from database")
        print(f"   • {counts['images']} image records from database")
        print(f"   • {counts['messages']} message records from database")
        print(
            f"   • {counts['llm_analyses']} LLM analysis records from database")
        if self.delete_s3 and s3_urls:
            print(f"   • {len(s3_urls)} actual image files from S3 storage")
        if clear_name_mappings:
            print(f"   • All name anonymization mappings (with backup)")

        confirmation = input("\nType 'DELETE' to confirm: ")

        if confirmation != "DELETE":
            print("\n❌ Cleanup cancelled")
            return

        print("\n🗑️  Starting cleanup...")

        # Delete from S3 if enabled
        if self.delete_s3 and s3_urls:
            print("\n📤 Deleting files from S3...")
            deleted_s3 = self.delete_from_s3(s3_urls)
            print(f"   ✅ Deleted {deleted_s3} files from S3")

        # Delete from database
        print("\n🗄️  Deleting records from database...")
        deleted = self.delete_database_records()

        print(f"\n   ✅ Deleted {deleted['reports']} reports")
        print(f"   ✅ Deleted {deleted['images']} image records")
        print(f"   ✅ Deleted {deleted['messages']} message records")
        print(f"   ✅ Deleted {deleted['llm_analyses']} LLM analyses")

        # Clear name mappings if requested
        if clear_name_mappings:
            print("\n📝 Clearing name anonymization mappings...")
            self.clear_name_mappings()

        print("\n" + "=" * 70)
        print("✅ CLEANUP COMPLETE!")
        print("=" * 70)
        print("\nYou can now rerun the WhatsApp processing scripts.")
        print("The source data (chat files and media) remain unchanged.\n")


def main():
    """Main entry point for the cleanup script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Cleanup tool for WhatsApp report processing. Deletes all generated reports, messages, images, and analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Delete database records only (keep S3 files):
  python cleanup_reports.py
  
  # Delete database records and S3 files:
  python cleanup_reports.py --delete-s3
  
  # Delete everything except name mappings:
  python cleanup_reports.py --delete-s3 --keep-name-mappings
  
Note: S3 deletion is disabled by default to prevent accidental data loss.
      Enable with --delete-s3 flag only if you're sure.
        """
    )

    parser.add_argument(
        '--delete-s3',
        action='store_true',
        help='Also delete image files from S3 bucket (WARNING: This is permanent!)'
    )

    parser.add_argument(
        '--keep-name-mappings',
        action='store_true',
        help='Keep the name anonymization mappings (do not clear)'
    )

    args = parser.parse_args()

    try:
        cleanup = ReportCleanup(delete_s3=args.delete_s3)
        cleanup.cleanup(clear_name_mappings=not args.keep_name_mappings)
    except KeyboardInterrupt:
        print("\n\n❌ Cleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during cleanup: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
