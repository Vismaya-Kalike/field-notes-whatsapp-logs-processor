"""
Name Anonymizer for Educational Field Reports.

Stores and retrieves child information from the database so anonymized names are
consistent across reports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

try:
    from openai import OpenAI  # type: ignore
except ImportError:
    OpenAI = None

from anonymizer.constants import (
    OPENAI_MAX_COMPLETION_TOKENS,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    OPENAI_TIMEOUT,
)
from anonymizer.prompts import get_name_detection_prompt

if TYPE_CHECKING:
    from database.child_service import ChildService


@dataclass
class AnonymizedSegment:
    """Result container for anonymized text."""

    text: str
    children: List[Dict[str, str]] = field(default_factory=list)


class NameAnonymizer:
    """
    Handles anonymization of children's names in educational content using the database.
    """

    def __init__(self, child_service: "ChildService"):
        if child_service is None:
            raise ValueError("ChildService instance is required for NameAnonymizer.")
        self.child_service = child_service

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

        if OpenAI is None:
            print("Warning: openai package not available; skipping AI name detection.")
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

    def anonymize_text(
        self,
        text: str,
        facilitator_id: str,
        learning_centre_id: Optional[str],
    ) -> AnonymizedSegment:
        """
        Anonymize children's names in text using AI-only detection and existing mappings

        Args:
            text: Text to anonymize
            facilitator_id: ID of the facilitator for mapping context
            learning_centre_id: Learning centre scope for the child records

        Returns:
            AnonymizedSegment containing the anonymized text and referenced children
        """
        if not text or not text.strip():
            return AnonymizedSegment(text=text, children=[])

        anonymized_text = text
        referenced_children: Dict[str, Dict[str, str]] = {}

        # Step 1: Apply existing mappings from the database.
        if learning_centre_id:
            existing_children = self.child_service.get_children_for_learning_centre(learning_centre_id)
            for child in existing_children:
                aliases = child.get("alias") or []
                if not aliases:
                    continue
                preferred_alias = aliases[0]
                original_name = child["name"]
                pattern = r"\b" + re.escape(original_name) + r"\b"
                if re.search(pattern, anonymized_text, re.IGNORECASE):
                    anonymized_text = re.sub(
                        pattern, preferred_alias, anonymized_text, flags=re.IGNORECASE
                    )
                    referenced_children[child["id"]] = {
                        "id": child["id"],
                        "name": original_name,
                        "alias": preferred_alias,
                    }

        # Step 2: Detect any additional names via AI and persist them.
        new_mappings = self.generate_alternate_names(text, facilitator_id)
        for original_name, alternate_name in new_mappings.items():
            child_id: Optional[str] = None
            preferred_alias = alternate_name
            if learning_centre_id:
                child_record = self.child_service.ensure_child_with_alias(
                    learning_centre_id, original_name, alternate_name
                )
                child_id = child_record["id"]
                preferred_alias = child_record["alias"]
            pattern = r"\b" + re.escape(original_name) + r"\b"
            if re.search(pattern, anonymized_text, re.IGNORECASE):
                anonymized_text = re.sub(
                    pattern, preferred_alias, anonymized_text, flags=re.IGNORECASE
                )

            referenced_children[child_id or original_name] = {
                "id": child_id,
                "name": original_name,
                "alias": preferred_alias,
            }

        return AnonymizedSegment(
            text=anonymized_text,
            children=list(referenced_children.values()),
        )
