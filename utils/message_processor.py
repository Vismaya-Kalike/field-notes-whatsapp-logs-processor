"""
Message filtering utilities for WhatsApp data
Handles filtering and preparation of text messages (no database operations)
"""

from typing import List, Dict
from utils.constants import ADMINISTRATIVE_SKIP_PHRASES, MIN_MESSAGE_LENGTH


def filter_text_messages(safe_messages: List[Dict], filtered_messages: List[Dict]) -> List[Dict]:
    """
    Filter text messages to remove administrative messages and prepare for processing

    Args:
        safe_messages: List of safe message dictionaries
        filtered_messages: List of filtered message dictionaries (includes messages with problematic images)

    Returns:
        List of filtered text messages ready for processing
    """
    text_messages = []


    # Process ALL safe messages that have text content (whether they have attachments or not)
    for msg in safe_messages:
        if msg.get('message', '').strip():
            message_text = msg['message'].strip()

            # Only skip short messages
            if len(message_text) >= MIN_MESSAGE_LENGTH:
                text_messages.append(msg)

    # IMPORTANT: Also extract text from ALL filtered messages (whether they have attachments or not)
    # These were filtered for various reasons, but their text content can still be valuable
    for msg in filtered_messages:
        if msg.get('message', '').strip():
            message_text = msg['message'].strip()
            # Only skip short messages
            if len(message_text) >= MIN_MESSAGE_LENGTH:
                text_messages.append(msg)

    return text_messages


def filter_administrative_messages(messages: List[Dict]) -> List[Dict]:
    """
    Filter out short messages (no longer filtering administrative phrases)

    Args:
        messages: List of message dictionaries

    Returns:
        List of filtered messages
    """
    filtered = []

    for msg in messages:
        if msg.get('message', '').strip():
            message_text = msg['message'].strip()

            # Only skip short messages
            if len(message_text) >= MIN_MESSAGE_LENGTH:
                filtered.append(msg)

    return filtered


def is_administrative_message(message_text: str) -> bool:
    """
    Check if a message is too short (no longer checking administrative phrases)

    Args:
        message_text: The message text to check

    Returns:
        True if message is too short, False otherwise
    """
    if not message_text or len(message_text.strip()) < MIN_MESSAGE_LENGTH:
        return True

    return False


def prepare_messages_for_analysis(messages: List[Dict]) -> List[Dict]:
    """
    Prepare messages for analysis by filtering and cleaning

    Args:
        messages: List of message dictionaries

    Returns:
        List of clean messages ready for analysis
    """
    prepared = []

    for msg in messages:
        if msg.get('message', '').strip():
            message_text = msg['message'].strip()

            if not is_administrative_message(message_text):
                # Create clean message dict
                clean_msg = {
                    'text': message_text,
                    'timestamp': msg.get('timestamp'),
                    'username': msg.get('username'),
                    'original_message': msg
                }
                prepared.append(clean_msg)

    return prepared