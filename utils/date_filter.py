import re
from datetime import datetime
from utils.constants import DATE_FORMATS, DEFAULT_TIMEZONE
from typing import List, Dict, Any

def extract_messages_by_month(file_path: str, month: int, year: int) -> List[Dict[str, Any]]:
    """
    Extract all WhatsApp messages from a specific month and year.

    Args:
        file_path (str): Path to the WhatsApp chat txt file
        month (int): Month (1-12)
        year (int): Year (e.g., 2025)

    Returns:
        List[Dict]: List of message dictionaries with keys:
            - timestamp: datetime object
            - username: sender name
            - message: message content
            - has_attachment: boolean
            - attachment_filename: filename if attachment exists
    """
    messages = []

    # Pattern to match newer WhatsApp format: DD/MM/YY, HH:MM - Username: Message
    new_message_pattern = r'(\d{2}/\d{2}/\d{2}), (\d{2}:\d{2}) - ([^:]+): ?(.*)'

    # Pattern to match older WhatsApp format: [M/D/YY, H:MM:SS AM/PM] Username: Message
    # Note: WhatsApp uses special Unicode characters like \u202f (narrow no-break space) and \u200e (left-to-right mark)
    old_message_pattern = r'(?:\u200e)?\[(\d{1,2}/\d{1,2}/\d{2}), (\d{1,2}:\d{2}:\d{2}[\u202f\s](?:AM|PM))\] ([^:]+): (?:\u200e)?(.*)'

    # Pattern to match attachments (including Unicode characters)
    attachment_pattern = r'(.+\.(?:jpg|jpeg|png|gif|webp|mp4|mov|avi|webm|mp3|wav|ogg|m4a|opus|pdf|doc|docx)) \(file attached\)'

    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    current_message = None
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Skip system messages and empty lines
        if not line or 'Messages and calls are end-to-end encrypted' in line or 'added' in line or 'created group' in line or 'changed this group' in line:
            i += 1
            continue

        # Try new format first (DD/MM/YY, HH:MM)
        match = re.match(new_message_pattern, line)
        if match:
            date_str, time_str, username, message_content = match.groups()

            # Parse the date
            try:
                # New WhatsApp format: DD/MM/YY HH:MM (24-hour format)
                full_datetime_str = f"{date_str} {time_str}"
                timestamp = datetime.strptime(full_datetime_str, '%d/%m/%y %H:%M')

                # Handle 2-digit year: assume 20XX for years 00-99
                if timestamp.year < 2000:
                    timestamp = timestamp.replace(year=timestamp.year + 100)

                # Check if this message is from the requested month/year
                if timestamp.month == month and timestamp.year == year:
                    # Collect continuation lines for this message
                    full_message_content = message_content
                    j = i + 1

                    # Look ahead for continuation lines (lines that don't start with timestamp)
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if not next_line:
                            j += 1
                            continue

                        # Check if next line is a new message (has timestamp pattern)
                        if (re.match(new_message_pattern, next_line) or
                            re.match(old_message_pattern, next_line)):
                            break

                        # This is a continuation line, add it to the message
                        full_message_content += " " + next_line
                        j += 1

                    # Update iterator to skip processed continuation lines
                    i = j - 1

                    # Check for attachments in the full message content
                    attachment_match = re.search(attachment_pattern, full_message_content)
                    has_attachment = bool(attachment_match)
                    attachment_filename = attachment_match.group(1) if attachment_match else None

                    # Clean up the message content (remove attachment markers)
                    clean_message = re.sub(attachment_pattern, '', full_message_content).strip()

                    # Clean up username (remove phone numbers, keep readable names)
                    clean_username = username.strip()

                    message_dict = {
                        'timestamp': timestamp,
                        'username': clean_username,
                        'message': clean_message,
                        'has_attachment': has_attachment,
                        'attachment_filename': attachment_filename
                    }

                    messages.append(message_dict)

            except ValueError:
                # Skip lines that don't match the expected date format
                pass

        else:
            # Try old format ([M/D/YY, H:MM:SS AM/PM])
            match = re.match(old_message_pattern, line)
            if match:
                date_str, time_str, username, message_content = match.groups()

                # Parse the date
                try:
                    # Old WhatsApp format: M/D/YY with special Unicode characters
                    # Clean up the time string by replacing Unicode characters with regular space
                    clean_time_str = time_str.replace('\u202f', ' ')
                    full_datetime_str = f"{date_str} {clean_time_str}"
                    timestamp = datetime.strptime(full_datetime_str, '%m/%d/%y %I:%M:%S %p')

                    # Handle 2-digit year: assume 20XX for years 00-99
                    if timestamp.year < 2000:
                        timestamp = timestamp.replace(year=timestamp.year + 100)

                    # Check if this message is from the requested month/year
                    if timestamp.month == month and timestamp.year == year:
                        # Collect continuation lines for this message
                        full_message_content = message_content
                        j = i + 1

                        # Look ahead for continuation lines (lines that don't start with timestamp)
                        while j < len(lines):
                            next_line = lines[j].strip()
                            if not next_line:
                                j += 1
                                continue

                            # Check if next line is a new message (has timestamp pattern)
                            if (re.match(new_message_pattern, next_line) or
                                re.match(old_message_pattern, next_line)):
                                break

                            # This is a continuation line, add it to the message
                            full_message_content += " " + next_line
                            j += 1

                        # Update iterator to skip processed continuation lines
                        i = j - 1

                        # Check for attachments
                        old_attachment_pattern = r'(?:\u200e)?<attached: ([^>]+)>'
                        attachment_match = re.search(old_attachment_pattern, full_message_content)
                        has_attachment = bool(attachment_match)
                        attachment_filename = attachment_match.group(1) if attachment_match else None

                        # Clean up the message content (remove attachment markers)
                        clean_message = re.sub(old_attachment_pattern, '', full_message_content).strip()

                        # Clean up username (remove Unicode characters)
                        clean_username = username.replace('\u202f', ' ').strip()

                        message_dict = {
                            'timestamp': timestamp,
                            'username': clean_username,
                            'message': clean_message,
                            'has_attachment': has_attachment,
                            'attachment_filename': attachment_filename
                        }

                        messages.append(message_dict)

                except ValueError:
                    # Skip lines that don't match the expected date format
                    pass

        # Move to next line
        i += 1

    # Sort messages by timestamp
    messages.sort(key=lambda x: x['timestamp'])

    return messages

def print_messages_summary(messages: List[Dict[str, Any]]) -> None:
    """
    Print a summary of the extracted messages.

    Args:
        messages (List[Dict]): List of message dictionaries
    """
    print(f"Found {len(messages)} messages")

    if messages:
        print(f"Date range: {messages[0]['timestamp'].date()} to {messages[-1]['timestamp'].date()}")

        # Count messages by user
        user_counts = {}
        attachment_count = 0

        for msg in messages:
            user = msg['username']
            user_counts[user] = user_counts.get(user, 0) + 1
            if msg['has_attachment']:
                attachment_count += 1

        print(f"Total attachments: {attachment_count}")
        print("\nMessages by user:")
        for user, count in sorted(user_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {user}: {count} messages")

# Example usage
if __name__ == "__main__":
    # Example: Extract all messages from July 2025
    file_path = "whatsapp_data/WhatsApp Chat with SAKHI VK.txt"
    messages = extract_messages_by_month(file_path, month=7, year=2025)

    print_messages_summary(messages)

    # Print first few messages as examples
    print("\nFirst 5 messages:")
    for i, msg in enumerate(messages[:5]):
        print(f"{i+1}. [{msg['timestamp']}] {msg['username']}: {msg['message']}")
        if msg['has_attachment']:
            print(f"   📎 Attachment: {msg['attachment_filename']}")