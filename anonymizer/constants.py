"""
Constants for the name anonymization system
"""

# OpenAI Model Configuration
OPENAI_MODEL = "gpt-4o-mini"  # Fast and efficient for name detection
OPENAI_TEMPERATURE = 0.3  # Lower temperature for more consistent results
OPENAI_MAX_COMPLETION_TOKENS = 500  # Reduced since we only need JSON output
OPENAI_TIMEOUT = 15  # Shorter timeout

# Anonymization Settings
NAME_MAPPING_FILE = "name_anonymization_mapping.json"