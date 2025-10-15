"""
Constants for the LLM analysis system
"""

# OpenAI Model Configuration
OPENAI_MODEL = "gpt-5"
OPENAI_TEMPERATURE = 1.0  # GPT-5 only supports default temperature of 1
OPENAI_MAX_COMPLETION_TOKENS = 4000
OPENAI_TIMEOUT = 60

# Analysis Settings
MAX_IMAGES_PER_ANALYSIS = 10  # GPT-5 has limits on number of images
MIN_MESSAGES_FOR_ANALYSIS = 3  # Minimum messages required for meaningful analysis

# Output Settings
ANALYSIS_FORMAT = "markdown"  # Output format for analysis