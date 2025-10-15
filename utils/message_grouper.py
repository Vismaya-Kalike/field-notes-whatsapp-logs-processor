from typing import List, Dict, Any

def group_messages_by_sender(messages: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group messages by sender username.

    Args:
        messages (List[Dict]): List of message dictionaries from extract_messages_by_month
                              Each message should have keys: timestamp, username, message,
                              has_attachment, attachment_filename

    Returns:
        Dict[str, List[Dict]]: Dictionary where keys are usernames and values are lists
                              of messages from that user
    """
    sender_groups = {}

    for message in messages:
        username = message['username']

        # Initialize list for this sender if not exists
        if username not in sender_groups:
            sender_groups[username] = []

        # Add message to sender's list
        sender_groups[username].append(message)

    return sender_groups

def get_sender_statistics(sender_groups: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    """
    Generate statistics for each sender.

    Args:
        sender_groups (Dict): Dictionary from group_messages_by_sender

    Returns:
        Dict[str, Dict]: Dictionary with sender statistics including:
                        - message_count: total messages
                        - attachment_count: total attachments
                        - first_message_time: earliest message timestamp
                        - last_message_time: latest message timestamp
                        - avg_messages_per_day: average messages per day
    """
    stats = {}

    for username, messages in sender_groups.items():
        if not messages:
            continue

        # Sort messages by timestamp to get first and last
        sorted_messages = sorted(messages, key=lambda x: x['timestamp'])

        # Count attachments
        attachment_count = sum(1 for msg in messages if msg['has_attachment'])

        # Calculate time span
        first_msg_time = sorted_messages[0]['timestamp']
        last_msg_time = sorted_messages[-1]['timestamp']
        time_span = (last_msg_time - first_msg_time).days + 1  # +1 to include both start and end days

        # Calculate average messages per day
        avg_per_day = len(messages) / max(time_span, 1)  # Avoid division by zero

        stats[username] = {
            'message_count': len(messages),
            'attachment_count': attachment_count,
            'first_message_time': first_msg_time,
            'last_message_time': last_msg_time,
            'time_span_days': time_span,
            'avg_messages_per_day': round(avg_per_day, 2)
        }

    return stats

def print_sender_summary(sender_groups: Dict[str, List[Dict[str, Any]]], top_n: int = 10) -> None:
    """
    Print a summary of top senders.

    Args:
        sender_groups (Dict): Dictionary from group_messages_by_sender
        top_n (int): Number of top senders to display
    """
    # Sort senders by message count
    sorted_senders = sorted(sender_groups.items(), key=lambda x: len(x[1]), reverse=True)

    print(f"Top {top_n} most active senders:")
    print("-" * 60)

    for i, (username, messages) in enumerate(sorted_senders[:top_n], 1):
        attachment_count = sum(1 for msg in messages if msg['has_attachment'])
        print(f"{i:2d}. {username}")
        print(f"    Messages: {len(messages)}")
        print(f"    Attachments: {attachment_count}")
        print()

def get_messages_for_sender(sender_groups: Dict[str, List[Dict[str, Any]]], username: str) -> List[Dict[str, Any]]:
    """
    Get all messages for a specific sender.

    Args:
        sender_groups (Dict): Dictionary from group_messages_by_sender
        username (str): Username to get messages for

    Returns:
        List[Dict]: List of messages from that sender, sorted by timestamp
    """
    if username not in sender_groups:
        return []

    # Return messages sorted by timestamp
    return sorted(sender_groups[username], key=lambda x: x['timestamp'])

# Example usage
if __name__ == "__main__":
    from message_date_filter import extract_messages_by_month

    # Extract messages from July 2025
    file_path = "whatsapp_data/_chat.txt"
    messages = extract_messages_by_month(file_path, month=7, year=2025)

    # Group by sender
    sender_groups = group_messages_by_sender(messages)

    print(f"Found {len(sender_groups)} unique senders")
    print()

    # Print summary
    print_sender_summary(sender_groups)

    # Get statistics
    stats = get_sender_statistics(sender_groups)

    # Show detailed stats for top 3 senders
    print("\nDetailed statistics for top 3 senders:")
    print("=" * 70)

    top_senders = sorted(stats.items(), key=lambda x: x[1]['message_count'], reverse=True)[:3]

    for username, stat in top_senders:
        print(f"\n{username}:")
        print(f"  Total messages: {stat['message_count']}")
        print(f"  Total attachments: {stat['attachment_count']}")
        print(f"  First message: {stat['first_message_time']}")
        print(f"  Last message: {stat['last_message_time']}")
        print(f"  Active for: {stat['time_span_days']} days")
        print(f"  Average messages/day: {stat['avg_messages_per_day']}")

    # Example: Get messages for a specific sender
    if sender_groups:
        top_sender = max(sender_groups.keys(), key=lambda x: len(sender_groups[x]))
        user_messages = get_messages_for_sender(sender_groups, top_sender)
        print(f"\nFirst 3 messages from {top_sender}:")
        for i, msg in enumerate(user_messages[:3], 1):
            print(f"  {i}. [{msg['timestamp']}]: {msg['message'][:50]}...")
            if msg['has_attachment']:
                print(f"     📎 {msg['attachment_filename']}")