#!/usr/bin/env python3
"""
Test script for the improved name anonymizer
"""
import os
import sys
from dotenv import load_dotenv

# Add the parent directory to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from name_anonymizer import NameAnonymizer

def test_anonymization():
    """Test the improved name anonymization function"""
    load_dotenv()

    # Initialize anonymizer directly
    anonymizer = NameAnonymizer()

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
            anonymized = anonymizer.anonymize_text(message, test_facilitator_id)
            print(f"Anonymized: {anonymized}")

            # Check if anonymization occurred
            if message != anonymized:
                print("✅ Names were detected and anonymized")
            else:
                print("ℹ️  No names detected (or no changes needed)")

        except Exception as e:
            print(f"❌ Error: {e}")

    print(f"\n📋 Final name mappings:")
    mappings = anonymizer.get_mappings_for_facilitator(test_facilitator_id)
    for original, alternate in mappings.items():
        print(f"   {original} → {alternate}")

    print(f"\nTotal names mapped: {len(mappings)}")

if __name__ == "__main__":
    test_anonymization()