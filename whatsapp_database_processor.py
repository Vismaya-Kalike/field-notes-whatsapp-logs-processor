#!/usr/bin/env python3
"""
WhatsApp Database Processor - Processes WhatsApp messages and stores data in PostgreSQL with S3 integration.
"""

import os
import time
import boto3
import psycopg2
import psycopg2.extras
import base64
import requests
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from photo_filter import filter_messages_by_privacy
from message_date_filter import extract_messages_by_month
from group_by_sender import group_messages_by_sender
from dotenv import load_dotenv

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
        # Database configuration
        self.db_url = os.getenv('DATABASE_URL')
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable is required")

        # S3 configuration
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

        # Name anonymization mapping file
        self.name_mapping_file = "name_anonymization_mapping.json"
        self.name_mappings = self.load_name_mappings()

        print(f"Initialized processor with S3 bucket: {self.s3_bucket}")
        print(f"Loaded {len(self.name_mappings)} existing name mappings")

    def get_db_connection(self):
        """Create and return a database connection."""
        return psycopg2.connect(self.db_url)

    def load_name_mappings(self) -> Dict[str, Dict[str, str]]:
        """Load existing name mappings from JSON file."""
        if os.path.exists(self.name_mapping_file):
            try:
                with open(self.name_mapping_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load name mappings: {e}")
                return {}
        return {}

    def save_name_mappings(self):
        """Save name mappings to JSON file."""
        try:
            with open(self.name_mapping_file, 'w', encoding='utf-8') as f:
                json.dump(self.name_mappings, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"Warning: Could not save name mappings: {e}")

    def get_facilitator_mapping_key(self, facilitator_id: str) -> str:
        """Get the mapping key for a facilitator."""
        return f"facilitator_{facilitator_id}"

    def generate_alternate_names(self, text: str, facilitator_id: str) -> Dict[str, str]:
        """
        Use GPT to generate alternate names for children mentioned in the text.
        Returns a mapping of original names to alternate names.
        """
        if not OPENAI_AVAILABLE:
            return {}

        try:
            client = OpenAI()

            prompt = f"""You are helping to anonymize children's names in educational field reports for privacy protection.

            Please analyze the following text and identify any children's names (first names only, not surnames or titles). For each child's name you find, generate an appropriate alternate name that:

            1. Maintains the same gender (if clear from context)
            2. Uses culturally appropriate Indian names
            3. Is different enough to protect privacy
            4. Is suitable for children

            Text to analyze:
            "{text}"

            Respond ONLY with a JSON object where keys are the original names and values are the alternate names. If no children's names are found, respond with an empty JSON object {{}}.

            Example format:
            {{"Aarav": "Arjun", "Priya": "Kavya", "Rohit": "Vikram"}}

            Important: Only include actual children's names, not facilitator names, adult names, or place names."""

            response = client.chat.completions.create(
                model="gpt-5",
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.choices[0].message.content.strip()

            # Try to parse JSON response
            try:
                name_mapping = json.loads(response_text)
                if isinstance(name_mapping, dict):
                    return name_mapping
                else:
                    print(
                        f"Warning: GPT response is not a dictionary: {response_text}")
                    return {}
            except json.JSONDecodeError:
                print(
                    f"Warning: Could not parse GPT response as JSON: {response_text}")
                return {}

        except Exception as e:
            print(f"Error generating alternate names: {e}")
            return {}

    def anonymize_message_text(self, text: str, facilitator_id: str) -> str:
        """
        Anonymize children's names in message text using existing mappings or generating new ones.
        """
        if not text or not text.strip():
            return text

        facilitator_key = self.get_facilitator_mapping_key(facilitator_id)

        # Get existing mappings for this facilitator
        facilitator_mappings = self.name_mappings.get(facilitator_key, {})

        # Check if any existing names are in the text
        anonymized_text = text
        names_found = []

        for original_name, alternate_name in facilitator_mappings.items():
            # Use word boundaries to match whole names only
            pattern = r'\b' + re.escape(original_name) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                anonymized_text = re.sub(
                    pattern, alternate_name, anonymized_text, flags=re.IGNORECASE)
                names_found.append(original_name)

        # If we found existing names, we're done
        if names_found:
            return anonymized_text

        # Otherwise, check if there might be new names to anonymize
        # Look for potential name patterns (capitalized words that aren't common words)
        potential_names = re.findall(r'\b[A-Z][a-z]{2,}\b', text)

        # Common words to exclude (not exhaustive, but covers basic cases)
        common_words = {
            'Today', 'Yesterday', 'Tomorrow', 'Monday', 'Tuesday', 'Wednesday', 'Thursday',
            'Friday', 'Saturday', 'Sunday', 'January', 'February', 'March', 'April', 'May',
            'June', 'July', 'August', 'September', 'October', 'November', 'December',
            'Good', 'Nice', 'Great', 'Happy', 'Sad', 'Beautiful', 'Amazing', 'Wonderful',
            'School', 'Class', 'Teacher', 'Student', 'Book', 'English', 'Math', 'Science',
            'Hindi', 'Kannada', 'Tamil', 'Telugu', 'Malayalam', 'Bengali', 'Gujarati',
            'WhatsApp', 'Message', 'Photo', 'Video', 'Voice', 'Call', 'Group', 'Chat'
        }

        # Filter out common words
        potential_names = [
            name for name in potential_names if name not in common_words]

        # If we have potential names, ask GPT to help identify which are actually children's names
        if potential_names:
            new_mappings = self.generate_alternate_names(text, facilitator_id)

            if new_mappings:
                # Add new mappings to facilitator's mappings
                if facilitator_key not in self.name_mappings:
                    self.name_mappings[facilitator_key] = {}

                for original_name, alternate_name in new_mappings.items():
                    self.name_mappings[facilitator_key][original_name] = alternate_name

                    # Apply the anonymization
                    pattern = r'\b' + re.escape(original_name) + r'\b'
                    anonymized_text = re.sub(
                        pattern, alternate_name, anonymized_text, flags=re.IGNORECASE)

                # Save updated mappings
                self.save_name_mappings()
                print(
                    f"   🔄 Added {len(new_mappings)} new name mappings for facilitator {facilitator_id}")

        return anonymized_text

    def find_facilitator_by_sender(self, sender_name: str) -> Optional[str]:
        """
        Find facilitator by matching sender name against name, alias, and contact_number fields.
        Returns facilitator UUID if found, None otherwise.
        """
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Try exact name match first
                cur.execute(
                    "SELECT id FROM facilitators WHERE name = %s",
                    (sender_name,)
                )
                result = cur.fetchone()
                if result:
                    return result[0]

                # Try alias match (case-insensitive)
                cur.execute(
                    """
                    SELECT id FROM facilitators
                    WHERE %s = ANY(alias) OR LOWER(%s) = ANY(LOWER(alias::text)::text[])
                    """,
                    (sender_name, sender_name)
                )
                result = cur.fetchone()
                if result:
                    return result[0]

                # Try contact number match (in case sender_name is a phone number)
                cur.execute(
                    "SELECT id FROM facilitators WHERE contact_number = %s",
                    (sender_name,)
                )
                result = cur.fetchone()
                if result:
                    return result[0]

                return None

    def get_unmatched_senders(self, sender_groups: Dict[str, List]) -> List[str]:
        """Get list of senders that don't match any facilitator."""
        unmatched = []
        for sender_name in sender_groups.keys():
            if not self.find_facilitator_by_sender(sender_name):
                unmatched.append(sender_name)
        return unmatched

    def check_existing_report(self, facilitator_id: str, month: int, year: int) -> Optional[str]:
        """Check if a report already exists for the facilitator in the given month/year."""
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id FROM generated_reports
                    WHERE facilitator_id = %s AND month = %s AND year = %s
                    """,
                    (facilitator_id, month, year)
                )
                result = cur.fetchone()
                return result[0] if result else None

    def get_facilitator_learning_centre(self, facilitator_id: str) -> Optional[str]:
        """Get the learning centre ID for a facilitator from the junction table."""
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT learning_centre_id
                    FROM learning_centre_facilitators
                    WHERE facilitator_id = %s
                    LIMIT 1
                    """,
                    (facilitator_id,)
                )
                result = cur.fetchone()
                return result[0] if result else None

    def create_generated_report(self, facilitator_id: str, month: int, year: int,
                                images_count: int, messages_count: int) -> str:
        """Create a new generated report and return its ID."""
        # Get learning centre from facilitator relationship
        learning_centre_id = self.get_facilitator_learning_centre(facilitator_id)

        if not learning_centre_id:
            # Fallback to default centre if no relationship exists
            learning_centre_id = self.get_or_create_default_centre()
            print(f"   ⚠️  No learning centre found for facilitator, using default centre")

        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO generated_reports
                    (facilitator_id, learning_centre_id, month, year, images_count, messages_count, has_llm_analysis)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (facilitator_id, learning_centre_id, month,
                     year, images_count, messages_count, False)
                )
                report_id = cur.fetchone()[0]
                conn.commit()
                return report_id

    def get_or_create_default_centre(self) -> str:
        """Get or create a default learning centre for reports."""
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Try to find existing default centre
                cur.execute(
                    "SELECT id FROM learning_centres WHERE centre_name = %s",
                    ("SAKHI VK Default Centre",)
                )
                result = cur.fetchone()
                if result:
                    return result[0]

                # Create default centre
                cur.execute(
                    """
                    INSERT INTO learning_centres
                    (centre_name, area, city, district, state, country, start_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    ("SAKHI VK Default Centre", "Unknown", "Bangalore", "Bangalore Urban",
                     "Karnataka", "India", datetime.now().date())
                )
                centre_id = cur.fetchone()[0]
                conn.commit()
                return centre_id

    def upload_image_to_s3(self, file_path: str, s3_key: str) -> str:
        """Upload image to S3 and return the public URL."""
        try:
            # Determine content type based on file extension
            file_extension = file_path.lower().split('.')[-1]
            if file_extension in ['jpg', 'jpeg']:
                content_type = 'image/jpeg'
            elif file_extension == 'png':
                content_type = 'image/png'
            elif file_extension == 'gif':
                content_type = 'image/gif'
            elif file_extension == 'webp':
                content_type = 'image/webp'
            else:
                content_type = 'image/jpeg'  # default

            # Upload without ACL (bucket must be configured for public access if needed)
            self.s3_client.upload_file(
                file_path,
                self.s3_bucket,
                s3_key,
                ExtraArgs={'ContentType': content_type}
            )
            return f"https://{self.s3_bucket}.s3.{self.aws_region}.amazonaws.com/{s3_key}"
        except Exception as e:
            print(f"Error uploading {file_path} to S3: {e}")
            return None

    def encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """Encode image to base64 for OpenAI API."""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Error encoding image {image_path}: {e}")
            return None

    def process_images(self, safe_messages: List[Dict], filtered_messages: List[Dict],
                       media_dir: str, report_id: str, facilitator_name: str,
                       month: int, year: int, facilitator_id: str) -> List[Dict]:
        """Process safe images, upload to S3, anonymize captions, and store in database."""
        safe_images = []

        for msg in safe_messages:
            if msg.get('has_attachment') and msg.get('attachment_filename'):
                filename = msg['attachment_filename']
                if any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                    source_path = os.path.join(media_dir, filename)

                    if os.path.exists(source_path):
                        # Generate S3 key
                        s3_key = f"reports/{year}/{month:02d}/{facilitator_name.replace(' ', '_')}/{filename}"

                        # Upload to S3
                        photo_url = self.upload_image_to_s3(
                            source_path, s3_key)

                        if photo_url:
                            # Anonymize caption if it exists
                            original_caption = msg.get('message', '')
                            anonymized_caption = self.anonymize_message_text(
                                original_caption, facilitator_id) if original_caption else ''

                            # Store in database with anonymized caption
                            with self.get_db_connection() as conn:
                                with conn.cursor() as cur:
                                    cur.execute(
                                        """
                                        INSERT INTO generated_report_images
                                        (generated_report_id, photo_url, caption, sent_at)
                                        VALUES (%s, %s, %s, %s)
                                        """,
                                        (report_id, photo_url,
                                         anonymized_caption, msg['timestamp'])
                                    )
                                    conn.commit()

                            safe_images.append({
                                'filename': filename,
                                'photo_url': photo_url,
                                'caption': anonymized_caption,
                                'timestamp': msg['timestamp'],
                                'local_path': source_path  # Keep local path for LLM analysis
                            })

                            print(f"   📸 Uploaded image: {filename}")

        return safe_images

    def process_text_messages(self, safe_messages: List[Dict], filtered_messages: List[Dict],
                              report_id: str, facilitator_id: str) -> List[Dict]:
        """Process text messages, filter administrative messages, anonymize names, and store in database."""
        processed_messages = []
        all_messages = safe_messages + filtered_messages

        # Filter out administrative and deleted messages
        skip_phrases = [
            'this message was deleted',
            '<media omitted>',
            'added',
            'created group',
            'changed this group',
            'left',
            'joined',
            'changed the subject',
            'changed their phone number',
            'security code changed'
        ]

        for msg in all_messages:
            if msg.get('message', '').strip() and not msg.get('has_attachment'):
                message_text = msg['message'].strip()

                # Skip administrative messages
                if not any(skip_phrase in message_text.lower() for skip_phrase in skip_phrases):
                    # Anonymize children's names in the message
                    anonymized_text = self.anonymize_message_text(
                        message_text, facilitator_id)

                    # Store anonymized message in database
                    with self.get_db_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                INSERT INTO generated_report_messages
                                (generated_report_id, text, sent_at)
                                VALUES (%s, %s, %s)
                                """,
                                (report_id, anonymized_text, msg['timestamp'])
                            )
                            conn.commit()

                    processed_messages.append({
                        'text': anonymized_text,
                        'timestamp': msg['timestamp']
                    })

        print(
            f"   💬 Processed {len(processed_messages)} text messages (anonymized)")
        return processed_messages

    def generate_llm_analysis_with_images(self, facilitator_name: str, safe_images: List[Dict],
                                          text_messages: List[Dict]) -> Optional[str]:
        """Generate LLM analysis using GPT-5 with both images and text messages."""
        if not OPENAI_AVAILABLE:
            return None

        try:
            client = OpenAI()

            # Prepare field notes for analysis
            field_notes = []
            for msg in text_messages:
                timestamp_str = msg['timestamp'].strftime('%Y-%m-%d %H:%M')
                field_notes.append(f"[{timestamp_str}] {msg['text']}")

            # Prepare messages for the API
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""You are analyzing field reports from a teacher/social worker named {facilitator_name} who works with SAKHI VK, a social service organization in India.

                            CONTEXT: This person shares photos of their work activities, teaching sessions, community outreach, and field notes about their daily work with students and community members. Since facilitators often prefer sending images over text, the visual content is crucial for understanding their work.

                            INSTRUCTIONS:
                            - Analyze both the images and text messages to understand what activities this person is doing
                            - Focus on educational activities, community work, social services, and teaching-related content visible in the images
                            - The images show real field work activities - describe what you see in terms of educational impact
                            - Create a comprehensive field work report based on visual evidence and text notes
                            - Pay special attention to the visual documentation as it's the primary way this facilitator communicates their work

                            TEXT MESSAGES AND FIELD NOTES:
                            {chr(10).join(field_notes) if field_notes else 'Limited text messages - analysis should focus primarily on visual documentation.'}

                            IMAGES PROVIDED: {len(safe_images)} work-related photos showing field activities

                            Based on the visual evidence and text data, please provide a comprehensive field work analysis report covering:

                            1. **Visual Documentation Analysis**: What activities, teaching sessions, and community work are visible in the images?
                            2. **Educational Impact**: What evidence of learning, student engagement, or educational outcomes can you observe?
                            3. **Community Engagement**: How is the facilitator interacting with students, parents, or community members?
                            4. **Work Patterns and Methods**: What teaching methods, materials, or approaches are visible?
                            5. **Overall Assessment**: Based on the visual and text evidence, how would you assess this facilitator's contributions to SAKHI VK's mission?

                            Write this as a professional field work assessment report that recognizes the visual documentation as the primary evidence of the facilitator's work and impact. Also write this as the facilitator would be writing it to the outside world. Don't make up any details and don't add any details that are not in the text messages or images. It's okay if the report is short and doesn't have a lot of details."""
                        }
                    ]
                }
            ]

            # Add images to the message (limit to first 10 images to avoid API limits)
            image_count = 0
            for img_data in safe_images:
                if image_count >= 10:  # GPT-5 has limits on number of images
                    break

                if 'local_path' in img_data and os.path.exists(img_data['local_path']):
                    base64_image = self.encode_image_to_base64(
                        img_data['local_path'])
                    if base64_image:
                        # Determine image type
                        file_extension = img_data['filename'].lower().split(
                            '.')[-1]
                        if file_extension in ['jpg', 'jpeg']:
                            image_type = 'jpeg'
                        elif file_extension == 'png':
                            image_type = 'png'
                        elif file_extension == 'gif':
                            image_type = 'gif'
                        elif file_extension == 'webp':
                            image_type = 'webp'
                        else:
                            image_type = 'jpeg'  # default

                        messages[0]["content"].append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_type};base64,{base64_image}",
                                "detail": "high"
                            }
                        })

                        # Add caption if available
                        if img_data.get('caption'):
                            messages[0]["content"].append({
                                "type": "text",
                                "text": f"Caption for image {image_count + 1}: {img_data['caption']}"
                            })

                        image_count += 1

            if image_count > 0:
                print(
                    f"   🖼️  Sending {image_count} images to GPT-5 for analysis...")

            response = client.chat.completions.create(
                model="gpt-5",
                messages=messages,
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"   ❌ OpenAI API error: {e}")
            # Fallback to text-only analysis if image analysis fails
            return self.generate_text_only_analysis(facilitator_name, safe_images, text_messages)

    def generate_text_only_analysis(self, facilitator_name: str, safe_images: List[Dict],
                                    text_messages: List[Dict]) -> Optional[str]:
        """Fallback text-only analysis if image analysis fails."""
        if not OPENAI_AVAILABLE:
            return None

        try:
            client = OpenAI()

            # Prepare field notes for analysis
            field_notes = []
            for msg in text_messages:
                timestamp_str = msg['timestamp'].strftime('%Y-%m-%d %H:%M')
                field_notes.append(f"[{timestamp_str}] {msg['text']}")

            prompt = f"""You are analyzing field reports from a teacher/social worker named {facilitator_name} who works with SAKHI VK, a social service organization in India.

CONTEXT: This person shares photos of their work activities, teaching sessions, community outreach, and field notes about their daily work with students and community members.

FIELD NOTES AND MESSAGES:
{chr(10).join(field_notes) if field_notes else 'No substantive field notes found in text messages.'}

IMAGES PROVIDED: {len(safe_images)} work-related photos (privacy-filtered, visual analysis not available)

Based on this data, please provide a field work analysis report covering:
1. Educational/teaching activities observed (if any mentioned in text)
2. Community outreach or social service work (if any mentioned)
3. Work patterns and contributions to SAKHI VK organization
4. Impact and activities based on the documentation provided

Write this as a professional field work assessment report focusing on their contributions to education and social services."""

            response = client.chat.completions.create(
                model="gpt-5",
                messages=[{"role": "user", "content": prompt}]
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"   ❌ Fallback analysis also failed: {e}")
            return None

    def store_llm_analysis(self, report_id: str, analysis_text: str):
        """Store LLM analysis in database and update report flag."""
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Store analysis
                cur.execute(
                    """
                    INSERT INTO generated_report_llm_analysis
                    (generated_report_id, text)
                    VALUES (%s, %s)
                    """,
                    (report_id, analysis_text)
                )

                # Update report to indicate LLM analysis is available
                cur.execute(
                    "UPDATE generated_reports SET has_llm_analysis = TRUE WHERE id = %s",
                    (report_id,)
                )

                conn.commit()

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
                safe_messages, filtered_messages, analysis_report = filter_messages_by_privacy(
                    sender_messages, media_dir, strict_mode=False, ultra_conservative=True
                )

                # Count images and messages
                safe_image_count = len(
                    [m for m in safe_messages if m.get('has_attachment')])
                total_messages = len(safe_messages) + len(filtered_messages)

                # Step 6: Create generated report
                print("   📝 Creating generated report...")
                report_id = self.create_generated_report(
                    facilitator_id, month, year, safe_image_count, total_messages
                )

                # Step 7: Process and upload images
                print("   📸 Processing images...")
                safe_images = self.process_images(
                    safe_messages, filtered_messages, media_dir,
                    report_id, sender_name, month, year, facilitator_id
                )

                # Step 8: Process text messages
                print("   💬 Processing text messages...")
                text_messages = self.process_text_messages(
                    safe_messages, filtered_messages, report_id, facilitator_id
                )

                # Step 9: Generate LLM analysis with images
                print("   🤖 Generating GPT-5 analysis with visual content...")
                llm_analysis = self.generate_llm_analysis_with_images(
                    sender_name, safe_images, text_messages)

                if llm_analysis:
                    self.store_llm_analysis(report_id, llm_analysis)
                    print("   ✅ GPT-5 analysis with images stored")
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
