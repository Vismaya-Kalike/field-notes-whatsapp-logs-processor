"""
Name Anonymizer for Educational Field Reports
Handles detection and anonymization of children's names using AI
"""

import json
import os
import re
from typing import Dict, Optional
from openai import OpenAI

from anonymizer.constants import (
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_MAX_COMPLETION_TOKENS,
    OPENAI_TIMEOUT,
    NAME_MAPPING_FILE
)
from anonymizer.prompts import get_name_detection_prompt


class NameAnonymizer:
    """
    Handles anonymization of children's names in educational content
    """

    def __init__(self, mapping_file_path: Optional[str] = None):
        """
        Initialize the name anonymizer

        Args:
            mapping_file_path: Custom path for the mapping file. If None, uses default.
        """
        self.name_mapping_file = mapping_file_path or NAME_MAPPING_FILE
        self.name_mappings = self.load_name_mappings()

        print(f"Loaded {len(self.name_mappings)} existing name mappings")

    def load_name_mappings(self) -> Dict[str, Dict[str, str]]:
        """Load existing name mappings from JSON file"""
        if os.path.exists(self.name_mapping_file):
            try:
                with open(self.name_mapping_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                print(f"Warning: Could not load mappings from {self.name_mapping_file}")
                return {}
        return {}

    def save_name_mappings(self):
        """Save current name mappings to JSON file"""
        try:
            with open(self.name_mapping_file, 'w', encoding='utf-8') as f:
                json.dump(self.name_mappings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning: Could not save mappings to {self.name_mapping_file}: {e}")

    def get_facilitator_mapping_key(self, facilitator_id: str) -> str:
        """Generate a mapping key for a facilitator"""
        return f"facilitator_{facilitator_id}"

    def generate_alternate_names(self, text: str, facilitator_id: str) -> Dict[str, str]:
        """
        Use AI to detect names in text and generate appropriate alternates

        Args:
            text: Text to analyze for names
            facilitator_id: ID of the facilitator (for context)

        Returns:
            Dictionary mapping original names to alternate names
        """
        if not text or not text.strip():
            return {}

        try:
            client = OpenAI()
            prompt = get_name_detection_prompt(text)

            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=OPENAI_TEMPERATURE,
                max_completion_tokens=OPENAI_MAX_COMPLETION_TOKENS,
                timeout=OPENAI_TIMEOUT
            )

            response_text = response.choices[0].message.content.strip()

            # Try to parse JSON response
            try:
                name_mapping = json.loads(response_text)
                if isinstance(name_mapping, dict):
                    return name_mapping
                else:
                    print(f"Warning: AI response is not a dictionary: {response_text}")
                    return {}
            except json.JSONDecodeError:
                print(f"Warning: Could not parse AI response as JSON:")
                print(f"Response: {response_text[:500]}...")  # Show first 500 chars

                # Try to extract JSON from response if it contains extra text
                try:
                    # Look for JSON object in the response
                    import re
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group()
                        name_mapping = json.loads(json_str)
                        if isinstance(name_mapping, dict):
                            print("Successfully extracted JSON from response")
                            return name_mapping
                except:
                    pass

                print("Could not extract valid JSON, returning empty mapping")
                return {}

        except Exception as e:
            print(f"Error generating alternate names: {e}")
            return {}

    def anonymize_text(self, text: str, facilitator_id: str) -> str:
        """
        Anonymize children's names in text using AI-only detection and existing mappings

        Args:
            text: Text to anonymize
            facilitator_id: ID of the facilitator for mapping context

        Returns:
            Text with names anonymized
        """
        if not text or not text.strip():
            return text

        facilitator_key = self.get_facilitator_mapping_key(facilitator_id)

        # Get existing mappings for this facilitator
        facilitator_mappings = self.name_mappings.get(facilitator_key, {})

        # Start with the original text
        anonymized_text = text

        # Step 1: Apply existing known mappings
        names_already_anonymized = []
        for original_name, alternate_name in facilitator_mappings.items():
            # Use word boundaries to match whole names only
            pattern = r'\b' + re.escape(original_name) + r'\b'
            if re.search(pattern, anonymized_text, re.IGNORECASE):
                anonymized_text = re.sub(
                    pattern, alternate_name, anonymized_text, flags=re.IGNORECASE)
                names_already_anonymized.append(original_name)

        # Step 2: Use AI to detect ALL names in the message (both new and existing)
        # This ensures we catch names we might have missed before
        new_mappings = self.generate_alternate_names(text, facilitator_id)

        if new_mappings:
            # Add new mappings to facilitator's mappings
            if facilitator_key not in self.name_mappings:
                self.name_mappings[facilitator_key] = {}

            new_names_found = []
            for original_name, alternate_name in new_mappings.items():
                # Check if this is a truly new name (not already in our mappings)
                if original_name not in facilitator_mappings:
                    self.name_mappings[facilitator_key][original_name] = alternate_name
                    new_names_found.append(original_name)

                # Apply anonymization (whether new or existing)
                pattern = r'\b' + re.escape(original_name) + r'\b'
                anonymized_text = re.sub(
                    pattern, alternate_name, anonymized_text, flags=re.IGNORECASE)

            # Save updated mappings if we found new names
            if new_names_found:
                self.save_name_mappings()
                print(f"   🔄 Added {len(new_names_found)} new name mappings for facilitator {facilitator_id}")

        return anonymized_text

    def get_mappings_for_facilitator(self, facilitator_id: str) -> Dict[str, str]:
        """
        Get all name mappings for a specific facilitator

        Args:
            facilitator_id: ID of the facilitator

        Returns:
            Dictionary of name mappings for this facilitator
        """
        facilitator_key = self.get_facilitator_mapping_key(facilitator_id)
        return self.name_mappings.get(facilitator_key, {})

    def get_all_mappings(self) -> Dict[str, Dict[str, str]]:
        """
        Get all name mappings

        Returns:
            Complete mapping dictionary organized by facilitator
        """
        return self.name_mappings.copy()

    def clear_mappings(self, facilitator_id: Optional[str] = None):
        """
        Clear name mappings

        Args:
            facilitator_id: If provided, clear only mappings for this facilitator.
                          If None, clear all mappings.
        """
        if facilitator_id:
            facilitator_key = self.get_facilitator_mapping_key(facilitator_id)
            if facilitator_key in self.name_mappings:
                del self.name_mappings[facilitator_key]
                print(f"Cleared mappings for facilitator {facilitator_id}")
        else:
            self.name_mappings.clear()
            print("Cleared all name mappings")

        self.save_name_mappings()