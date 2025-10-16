#!/usr/bin/env python3
"""
Test script for the improved name anonymizer
"""
import os
import sys
from dotenv import load_dotenv

# Add the parent directory to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import DatabaseManager
from database.child_service import ChildService
from name_anonymizer import NameAnonymizer

def test_anonymization():
    """Test the improved name anonymization function"""
    load_dotenv()

    learning_centre_id = os.getenv("TEST_LEARNING_CENTRE_ID")
    if not learning_centre_id:
        raise ValueError("Set TEST_LEARNING_CENTRE_ID environment variable to a valid learning centre UUID.")

    db_manager = DatabaseManager()
    child_service = ChildService(db_manager)
    anonymizer = NameAnonymizer(child_service)

    # Test cases with various name types
    test_messages = [
        "Aarav did very well in math today. He helped Priya with her homework.",
        "Jo and Anu are good friends. They play together every day.",
        "आज राम और सीता ने अच्छा काम किया।",  # Hindi names
        "Rajesh ಮತ್ತು Lakshmi ತುಂಬಾ ಚೆನ್ನಾಗಿ ಓದುತ್ತಾರೆ",  # Mixed Kannada
        "The children Vikram, Meera, and Dev participated in the story session.",
        "Yesterday was Monday and Today is Tuesday",  # Should not detect any names
    ]

    print("🧪 Testing Improved Name Anonymization")
    print("=" * 60)

    # Use a dummy facilitator ID for testing
    test_facilitator_id = "test-facilitator-123"

    for i, message in enumerate(test_messages, 1):
        print(f"\nTest {i}:")
        print(f"Original: {message}")

        try:
            anonymized = anonymizer.anonymize_text(message, test_facilitator_id, learning_centre_id)
            print(f"Anonymized: {anonymized.text}")

            # Check if anonymization occurred
            if message != anonymized.text:
                print("✅ Names were detected and anonymized")
            else:
                print("ℹ️  No names detected (or no changes needed)")

        except Exception as e:
            print(f"❌ Error: {e}")

    print(f"\n📋 Children recorded for learning centre {learning_centre_id}:")
    children = child_service.get_children_for_learning_centre(learning_centre_id)
    for child in children:
        aliases = ", ".join(child.get("alias") or [])
        print(f"   {child['name']} → {aliases}")

    print(f"\nTotal children stored: {len(children)}")

if __name__ == "__main__":
    test_anonymization()
