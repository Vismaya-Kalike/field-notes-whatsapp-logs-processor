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
from typing import List, Dict, Any, Optional, Set
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
from database.child_service import ChildService
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


class UserAbortError(Exception):
    """Raised when the operator cancels processing after anonymization review."""


class WhatsAppDatabaseProcessor:
    def __init__(self):
        """Initialize the processor with database and S3 connections."""
        # Initialize database manager
        self.db_manager = DatabaseManager()

        # Initialize database services
        self.facilitator_service = FacilitatorService(self.db_manager)
        self.child_service = ChildService(self.db_manager)
        self.report_service = ReportService(self.db_manager)
        self.image_service = ImageService(self.db_manager)
        self.message_service = MessageService(
            self.db_manager, self.child_service)
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
        self.name_anonymizer = NameAnonymizer(self.child_service)

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

    def create_generated_report(self, facilitator_id: str, learning_centre_id: str,
                                month: int, year: int) -> str:
        """Create a new generated report and return its ID."""
        return self.report_service.create_report(
            facilitator_id, learning_centre_id, month, year,
            has_llm_analysis=False
        )

    def process_text_messages(self, safe_messages: List[Dict], filtered_messages: List[Dict],
                              facilitator_id: str, learning_centre_id: str) -> List[Dict]:
        """Process text messages, filter administrative messages, anonymize names, and store in database."""
        processed_messages = []

        # Use utility function to filter text messages
        text_messages = filter_text_messages(safe_messages, filtered_messages)

        # Snapshot existing children before any anonymization induces creations.
        existing_children = self.child_service.get_children_for_learning_centre(learning_centre_id)
        existing_child_ids: Set[str] = {child["id"] for child in existing_children}

        # Prepare batch data for database storage (deferred until confirmation)
        message_batch = []
        message_children: List[List[Dict[str, str]]] = []

        for msg in text_messages:
            message_text = msg['message'].strip()

            # Anonymize children's names in the message
            anonymization_result = self.name_anonymizer.anonymize_text(
                message_text, facilitator_id, learning_centre_id)

            # Add to batch for database storage
            message_batch.append({
                'facilitator_id': facilitator_id,
                'learning_centre_id': learning_centre_id,
                'text': anonymization_result.text,
                'sent_at': msg['timestamp']
            })
            message_children.append(anonymization_result.children)

            processed_messages.append({
                'text': anonymization_result.text,
                'timestamp': msg['timestamp'],
                'children': anonymization_result.children
            })

        if not message_batch:
            return processed_messages

        # Determine which child records were created during anonymization.
        updated_children = self.child_service.get_children_for_learning_centre(learning_centre_id)
        updated_children_lookup = {child["id"]: child for child in updated_children}
        new_child_ids = {child_id for child_id in updated_children_lookup if child_id not in existing_child_ids}

        if new_child_ids:
            print("   🧒 Newly created child records detected during anonymization:")
            for child_id in new_child_ids:
                child_info = updated_children_lookup[child_id]
                alias_preview = ", ".join(child_info.get("alias") or []) or "no aliases"
                source_entry = next(
                    (
                        child
                        for payload in message_children
                        for child in payload
                        if child.get("id") == child_id
                    ),
                    None,
                )
                original_name = source_entry.get("name") if source_entry else child_info.get("name")
                alias_name = source_entry.get("alias") if source_entry else alias_preview
                print(
                    f"      • {original_name or 'Unknown name'} -> alias '{alias_name}' "
                    f"(child_id={child_id})"
                )
        else:
            print("   ℹ️  No new child records created during anonymization.")

        try:
            confirmation = input("   ❓ Continue storing anonymized messages and links? [y/N]: ").strip().lower()
        except EOFError:
            confirmation = ""

        if confirmation not in ("y", "yes"):
            if new_child_ids:
                print("   🧹 Removing newly created child records...")
                self.child_service.delete_children_by_ids(list(new_child_ids))
            print("   ⏹️  Operation cancelled by user after anonymization review.")
            raise UserAbortError("User aborted after reviewing anonymized names.")

        # Store messages in batch
        if message_batch:
            field_note_ids = self.message_service.store_messages_batch(
                message_batch)
            print(
                f"   💬 Processed {len(field_note_ids)} text messages (anonymized)")

            # Link children to the newly created field notes
            for field_note_id, children in zip(field_note_ids, message_children):
                for child in children:
                    self.child_service.link_child_to_field_note(
                        child['id'], field_note_id)

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

                learning_centre_id = self.get_facilitator_learning_centre(
                    facilitator_id)
                if not learning_centre_id:
                    print(
                        f"   ⚠️  No learning centre linked to facilitator {facilitator_id}, skipping...")
                    results['skipped_reports'].append({
                        'sender': sender_name,
                        'reason': 'No linked learning centre'
                    })
                    continue

                # Step 5: Run face detection filter
                print("   🔍 Running face detection filter...")

                # Show initial counts
                initial_attachments = len(
                    [m for m in sender_messages if m.get('has_attachment')])
                initial_total = len(sender_messages)
                print(
                    f"      📊 Initial counts - Total messages: {initial_total}, Messages with attachments: {initial_attachments}")

                safe_messages, filtered_messages, analysis_report = filter_messages_by_privacy(
                    sender_messages, media_dir, strict_mode=False, ultra_conservative=True
                )

                print(
                    f"      🔍 After privacy filter - Safe: {len(safe_messages)}, Filtered: {len(filtered_messages)}")
                if analysis_report.get('filtering_reasons'):
                    for reason, count in analysis_report['filtering_reasons'].items():
                        print(f"         • {reason}: {count}")

                # Step 6: Process images first to get accurate count
                print("   📸 Processing images...")
                safe_images = self.image_processor.process_images(
                    safe_messages, media_dir, sender_name, month, year,
                    facilitator_id, learning_centre_id
                )
                actual_images_count = len(safe_images)

                # Step 7: Get text messages count (without storing yet)
                print("   💬 Counting text messages...")
                from utils.message_processor import filter_text_messages
                text_messages_preview = filter_text_messages(
                    safe_messages, filtered_messages)
                actual_messages_count = len(text_messages_preview)

                # Step 8: Create generated report with accurate counts
                print("   📝 Creating generated report...")
                print(
                    f"      📊 Final counts - Images: {actual_images_count}, Messages: {actual_messages_count}")
                report_id = self.create_generated_report(
                    facilitator_id, learning_centre_id, month, year
                )

                # Step 9: Store images in database
                if safe_images:
                    image_batch = []
                    for img in safe_images:
                        image_batch.append({
                            'facilitator_id': facilitator_id,
                            'learning_centre_id': learning_centre_id,
                            'photo_url': img['photo_url'],
                            'caption': img['caption'],
                            'sent_at': img['sent_at']
                        })

                    stored_images = self.image_service.store_images_batch(
                        image_batch)
                    print(f"   📸 Stored {stored_images} images in database")

                # Step 10: Process and store text messages
                print("   💬 Processing and storing text messages...")
                try:
                    text_messages = self.process_text_messages(
                        safe_messages, filtered_messages, facilitator_id, learning_centre_id
                    )
                except UserAbortError as abort_exc:
                    print(f"   ⏹️  {abort_exc}")
                    if safe_images:
                        removed = self.image_service.delete_images_by_report(report_id)
                        if removed:
                            print(f"   🧹 Removed {removed} images linked to the aborted report.")
                    self.report_service.delete_report(report_id)
                    results['skipped_reports'].append({
                        'sender': sender_name,
                        'reason': 'User aborted after anonymization review'
                    })
                    continue

                mentioned_child_ids = {
                    child['id']
                    for entry in text_messages
                    for child in entry.get('children', [])
                }

                # Step 11: Check if LLM analysis is viable and generate if so
                print("   🤖 Checking if LLM analysis is viable...")
                if self.llm_analyzer.is_analysis_viable(safe_images, text_messages):
                    print("   🤖 Generating LLM analysis with visual content...")
                    llm_analysis = self.llm_analyzer.generate_comprehensive_analysis(
                        sender_name, safe_images, text_messages)

                    if llm_analysis:
                        # Store analysis using analysis service
                        analysis_stored = self.analysis_service.store_analysis(
                            report_id, llm_analysis)
                        if analysis_stored:
                            # Update report to indicate analysis is available
                            self.report_service.update_report_analysis_status(
                                report_id, True)
                            print("   ✅ LLM analysis with images stored")
                        else:
                            print("   ⚠️  Failed to store LLM analysis")
                    else:
                        print("   ⚠️  LLM analysis generation failed")
                        llm_analysis = None
                else:
                    print(
                        "   ⏭️  Skipping LLM analysis - insufficient meaningful content")
                    llm_analysis = None

                results['processed_reports'].append({
                    'sender': sender_name,
                    'facilitator_id': facilitator_id,
                    'learning_centre_id': learning_centre_id,
                    'report_id': report_id,
                    'images_count': len(safe_images),
                    'messages_count': len(text_messages),
                    'children_count': len(mentioned_child_ids),
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
