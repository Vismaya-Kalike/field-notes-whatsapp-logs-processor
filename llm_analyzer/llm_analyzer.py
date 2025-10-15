"""
LLM Analyzer for educational field reports
Handles AI-powered analysis of images and text messages
"""

import os
from typing import List, Dict, Optional
from openai import OpenAI

from llm_analyzer.constants import (
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_MAX_COMPLETION_TOKENS,
    OPENAI_TIMEOUT,
    MAX_IMAGES_PER_ANALYSIS,
    MIN_MESSAGES_FOR_ANALYSIS
)
from llm_analyzer.prompts import (
    get_comprehensive_analysis_prompt,
    get_text_only_analysis_prompt,
    format_image_caption
)


class LLMAnalyzer:
    """
    Handles AI-powered analysis of field work images and text messages
    """

    def __init__(self, image_processor):
        """
        Initialize LLM analyzer

        Args:
            image_processor: ImageProcessor instance for base64 encoding
        """
        self.image_processor = image_processor

        # Check if OpenAI is available
        try:
            self.client = OpenAI()
            self.openai_available = True
            print("LLM Analyzer initialized with OpenAI support")
        except Exception as e:
            self.openai_available = False
            print(f"Warning: OpenAI not available - {e}")

    def _prepare_field_notes(self, text_messages: List[Dict]) -> List[str]:
        """
        Prepare field notes from text messages with timestamps

        Args:
            text_messages: List of text message dictionaries

        Returns:
            List of formatted field notes
        """
        field_notes = []
        for msg in text_messages:
            timestamp_str = msg['timestamp'].strftime('%Y-%m-%d %H:%M')
            field_notes.append(f"[{timestamp_str}] {msg['text']}")
        return field_notes

    def _get_image_type_from_filename(self, filename: str) -> str:
        """
        Determine image MIME type from filename

        Args:
            filename: Name of the image file

        Returns:
            Image type string for data URL
        """
        file_extension = filename.lower().split('.')[-1]
        type_map = {
            'jpg': 'jpeg',
            'jpeg': 'jpeg',
            'png': 'png',
            'gif': 'gif',
            'webp': 'webp'
        }
        return type_map.get(file_extension, 'jpeg')

    def _add_images_to_message(self, messages: List[Dict], safe_images: List[Dict]) -> int:
        """
        Add images to the message content for analysis

        Args:
            messages: List of message objects for the API
            safe_images: List of image dictionaries

        Returns:
            Number of images successfully added
        """
        image_count = 0

        for img_data in safe_images:
            if image_count >= MAX_IMAGES_PER_ANALYSIS:
                break

            if 'local_path' in img_data and os.path.exists(img_data['local_path']):
                base64_image = self.image_processor.encode_image_to_base64(
                    img_data['local_path'])

                if base64_image:
                    image_type = self._get_image_type_from_filename(img_data['filename'])

                    messages[0]["content"].append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{image_type};base64,{base64_image}",
                            "detail": "high"
                        }
                    })

                    # Add caption if available
                    if img_data.get('caption'):
                        caption_text = format_image_caption(image_count + 1, img_data['caption'])
                        messages[0]["content"].append({
                            "type": "text",
                            "text": caption_text
                        })

                    image_count += 1

        return image_count

    def generate_comprehensive_analysis(self, facilitator_name: str, safe_images: List[Dict],
                                      text_messages: List[Dict]) -> Optional[str]:
        """
        Generate comprehensive LLM analysis using both images and text messages

        Args:
            facilitator_name: Name of the facilitator
            safe_images: List of image dictionaries
            text_messages: List of text message dictionaries

        Returns:
            Analysis text or None if analysis failed
        """
        if not self.openai_available:
            return None

        try:
            # Prepare field notes
            field_notes = self._prepare_field_notes(text_messages)

            # Create base message with text prompt
            prompt_text = get_comprehensive_analysis_prompt(
                facilitator_name, field_notes, len(safe_images))

            messages = [{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": prompt_text
                }]
            }]

            # Add images to the message
            image_count = self._add_images_to_message(messages, safe_images)

            if image_count > 0:
                print(f"   🖼️  Sending {image_count} images to {OPENAI_MODEL} for analysis...")

            # Make API call
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=OPENAI_TEMPERATURE,
                max_completion_tokens=OPENAI_MAX_COMPLETION_TOKENS,
                timeout=OPENAI_TIMEOUT
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"   ❌ OpenAI API error: {e}")
            # Fallback to text-only analysis
            return self.generate_text_only_analysis(facilitator_name, safe_images, text_messages)

    def generate_text_only_analysis(self, facilitator_name: str, safe_images: List[Dict],
                                   text_messages: List[Dict]) -> Optional[str]:
        """
        Generate fallback text-only analysis if image analysis fails

        Args:
            facilitator_name: Name of the facilitator
            safe_images: List of image dictionaries (for count)
            text_messages: List of text message dictionaries

        Returns:
            Analysis text or None if analysis failed
        """
        if not self.openai_available:
            return None

        try:
            # Prepare field notes
            field_notes = self._prepare_field_notes(text_messages)

            # Generate text-only prompt
            prompt = get_text_only_analysis_prompt(
                facilitator_name, field_notes, len(safe_images))

            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=OPENAI_TEMPERATURE,
                max_completion_tokens=OPENAI_MAX_COMPLETION_TOKENS,
                timeout=OPENAI_TIMEOUT
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"   ❌ Fallback analysis also failed: {e}")
            return None


    def is_analysis_viable(self, safe_images: List[Dict], text_messages: List[Dict]) -> bool:
        """
        Check if there's enough content for meaningful analysis

        Args:
            safe_images: List of image dictionaries
            text_messages: List of text message dictionaries

        Returns:
            True if analysis is viable, False otherwise
        """
        # Check if we have images or sufficient text messages
        has_images = len(safe_images) > 0
        has_sufficient_text = len(text_messages) >= MIN_MESSAGES_FOR_ANALYSIS

        return has_images or has_sufficient_text

    def get_analysis_summary(self, safe_images: List[Dict], text_messages: List[Dict]) -> Dict[str, int]:
        """
        Get a summary of content available for analysis

        Args:
            safe_images: List of image dictionaries
            text_messages: List of text message dictionaries

        Returns:
            Dictionary with content counts
        """
        return {
            'images': len(safe_images),
            'text_messages': len(text_messages),
            'images_for_analysis': min(len(safe_images), MAX_IMAGES_PER_ANALYSIS),
            'viable': self.is_analysis_viable(safe_images, text_messages)
        }