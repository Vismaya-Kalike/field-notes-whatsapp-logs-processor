"""
Image Processor for educational field reports
Handles image processing, database storage, and S3 integration
"""

import os
import base64
from typing import List, Dict, Optional
from image_processor.s3_uploader import S3ImageUploader
from image_processor.constants import SUPPORTED_IMAGE_EXTENSIONS


class ImageProcessor:
    """
    Main image processing class that handles the complete image workflow
    """

    def __init__(self, s3_uploader: S3ImageUploader, name_anonymizer):
        """
        Initialize image processor

        Args:
            s3_uploader: S3ImageUploader instance
            name_anonymizer: NameAnonymizer instance for caption anonymization
        """
        self.s3_uploader = s3_uploader
        self.name_anonymizer = name_anonymizer

    def encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """
        Encode image to base64 for OpenAI API

        Args:
            image_path: Path to the image file

        Returns:
            Base64 encoded image string, or None if encoding failed
        """
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Error encoding image {image_path}: {e}")
            return None

    def process_images(self, safe_messages: List[Dict], media_dir: str,
                       facilitator_name: str, month: int, year: int,
                       facilitator_id: str) -> List[Dict]:
        """
        Process safe images, upload to S3, and anonymize captions
        NO database operations - returns data for storage elsewhere

        Args:
            safe_messages: List of safe message dictionaries
            media_dir: Directory containing media files
            facilitator_name: Name of the facilitator
            month: Month of the report
            year: Year of the report
            facilitator_id: ID of the facilitator

        Returns:
            List of processed image dictionaries ready for database storage
        """
        processed_images = []

        for msg in safe_messages:
            if msg.get('has_attachment') and msg.get('attachment_filename'):
                filename = msg['attachment_filename']

                # Check if it's a supported image format
                if self.s3_uploader.is_supported_image(filename):
                    source_path = os.path.join(media_dir, filename)

                    if os.path.exists(source_path):
                        # Generate S3 key
                        s3_key = self.s3_uploader.generate_s3_key(
                            year, month, facilitator_name, filename)

                        # Upload to S3
                        photo_url = self.s3_uploader.upload_image(source_path, s3_key)

                        if photo_url:
                            # Anonymize caption if it exists
                            original_caption = msg.get('message', '')
                            anonymized_caption = self.name_anonymizer.anonymize_text(
                                original_caption, facilitator_id) if original_caption else ''

                            processed_images.append({
                                'filename': filename,
                                'photo_url': photo_url,
                                'caption': anonymized_caption,
                                'timestamp': msg['timestamp'],
                                'local_path': source_path,  # Keep local path for LLM analysis
                                'sent_at': msg['timestamp']  # For database storage
                            })

                            print(f"   📸 Uploaded image: {filename}")

        return processed_images

    def get_supported_extensions(self) -> set:
        """
        Get the set of supported image file extensions

        Returns:
            Set of supported file extensions
        """
        return SUPPORTED_IMAGE_EXTENSIONS