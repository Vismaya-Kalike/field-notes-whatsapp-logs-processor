#!/usr/bin/env python3
"""
WhatsApp Database Processor - Processes WhatsApp messages and stores data in PostgreSQL with S3 integration.
"""

import os
import time
import requests
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from face_detection.privacy_filter import filter_messages_by_privacy
from utils.date_filter import extract_messages_by_month
from utils.message_grouper import group_messages_by_sender
from utils.message_processor import filter_text_messages
from dotenv import load_dotenv
from anonymizer.name_anonymizer import NameAnonymizer
from image_processor.s3_uploader import S3ImageUploader
from image_processor.image_processor import ImageProcessor
from llm_analyzer.llm_analyzer import LLMAnalyzer
from database.connection import DatabaseManager
from database.facilitator_service import FacilitatorService
from database.report_service import ReportService
from database.image_service import ImageService
from database.message_service import MessageService
from database.analysis_service import AnalysisService

load_dotenv()

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("OpenAI library not available. Install with: pip install openai")


class WhatsAppDatabaseProcessor:
    def __init__(self):
        """Initialize the processor with database and S3 connections."""
        # Initialize database manager
        self.db_manager = DatabaseManager()

        # Initialize database services
        self.facilitator_service = FacilitatorService(self.db_manager)
        self.report_service = ReportService(self.db_manager)
        self.image_service = ImageService(self.db_manager)
        self.message_service = MessageService(self.db_manager)
        self.analysis_service = AnalysisService(self.db_manager)

        # S3 configuration
        self.aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.aws_region = os.getenv('AWS_REGION')
        self.s3_bucket = os.getenv('S3_BUCKET_NAME')

        if not all([self.aws_access_key, self.aws_secret_key, self.aws_region, self.s3_bucket]):
            raise ValueError(
                "AWS S3 configuration is incomplete. Check AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, and S3_BUCKET_NAME")

        # Initialize name anonymizer
        self.name_anonymizer = NameAnonymizer()

        # Initialize S3 uploader
        self.s3_uploader = S3ImageUploader(
            self.aws_access_key,
            self.aws_secret_key,
            self.aws_region,
            self.s3_bucket
        )

        # Initialize image processor
        self.image_processor = ImageProcessor(
            self.s3_uploader,
            self.name_anonymizer
        )

        # Initialize LLM analyzer
        self.llm_analyzer = LLMAnalyzer(
            self.image_processor
        )

        print(f"Initialized processor with S3 bucket: {self.s3_bucket}")

    def get_db_connection(self):
        """Create and return a database connection."""
        return self.db_manager.get_connection()


    def find_facilitator_by_sender(self, sender_name: str) -> Optional[str]:
        """
        Find facilitator by matching sender name against name, alias, and contact_number fields.
        Returns facilitator UUID if found, None otherwise.
        """
        return self.facilitator_service.find_facilitator_by_sender(sender_name)

    def get_unmatched_senders(self, sender_groups: Dict[str, List]) -> List[str]:
        """Get list of senders that don't match any facilitator."""
        return self.facilitator_service.get_unmatched_senders(list(sender_groups.keys()))

    def check_existing_report(self, facilitator_id: str, month: int, year: int) -> Optional[str]:
        """Check if a report already exists for the facilitator in the given month/year."""
        return self.report_service.get_existing_report(facilitator_id, month, year)

    def get_facilitator_learning_centre(self, facilitator_id: str) -> Optional[str]:
        """Get the learning centre ID for a facilitator from the junction table."""
        return self.facilitator_service.get_learning_centre_by_facilitator(facilitator_id)

    def create_generated_report(self, facilitator_id: str, month: int, year: int,
                                images_count: int, messages_count: int) -> str:
        """Create a new generated report and return its ID."""
        # Get learning centre from facilitator relationship
        learning_centre_id = self.get_facilitator_learning_centre(facilitator_id)

        if not learning_centre_id:
            # Fallback to default centre if no relationship exists
            learning_centre_id = self.get_or_create_default_centre()
            print(f"   ⚠️  No learning centre found for facilitator, using default centre")

        return self.report_service.create_report(
            facilitator_id, learning_centre_id, month, year,
            images_count, messages_count, has_llm_analysis=False
        )

    def get_or_create_default_centre(self) -> str:
        """Get or create a default learning centre for reports."""
        return self.facilitator_service.create_learning_centre_if_needed("SAKHI VK Default Centre")


    def process_text_messages(self, safe_messages: List[Dict], filtered_messages: List[Dict],
                              report_id: str, facilitator_id: str) -> List[Dict]:
        """Process text messages, filter administrative messages, anonymize names, and store in database."""
        processed_messages = []

        # Use utility function to filter text messages
        text_messages = filter_text_messages(safe_messages, filtered_messages)

        # Prepare batch data for database storage
        message_batch = []

        for msg in text_messages:
            message_text = msg['message'].strip()

            # Anonymize children's names in the message
            anonymized_text = self.name_anonymizer.anonymize_text(
                message_text, facilitator_id)

            # Add to batch for database storage
            message_batch.append({
                'report_id': report_id,
                'text': anonymized_text,
                'sent_at': msg['timestamp']
            })

            processed_messages.append({
                'text': anonymized_text,
                'timestamp': msg['timestamp']
            })

        # Store messages in batch
        if message_batch:
            stored_count = self.message_service.store_messages_batch(message_batch)
            print(f"   💬 Processed {stored_count} text messages (anonymized)")

        return processed_messages


    def process_whatsapp_messages(self, file_path: str, month: int, year: int,
                                  media_dir: str = "whatsapp_data") -> Dict[str, Any]:
        """
        Main function to process WhatsApp messages for a given month and year.
        """
        print(f"🚀 Processing WhatsApp messages for {month}/{year}")
        print("=" * 60)

        # Step 1: Filter messages by month
        print(f"📅 Step 1: Filtering messages for {month}/{year}")
        messages = extract_messages_by_month(file_path, month=month, year=year)
        print(f"   Found {len(messages)} messages")

        # Step 2: Group messages by sender
        print("👥 Step 2: Grouping messages by sender")
        sender_groups = group_messages_by_sender(messages)
        print(f"   Found {len(sender_groups)} unique senders")

        # Step 3: Check for unmatched senders
        print("🔍 Step 3: Checking facilitator matches")
        unmatched_senders = self.get_unmatched_senders(sender_groups)

        if unmatched_senders:
            print(f"⚠️  Found {len(unmatched_senders)} unmatched senders:")
            for sender in unmatched_senders:
                print(f"   - {sender}")
            print("⏰ Waiting 30 seconds to allow cancellation...")
            time.sleep(30)
            print("✅ Continuing with processing...")

        # Step 4-9: Process each sender
        results = {
            'processed_reports': [],
            'skipped_reports': [],
            'errors': []
        }

        for sender_name, sender_messages in sender_groups.items():
            print(
                f"\n👤 Processing: {sender_name} ({len(sender_messages)} messages)")

            try:
                # Find facilitator
                facilitator_id = self.find_facilitator_by_sender(sender_name)
                if not facilitator_id:
                    print(
                        f"   ⚠️  No facilitator found for {sender_name}, skipping...")
                    results['skipped_reports'].append({
                        'sender': sender_name,
                        'reason': 'No matching facilitator'
                    })
                    continue

                # Check for existing report
                existing_report_id = self.check_existing_report(
                    facilitator_id, month, year)
                if existing_report_id:
                    print(
                        f"   ⚠️  Report already exists for {sender_name} in {month}/{year}")
                    print(f"   Report ID: {existing_report_id}")
                    results['skipped_reports'].append({
                        'sender': sender_name,
                        'reason': 'Report already exists',
                        'existing_report_id': existing_report_id
                    })
                    continue

                # Step 5: Run face detection filter
                print("   🔍 Running face detection filter...")

                # Show initial counts
                initial_attachments = len([m for m in sender_messages if m.get('has_attachment')])
                initial_total = len(sender_messages)
                print(f"      📊 Initial counts - Total messages: {initial_total}, Messages with attachments: {initial_attachments}")

                safe_messages, filtered_messages, analysis_report = filter_messages_by_privacy(
                    sender_messages, media_dir, strict_mode=False, ultra_conservative=True
                )

                print(f"      🔍 After privacy filter - Safe: {len(safe_messages)}, Filtered: {len(filtered_messages)}")
                if analysis_report.get('filtering_reasons'):
                    for reason, count in analysis_report['filtering_reasons'].items():
                        print(f"         • {reason}: {count}")

                # Step 6: Process images first to get accurate count
                print("   📸 Processing images...")
                safe_images = self.image_processor.process_images(
                    safe_messages, media_dir, sender_name, month, year, facilitator_id
                )
                actual_images_count = len(safe_images)

                # Step 7: Get text messages count (without storing yet)
                print("   💬 Counting text messages...")
                from utils.message_processor import filter_text_messages
                text_messages_preview = filter_text_messages(safe_messages, filtered_messages)
                actual_messages_count = len(text_messages_preview)

                # Step 8: Create generated report with accurate counts
                print("   📝 Creating generated report...")
                print(f"      📊 Final counts - Images: {actual_images_count}, Messages: {actual_messages_count}")
                report_id = self.create_generated_report(
                    facilitator_id, month, year, actual_images_count, actual_messages_count
                )

                # Step 9: Store images in database
                if safe_images:
                    image_batch = []
                    for img in safe_images:
                        image_batch.append({
                            'report_id': report_id,
                            'photo_url': img['photo_url'],
                            'caption': img['caption'],
                            'sent_at': img['sent_at']
                        })

                    stored_images = self.image_service.store_images_batch(image_batch)
                    print(f"   📸 Stored {stored_images} images in database")

                # Step 10: Process and store text messages
                print("   💬 Processing and storing text messages...")
                text_messages = self.process_text_messages(
                    safe_messages, filtered_messages, report_id, facilitator_id
                )

                # Step 11: Generate LLM analysis with images
                print("   🤖 Generating LLM analysis with visual content...")
                llm_analysis = self.llm_analyzer.generate_comprehensive_analysis(
                    sender_name, safe_images, text_messages)

                if llm_analysis:
                    # Store analysis using analysis service
                    analysis_stored = self.analysis_service.store_analysis(report_id, llm_analysis)
                    if analysis_stored:
                        # Update report to indicate analysis is available
                        self.report_service.update_report_analysis_status(report_id, True)
                        print("   ✅ LLM analysis with images stored")
                    else:
                        print("   ⚠️  Failed to store LLM analysis")
                else:
                    print("   ⚠️  LLM analysis not available")

                results['processed_reports'].append({
                    'sender': sender_name,
                    'facilitator_id': facilitator_id,
                    'report_id': report_id,
                    'images_count': len(safe_images),
                    'messages_count': len(text_messages),
                    'has_llm_analysis': llm_analysis is not None
                })

                print(f"   ✅ Successfully processed {sender_name}")

            except Exception as e:
                print(f"   ❌ Error processing {sender_name}: {str(e)}")
                results['errors'].append({
                    'sender': sender_name,
                    'error': str(e)
                })

        # Summary
        print(f"\n🎉 Processing Complete!")
        print(
            f"   ✅ Successfully processed: {len(results['processed_reports'])} reports")
        print(f"   ⚠️  Skipped: {len(results['skipped_reports'])} reports")
        print(f"   ❌ Errors: {len(results['errors'])} reports")

        return results


# Example usage
if __name__ == "__main__":
    processor = WhatsAppDatabaseProcessor()

    # Process messages for July 2025 - Bangalore Learning Centre Facilitators
    results = processor.process_whatsapp_messages(
        file_path="whatsapp_data_bangalore/WhatsApp Chat with Learning Centre Facilitators.txt",
        month=9,
        year=2025,
        media_dir="whatsapp_data_bangalore"
    )
