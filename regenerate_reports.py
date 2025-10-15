#!/usr/bin/env python3
"""
Regenerate Reports Script - Regenerates LLM analysis for existing reports using database data.
This script is useful when you want to reprocess reports with updated prompts or regenerate analysis.
"""

import os
import sys
import argparse
import requests
import tempfile
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from database.connection import DatabaseManager
from database.facilitator_service import FacilitatorService
from database.report_service import ReportService
from database.image_service import ImageService
from database.message_service import MessageService
from database.analysis_service import AnalysisService
from llm_analyzer.llm_analyzer import LLMAnalyzer
from image_processor.image_processor import ImageProcessor
from image_processor.s3_uploader import S3ImageUploader
from anonymizer.name_anonymizer import NameAnonymizer

load_dotenv()


class ReportRegenerator:
    def __init__(self, temp_dir: Optional[str] = None):
        """Initialize the report regenerator with database services and LLM analyzer."""
        # Initialize database manager and services
        self.db_manager = DatabaseManager()
        self.facilitator_service = FacilitatorService(self.db_manager)
        self.report_service = ReportService(self.db_manager)
        self.image_service = ImageService(self.db_manager)
        self.message_service = MessageService(self.db_manager)
        self.analysis_service = AnalysisService(self.db_manager)

        # Initialize S3 uploader for image processing
        self.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.aws_region = os.getenv('AWS_REGION')
        self.s3_bucket = os.getenv('S3_BUCKET_NAME')

        if not all([self.aws_access_key, self.aws_secret_key, self.aws_region, self.s3_bucket]):
            raise ValueError(
                "AWS S3 configuration is incomplete. Check AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, and S3_BUCKET_NAME")

        # Initialize components for LLM analysis
        self.name_anonymizer = NameAnonymizer()
        self.s3_uploader = S3ImageUploader(
            self.aws_access_key,
            self.aws_secret_key,
            self.aws_region,
            self.s3_bucket
        )
        self.image_processor = ImageProcessor(
            self.s3_uploader,
            self.name_anonymizer
        )
        self.llm_analyzer = LLMAnalyzer(self.image_processor)

        # Setup temporary directory for downloaded images
        if temp_dir:
            self.temp_dir = temp_dir
            os.makedirs(temp_dir, exist_ok=True)
        else:
            self.temp_dir = tempfile.mkdtemp(prefix="regenerate_images_")

        print(f"Initialized regenerator with S3 bucket: {self.s3_bucket}")
        print(f"Using temporary directory for images: {self.temp_dir}")

    def find_reports_to_regenerate(self, facilitator_name: Optional[str] = None,
                                 facilitator_id: Optional[str] = None,
                                 month: Optional[int] = None,
                                 year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Find reports that match the given criteria.

        Args:
            facilitator_name: Name of facilitator to filter by
            facilitator_id: ID of facilitator to filter by
            month: Month to filter by
            year: Year to filter by

        Returns:
            List of report records
        """
        # If facilitator name is provided, get the facilitator ID
        if facilitator_name and not facilitator_id:
            facilitator_id = self.facilitator_service.find_facilitator_by_sender(facilitator_name)
            if not facilitator_id:
                print(f"❌ No facilitator found with name: {facilitator_name}")
                return []

        # Get all reports that match criteria
        if facilitator_id:
            # Get reports for specific facilitator
            reports = self.report_service.get_reports_by_facilitator(facilitator_id)

            # Filter by date if specified
            if month is not None and year is not None:
                reports = [r for r in reports if r[3] == month and r[4] == year]  # month and year columns
            elif year is not None:
                reports = [r for r in reports if r[4] == year]  # year column
        else:
            # Get all report IDs for the date filter
            report_ids = self.report_service.get_report_ids_by_date(month, year)
            if not report_ids:
                return []

            # Get full report records
            reports = []
            for report_id in report_ids:
                report = self.report_service.get_report_by_id(report_id)
                if report:
                    reports.append(report)

        # Convert to list of dicts for easier handling
        report_dicts = []
        for report in reports:
            report_dict = {
                'id': report[0],
                'facilitator_id': report[1],
                'learning_centre_id': report[2],
                'month': report[3],
                'year': report[4],
                'images_count': report[5],
                'messages_count': report[6],
                'has_llm_analysis': report[7],
                'created_at': report[8] if len(report) > 8 else None
            }
            report_dicts.append(report_dict)

        return report_dicts

    def get_report_data(self, report_id: str) -> Dict[str, Any]:
        """
        Get all data for a report from the database.

        Args:
            report_id: Report UUID

        Returns:
            Dictionary containing images and messages
        """
        # Get images for the report
        images = self.image_service.get_images_by_report(report_id)

        # Get messages for the report
        messages = self.message_service.get_messages_by_report(report_id)

        return {
            'images': images,
            'messages': messages
        }

    def download_image_from_s3(self, image_url: str, image_id: str) -> Optional[str]:
        """
        Download an image from S3 URL to local temporary directory.

        Args:
            image_url: S3 URL of the image
            image_id: Unique identifier for the image

        Returns:
            Local file path if successful, None otherwise
        """
        try:
            # Parse URL to get filename extension
            parsed_url = urlparse(image_url)
            # Try to get extension from URL, default to .jpg
            path_parts = parsed_url.path.split('.')
            extension = f".{path_parts[-1]}" if len(path_parts) > 1 and path_parts[-1] in ['jpg', 'jpeg', 'png', 'gif', 'webp'] else '.jpg'

            # Create local filename
            local_filename = f"image_{image_id}{extension}"
            local_path = os.path.join(self.temp_dir, local_filename)

            # Skip if already downloaded
            if os.path.exists(local_path):
                return local_path

            # Download the image
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()

            # Save to local file
            with open(local_path, 'wb') as f:
                f.write(response.content)

            return local_path

        except Exception as e:
            print(f"   ⚠️  Failed to download image {image_id}: {str(e)}")
            return None

    def download_images_for_report(self, images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Download all images for a report to local temporary directory.

        Args:
            images: List of image records from database

        Returns:
            List of image records with local_path added
        """
        processed_images = []

        for img in images:
            # Create a copy of the image record
            processed_img = img.copy()

            # Download the image
            if img['photo_url']:
                local_path = self.download_image_from_s3(img['photo_url'], img['id'])
                if local_path:
                    processed_img['local_path'] = local_path
                    processed_img['filename'] = os.path.basename(local_path)
                else:
                    # If download fails, we'll still include the image but without local_path
                    # This will trigger text-only analysis
                    processed_img['filename'] = f"image_{img['id']}.jpg"
            else:
                processed_img['filename'] = f"image_{img['id']}.jpg"

            processed_images.append(processed_img)

        return processed_images

    def prepare_data_for_analysis(self, report_data: Dict[str, Any]) -> tuple:
        """
        Prepare database data for LLM analysis, downloading images locally.

        Args:
            report_data: Dictionary containing images and messages from database

        Returns:
            Tuple of (safe_images, text_messages) formatted for LLM analyzer
        """
        # Download images locally first
        print(f"   📥 Downloading {len(report_data['images'])} images...")
        processed_images = self.download_images_for_report(report_data['images'])

        # Convert to format expected by LLM analyzer
        safe_images = []
        downloaded_count = 0
        for img in processed_images:
            image_data = {
                'filename': img['filename'],
                'photo_url': img['photo_url'],
                'caption': img['caption'],
                'timestamp': img['sent_at'],
                'sent_at': img['sent_at']
            }

            # Add local_path if download was successful
            if 'local_path' in img:
                image_data['local_path'] = img['local_path']
                downloaded_count += 1

            safe_images.append(image_data)

        if downloaded_count > 0:
            print(f"   ✅ Successfully downloaded {downloaded_count}/{len(processed_images)} images")
        else:
            print(f"   ⚠️  No images downloaded successfully - will use text-only analysis")

        # Convert database messages to format expected by LLM analyzer
        text_messages = []
        for msg in report_data['messages']:
            text_messages.append({
                'text': msg['text'],
                'timestamp': msg['sent_at']
            })

        return safe_images, text_messages

    def regenerate_analysis_for_report(self, report: Dict[str, Any],
                                     force_regenerate: bool = False) -> bool:
        """
        Regenerate LLM analysis for a single report.

        Args:
            report: Report dictionary
            force_regenerate: If True, regenerate even if analysis already exists

        Returns:
            True if analysis was regenerated successfully
        """
        report_id = report['id']

        # Check if analysis already exists
        if report['has_llm_analysis'] and not force_regenerate:
            print(f"   ⏭️  Analysis already exists for report {report_id}, skipping...")
            return True

        print(f"   🤖 Regenerating analysis for report {report_id}...")

        try:
            # Get report data from database
            report_data = self.get_report_data(report_id)

            if not report_data['images'] and not report_data['messages']:
                print(f"   ⚠️  No data found for report {report_id}")
                return False

            # Prepare data for analysis
            safe_images, text_messages = self.prepare_data_for_analysis(report_data)

            # Get facilitator info for analysis
            facilitator = self.facilitator_service.get_facilitator_by_id(report['facilitator_id'])
            facilitator_name = facilitator['name'] if facilitator else 'Unknown Facilitator'

            print(f"   📊 Found {len(safe_images)} images and {len(text_messages)} messages")

            # Check if we have enough content for analysis
            if not self.llm_analyzer.is_analysis_viable(safe_images, text_messages):
                print(f"   ⚠️  Insufficient content for analysis")
                return False

            # Generate LLM analysis
            images_with_local_paths = [img for img in safe_images if 'local_path' in img]

            if images_with_local_paths:
                # Full comprehensive analysis with downloaded images
                print(f"   🖼️  Generating comprehensive analysis with {len(images_with_local_paths)} images...")
                analysis = self.llm_analyzer.generate_comprehensive_analysis(
                    facilitator_name, safe_images, text_messages)
            else:
                # Text-only analysis fallback
                print(f"   📝 Generating text-only analysis...")
                analysis = self.llm_analyzer.generate_text_only_analysis(
                    facilitator_name, safe_images, text_messages)

            if analysis:
                # Delete existing analysis if it exists
                if report['has_llm_analysis']:
                    self.analysis_service.delete_analysis_by_report(report_id)

                # Store new analysis
                success = self.analysis_service.store_analysis(report_id, analysis)
                if success:
                    # Update report status
                    self.report_service.update_report_analysis_status(report_id, True)
                    print(f"   ✅ Analysis regenerated successfully")
                    return True
                else:
                    print(f"   ❌ Failed to store analysis")
                    return False
            else:
                print(f"   ❌ Failed to generate analysis")
                return False

        except Exception as e:
            print(f"   ❌ Error regenerating analysis: {str(e)}")
            return False

    def regenerate_reports(self, facilitator_name: Optional[str] = None,
                          facilitator_id: Optional[str] = None,
                          month: Optional[int] = None,
                          year: Optional[int] = None,
                          force_regenerate: bool = False) -> Dict[str, Any]:
        """
        Regenerate reports based on the given criteria.

        Args:
            facilitator_name: Name of facilitator to filter by
            facilitator_id: ID of facilitator to filter by
            month: Month to filter by
            year: Year to filter by
            force_regenerate: If True, regenerate even if analysis already exists

        Returns:
            Dictionary with regeneration results
        """
        print("\n" + "=" * 70)
        print("🔄 REPORT REGENERATION TOOL")
        print("=" * 70)

        # Show filtering criteria
        filters = []
        if facilitator_name:
            filters.append(f"Facilitator: {facilitator_name}")
        elif facilitator_id:
            filters.append(f"Facilitator ID: {facilitator_id}")
        if month is not None and year is not None:
            filters.append(f"Date: {month}/{year}")
        elif year is not None:
            filters.append(f"Year: {year}")

        if filters:
            print(f"\n🎯 Filters: {', '.join(filters)}")
        else:
            print(f"\n🎯 Target: ALL REPORTS")

        print(f"\n🔍 Finding reports to regenerate...")

        # Find reports that match criteria
        reports = self.find_reports_to_regenerate(
            facilitator_name, facilitator_id, month, year)

        if not reports:
            print("✅ No reports found matching the criteria.")
            return {'regenerated': 0, 'skipped': 0, 'errors': 0}

        print(f"   Found {len(reports)} reports")

        # Filter reports that need regeneration if not forcing
        if not force_regenerate:
            reports_needing_regen = [r for r in reports if not r['has_llm_analysis']]
            reports_with_analysis = len(reports) - len(reports_needing_regen)

            if reports_with_analysis > 0:
                print(f"   {reports_with_analysis} reports already have analysis (use --force to regenerate)")

            reports = reports_needing_regen

        if not reports:
            print("✅ All reports already have analysis. Use --force to regenerate.")
            return {'regenerated': 0, 'skipped': len(reports), 'errors': 0}

        # Confirm regeneration
        action = "regenerate" if force_regenerate else "generate"
        print(f"\n⚠️  This will {action} LLM analysis for {len(reports)} reports.")
        if not force_regenerate:
            print("   (Reports with existing analysis will be skipped)")

        confirmation = input(f"\nType 'REGENERATE' to confirm: ")
        if confirmation != "REGENERATE":
            print("\n❌ Regeneration cancelled")
            return {'regenerated': 0, 'skipped': 0, 'errors': 0}

        # Process each report
        results = {'regenerated': 0, 'skipped': 0, 'errors': 0}

        print(f"\n🚀 Starting regeneration...")
        for i, report in enumerate(reports, 1):
            facilitator = self.facilitator_service.get_facilitator_by_id(report['facilitator_id'])
            facilitator_name = facilitator['name'] if facilitator else 'Unknown'

            print(f"\n[{i}/{len(reports)}] Processing report for {facilitator_name} ({report['month']}/{report['year']})")

            success = self.regenerate_analysis_for_report(report, force_regenerate)

            if success:
                results['regenerated'] += 1
            else:
                results['errors'] += 1

        # Summary
        print(f"\n🎉 Regeneration Complete!")
        print(f"   ✅ Successfully regenerated: {results['regenerated']} reports")
        print(f"   ⚠️  Skipped: {results['skipped']} reports")
        print(f"   ❌ Errors: {results['errors']} reports")

        return results

    def cleanup_temp_directory(self, keep_images: bool = False):
        """
        Clean up temporary directory used for downloaded images.

        Args:
            keep_images: If True, keep the temporary directory and images
        """
        if not keep_images and os.path.exists(self.temp_dir):
            import shutil
            try:
                shutil.rmtree(self.temp_dir)
                print(f"\n🧹 Cleaned up temporary directory: {self.temp_dir}")
            except Exception as e:
                print(f"\n⚠️  Failed to clean up temporary directory: {e}")
        elif keep_images:
            print(f"\n💾 Temporary images saved in: {self.temp_dir}")


def main():
    """Main entry point for the regenerate script."""
    parser = argparse.ArgumentParser(
        description="Regenerate LLM analysis for existing reports using database data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Regenerate all reports missing analysis:
  python regenerate_reports.py

  # Regenerate reports for a specific facilitator:
  python regenerate_reports.py --facilitator-name "John Doe"

  # Regenerate reports for September 2025:
  python regenerate_reports.py --month 9 --year 2025

  # Force regenerate all reports from 2025 (even if analysis exists):
  python regenerate_reports.py --year 2025 --force

  # Regenerate reports for specific facilitator and date:
  python regenerate_reports.py --facilitator-name "Jane Smith" --month 10 --year 2025

  # Keep downloaded images for debugging:
  python regenerate_reports.py --month 9 --year 2025 --keep-images

  # Use specific directory for downloaded images:
  python regenerate_reports.py --temp-dir ./temp_images --keep-images

Note: This script downloads images from S3 to enable full visual analysis.
      Images are temporarily stored locally and cleaned up after processing unless --keep-images is used.
        """
    )

    parser.add_argument(
        '--facilitator-name',
        type=str,
        help='Name of the facilitator to regenerate reports for'
    )

    parser.add_argument(
        '--facilitator-id',
        type=str,
        help='ID of the facilitator to regenerate reports for'
    )

    parser.add_argument(
        '--month',
        type=int,
        choices=range(1, 13),
        help='Month to regenerate reports for (1-12, requires --year)'
    )

    parser.add_argument(
        '--year',
        type=int,
        help='Year to regenerate reports for'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Force regeneration even if analysis already exists'
    )

    parser.add_argument(
        '--temp-dir',
        type=str,
        help='Directory to store temporary downloaded images (default: auto-generated temp dir)'
    )

    parser.add_argument(
        '--keep-images',
        action='store_true',
        help='Keep downloaded images after processing (useful for debugging)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.month is not None and args.year is None:
        parser.error("--month requires --year to be specified")

    if args.facilitator_name and args.facilitator_id:
        parser.error("Cannot specify both --facilitator-name and --facilitator-id")

    try:
        regenerator = ReportRegenerator(temp_dir=args.temp_dir)
        regenerator.regenerate_reports(
            facilitator_name=args.facilitator_name,
            facilitator_id=args.facilitator_id,
            month=args.month,
            year=args.year,
            force_regenerate=args.force
        )
        # Cleanup temporary directory
        regenerator.cleanup_temp_directory(keep_images=args.keep_images)
    except KeyboardInterrupt:
        print("\n\n❌ Regeneration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during regeneration: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()