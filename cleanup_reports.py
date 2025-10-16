#!/usr/bin/env python3
"""
Cleanup Script - Clears all generated reports, images, messages, and analysis.
Use this when you need to rerun the WhatsApp processing scripts from scratch.
"""

import os
import sys
import boto3
import json
from typing import Optional, List
from dotenv import load_dotenv
from database.connection import DatabaseManager
from database.report_service import ReportService
from database.child_service import ChildService
from database.image_service import ImageService
from database.message_service import MessageService
from database.analysis_service import AnalysisService

load_dotenv()


class ReportCleanup:
    def __init__(self, delete_s3: bool = False):
        """
        Initialize the cleanup tool.

        Args:
            delete_s3 (bool): If True, also delete files from S3 bucket.
                            This is dangerous and may cost storage egress fees.
        """
        # Initialize database manager and services
        self.db_manager = DatabaseManager()
        self.report_service = ReportService(self.db_manager)
        self.child_service = ChildService(self.db_manager)
        self.image_service = ImageService(self.db_manager)
        self.message_service = MessageService(self.db_manager, self.child_service)
        self.analysis_service = AnalysisService(self.db_manager)

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

    def count_records(self, month: Optional[int] = None, year: Optional[int] = None) -> dict:
        """Count all records that will be deleted."""
        counts = {}

        # Count reports
        counts['reports'] = self.report_service.count_reports_by_date(month, year)

        field_note_ids: List[str] = []

        if counts['reports'] > 0:
            # Get report IDs for counting related records
            report_ids = self.report_service.get_report_ids_by_date(month, year)

            # Count related records
            counts['images'] = self.image_service.count_images_by_report_ids(report_ids)
            counts['messages'] = self.message_service.count_messages_by_report_ids(report_ids)
            counts['llm_analyses'] = self.analysis_service.count_analyses_by_report_ids(report_ids)

            field_note_ids = self.message_service.get_field_note_ids_for_reports(report_ids)
            counts['child_links'] = self.child_service.count_links_by_field_note_ids(field_note_ids)
            counts['unique_children'] = len(self.child_service.get_child_ids_by_field_note_ids(field_note_ids))
        else:
            counts['images'] = 0
            counts['messages'] = 0
            counts['llm_analyses'] = 0
            counts['child_links'] = 0
            counts['unique_children'] = 0

        return counts

    def get_s3_image_urls(self, month: Optional[int] = None, year: Optional[int] = None) -> List[str]:
        """Get all S3 image URLs from the database."""
        # Get report IDs for the date filter
        report_ids = self.report_service.get_report_ids_by_date(month, year)

        if not report_ids:
            return []

        # Get image URLs for these reports
        return self.image_service.get_image_urls_by_report_ids(report_ids)

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

    def delete_database_records(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        delete_children: bool = False
    ):
        """Delete records from database tables (in correct order)."""
        # Get report IDs to delete
        report_ids = self.report_service.get_report_ids_by_date(month, year)

        if not report_ids:
            return {
                'reports': 0,
                'images': 0,
                'messages': 0,
                'llm_analyses': 0,
                'children': 0
            }

        field_note_ids = self.message_service.get_field_note_ids_for_reports(report_ids)
        child_ids_to_delete: List[str] = []
        if delete_children and field_note_ids:
            child_ids_to_delete = self.child_service.get_child_ids_by_field_note_ids(field_note_ids)

        # Delete in order of foreign key dependencies using services
        print("   Deleting LLM analyses...")
        llm_deleted = self.analysis_service.delete_analyses_by_report_ids(report_ids)

        print("   Deleting report images...")
        images_deleted = self.image_service.delete_images_by_report_ids(report_ids)

        print("   Deleting report messages...")
        messages_deleted = self.message_service.delete_messages_by_report_ids(report_ids)

        print("   Deleting generated reports...")
        reports_deleted = self.report_service.delete_reports_by_date(month, year)

        children_deleted = 0
        if delete_children and child_ids_to_delete:
            print("   Deleting child records...")
            children_deleted = self.child_service.delete_children_by_ids(child_ids_to_delete)

        return {
            'reports': reports_deleted,
            'images': images_deleted,
            'messages': messages_deleted,
            'llm_analyses': llm_deleted,
            'children': children_deleted
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

    def cleanup(
        self,
        clear_name_mappings: bool = True,
        month: Optional[int] = None,
        year: Optional[int] = None,
        delete_children: bool = False
    ):
        """
        Perform the full cleanup operation.

        Args:
            clear_name_mappings (bool): If True, also clear the name anonymization mappings
            month (int, optional): Only delete reports from this month (requires year)
            year (int, optional): Only delete reports from this year
            delete_children (bool): If True, also delete child records referenced by the selected notes
        """
        print("\n" + "=" * 70)
        print("🧹 REPORT CLEANUP TOOL")
        print("=" * 70)

        # Show what will be cleaned up
        if month is not None and year is not None:
            print(f"\n🎯 Target: Reports from {month}/{year}")
        elif year is not None:
            print(f"\n🎯 Target: All reports from {year}")
        else:
            print(f"\n🎯 Target: ALL REPORTS (no date filter)")

        # Count records
        print("\n📊 Counting records to be deleted...")
        counts = self.count_records(month, year)

        print(f"\n   Reports: {counts['reports']}")
        print(f"   Images: {counts['images']}")
        print(f"   Messages: {counts['messages']}")
        print(f"   LLM Analyses: {counts['llm_analyses']}")
        print(f"   Child ↔ Note links: {counts['child_links']}")
        if delete_children:
            print(f"   Children (unique): {counts['unique_children']}")
        else:
            print(f"   Children (unique): {counts['unique_children']} (will remain)")

        if counts['reports'] == 0:
            if month is not None and year is not None:
                print(f"\n✅ No records found for {month}/{year}. Nothing to clean!")
            elif year is not None:
                print(f"\n✅ No records found for {year}. Nothing to clean!")
            else:
                print("\n✅ No records found. Database is already clean!")
            return

        # Get S3 URLs if needed
        s3_urls = []
        if self.delete_s3 and counts['images'] > 0:
            print("\n📸 Getting S3 image URLs...")
            s3_urls = self.get_s3_image_urls(month, year)
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
        if delete_children and counts['unique_children'] > 0:
            print(f"   • {counts['unique_children']} child records from the database")

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
        deleted = self.delete_database_records(month, year, delete_children=delete_children)

        print(f"\n   ✅ Deleted {deleted['reports']} reports")
        print(f"   ✅ Deleted {deleted['images']} image records")
        print(f"   ✅ Deleted {deleted['messages']} message records")
        print(f"   ✅ Deleted {deleted['llm_analyses']} LLM analyses")
        if delete_children:
            print(f"   ✅ Deleted {deleted['children']} child records")
        else:
            if counts['unique_children'] > 0:
                print("   ℹ️  Child records were retained (links removed with field notes)")

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
  # Delete ALL database records (keep S3 files):
  python cleanup_reports.py

  # Delete reports for a specific month/year:
  python cleanup_reports.py --month 9 --year 2025

  # Delete all reports from a specific year:
  python cleanup_reports.py --year 2025

  # Delete database records and S3 files for specific month:
  python cleanup_reports.py --month 9 --year 2025 --delete-s3

  # Delete everything except name mappings:
  python cleanup_reports.py --delete-s3 --keep-name-mappings

  # Delete reports and associated child records:
  python cleanup_reports.py --delete-children

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

    parser.add_argument(
        '--delete-children',
        action='store_true',
        help='Also delete child records referenced by the selected field notes (default: keep children)'
    )

    parser.add_argument(
        '--month',
        type=int,
        choices=range(1, 13),
        help='Only delete reports from this specific month (1-12, requires --year)'
    )

    parser.add_argument(
        '--year',
        type=int,
        help='Only delete reports from this specific year (or all months in year if --month not specified)'
    )

    args = parser.parse_args()

    # Validate month/year combination
    if args.month is not None and args.year is None:
        parser.error("--month requires --year to be specified")

    try:
        cleanup = ReportCleanup(delete_s3=args.delete_s3)
        cleanup.cleanup(
            clear_name_mappings=not args.keep_name_mappings,
            month=args.month,
            year=args.year,
            delete_children=args.delete_children
        )
    except KeyboardInterrupt:
        print("\n\n❌ Cleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during cleanup: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
