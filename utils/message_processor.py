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
        filtered_messages: List of filtered message dictionaries

    Returns:
        List of filtered text messages ready for processing
    """
    text_messages = []
    all_messages = safe_messages + filtered_messages

    for msg in all_messages:
        if msg.get('message', '').strip() and not msg.get('has_attachment'):
            message_text = msg['message'].strip()

            # Skip short or administrative messages
            if len(message_text) < MIN_MESSAGE_LENGTH:
                continue

            # Skip administrative messages
            if not any(skip_phrase in message_text.lower() for skip_phrase in ADMINISTRATIVE_SKIP_PHRASES):
                text_messages.append(msg)

    return text_messages


def filter_administrative_messages(messages: List[Dict]) -> List[Dict]:
    """
    Filter out administrative and system messages

    Args:
        messages: List of message dictionaries

    Returns:
        List of filtered messages
    """
    filtered = []

    for msg in messages:
        if msg.get('message', '').strip():
            message_text = msg['message'].strip()

            # Skip short messages
            if len(message_text) < MIN_MESSAGE_LENGTH:
                continue

            # Skip administrative messages
            if not any(skip_phrase in message_text.lower() for skip_phrase in ADMINISTRATIVE_SKIP_PHRASES):
                filtered.append(msg)

    return filtered


def is_administrative_message(message_text: str) -> bool:
    """
    Check if a message is administrative/system generated

    Args:
        message_text: The message text to check

    Returns:
        True if message is administrative, False otherwise
    """
    if not message_text or len(message_text.strip()) < MIN_MESSAGE_LENGTH:
        return True

    return any(skip_phrase in message_text.lower() for skip_phrase in ADMINISTRATIVE_SKIP_PHRASES)


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