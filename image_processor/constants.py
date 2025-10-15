"""
Constants for the image processing system
"""

# S3 Configuration
DEFAULT_S3_REGION = "ap-south-1"

# Image Processing Settings
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
MAX_IMAGE_SIZE_MB = 10
THUMBNAIL_SIZE = (150, 150)

# Upload Settings
S3_URL_EXPIRY_HOURS = 24 * 365 * 10  # 10 year
