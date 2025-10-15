"""
Constants for face detection and privacy filtering
"""

# Face Detection Settings
FACE_DETECTION_MODEL = 'mtcnn'  # or 'opencv', 'dlib'
MIN_FACE_SIZE = (20, 20)  # Minimum face size to detect
DETECTION_CONFIDENCE_THRESHOLD = 0.9

# Privacy Filter Settings
PRIVACY_KEYWORDS = [
    'private', 'personal', 'confidential', 'delete', 'remove',
    'don\'t share', 'not for sharing', 'family only'
]

# Image Processing Settings
MAX_IMAGE_DIMENSION = 1920  # Max width/height for processing
SUPPORTED_FORMATS = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']

# Output Settings
BLUR_RADIUS = 15  # Radius for face blurring
SAVE_ORIGINAL = True  # Keep original images