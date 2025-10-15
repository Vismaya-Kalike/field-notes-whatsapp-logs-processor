"""
Constants for utility functions
"""

# Message Processing Settings
ADMINISTRATIVE_SKIP_PHRASES = [
    'this message was deleted',
    'missed voice call',
    'missed video call',
    'joined using this group',
    'left',
    'changed the group description',
    'changed this group\'s icon',
    'changed the subject',
    'added',
    'removed',
    'end-to-end encrypted',
    'security code changed',
    'media omitted',
    '<media omitted>'
]

# Date Processing
DEFAULT_TIMEZONE = 'UTC'
DATE_FORMATS = [
    '%Y-%m-%d %H:%M:%S',
    '%d/%m/%Y, %H:%M',
    '%m/%d/%Y, %H:%M'
]

# Message Filtering
MIN_MESSAGE_LENGTH = 3  # Minimum characters for meaningful messages
MAX_MESSAGES_PER_SENDER = 1000  # Limit to prevent memory issues