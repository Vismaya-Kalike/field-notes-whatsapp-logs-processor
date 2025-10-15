"""
Constants for database operations
"""

# Connection Settings
DEFAULT_TIMEOUT = 30  # Connection timeout in seconds
MAX_RETRIES = 3       # Maximum connection retry attempts
RETRY_DELAY = 2       # Delay between retries in seconds

# Query Settings
DEFAULT_BATCH_SIZE = 1000     # Default batch size for bulk operations
MAX_QUERY_TIMEOUT = 300       # Maximum query timeout in seconds

# Table Names
TABLES = {
    'facilitators': 'facilitators',
    'learning_centres': 'learning_centres',
    'partner_organisations': 'partner_organisations',
    'generated_reports': 'generated_reports',
    'generated_report_images': 'generated_report_images',
    'generated_report_messages': 'generated_report_messages',
    'generated_report_llm_analysis': 'generated_report_llm_analysis',
    'generated_reports_summary': 'generated_reports_summary'
}

# Environment Variables
DATABASE_URL_ENV = 'DATABASE_URL'