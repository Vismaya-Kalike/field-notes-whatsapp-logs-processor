import cv2
import numpy as np
from typing import Tuple, List, Dict, Any
import os
from face_detection.constants import (
    MIN_FACE_SIZE,
    DETECTION_CONFIDENCE_THRESHOLD,
    MAX_IMAGE_DIMENSION,
    SUPPORTED_FORMATS
)

def detect_faces_in_image(image_path: str, min_face_size: Tuple[int, int] = MIN_FACE_SIZE,
                         scale_factor: float = 1.1, min_neighbors: int = 5) -> Dict[str, Any]:
    """
    Detect faces in an image and determine if they are clearly identifiable.

    Args:
        image_path (str): Path to the image file
        min_face_size (tuple): Minimum face size (width, height) to detect
        scale_factor (float): How much the image size is reduced at each scale
        min_neighbors (int): How many neighbors each face rectangle should have to retain it

    Returns:
        Dict containing:
        - has_faces (bool): Whether any faces were detected
        - face_count (int): Number of faces detected
        - clearly_identifiable (bool): Whether faces are clearly identifiable
        - faces (list): List of face rectangles [(x, y, w, h), ...]
        - face_details (list): Details about each face (size, clarity score)
    """

    result = {
        'has_faces': False,
        'face_count': 0,
        'clearly_identifiable': False,
        'faces': [],
        'face_details': [],
        'error': None
    }

    try:
        # Check if image file exists
        if not os.path.exists(image_path):
            result['error'] = f"Image file not found: {image_path}"
            return result

        # Load the image
        image = cv2.imread(image_path)
        if image is None:
            result['error'] = f"Could not load image: {image_path}"
            return result

        # Convert to grayscale for face detection
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Load OpenCV's pre-trained face detection classifiers
        # Use the found cascade file paths
        face_cascade_path = '/opt/homebrew/lib/python3.11/site-packages/cv2/data/haarcascade_frontalface_default.xml'
        profile_cascade_path = '/opt/homebrew/lib/python3.11/site-packages/cv2/data/haarcascade_profileface.xml'

        face_cascade = cv2.CascadeClassifier(face_cascade_path)
        profile_cascade = cv2.CascadeClassifier(profile_cascade_path)

        # Verify cascades loaded correctly
        if face_cascade.empty():
            raise RuntimeError(f"Could not load face cascade from {face_cascade_path}")
        if profile_cascade.empty():
            raise RuntimeError(f"Could not load profile cascade from {profile_cascade_path}")

        # Detect frontal faces
        frontal_faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors,
            minSize=min_face_size,
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        # Detect profile faces (side view)
        profile_faces = profile_cascade.detectMultiScale(
            gray,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors,
            minSize=min_face_size,
            flags=cv2.CASCADE_SCALE_IMAGE
        )

        # Combine all detected faces with their types
        all_faces = []
        face_types = []

        # Add frontal faces
        for face in frontal_faces:
            all_faces.append(face)
            face_types.append('frontal')

        # Add profile faces
        for face in profile_faces:
            all_faces.append(face)
            face_types.append('profile')

        # Convert to numpy array for consistency
        faces = np.array(all_faces) if all_faces else np.array([])

        result['has_faces'] = len(faces) > 0
        result['face_count'] = len(faces)
        result['faces'] = faces.tolist() if len(faces) > 0 else []

        # Analyze each detected face for clarity/identifiability
        image_height, image_width = gray.shape
        total_image_area = image_height * image_width

        clearly_identifiable_faces = 0

        for i, (x, y, w, h) in enumerate(faces):
            face_area = w * h
            face_percentage = (face_area / total_image_area) * 100

            # Get face type (frontal or profile)
            face_type = face_types[i] if i < len(face_types) else 'frontal'

            # Extract face region for analysis
            face_roi = gray[y:y+h, x:x+w]

            # Calculate sharpness/clarity using Laplacian variance
            laplacian_var = cv2.Laplacian(face_roi, cv2.CV_64F).var()

            # Calculate face size relative to image
            face_size_score = min(w, h)  # Smaller dimension of the face

            face_detail = {
                'position': (x, y, w, h),
                'area': face_area,
                'percentage_of_image': face_percentage,
                'sharpness_score': laplacian_var,
                'min_dimension': face_size_score,
                'face_type': face_type,
                'is_clearly_identifiable': False
            }

            # More conservative criteria for "clearly identifiable" faces:
            # Being much more privacy-protective with lower thresholds

            # Different criteria based on face type
            if face_type == 'frontal':
                # Frontal faces are more identifiable - stricter criteria
                min_size = 30      # Even smaller faces can be identifiable (was 40)
                min_percentage = 0.3   # Even smaller portions matter (was 0.5%)
                min_sharpness = 30     # Even blurrier faces can be recognized (was 50)
            else:  # profile faces
                # Profile faces are less identifiable but still risky - moderate criteria
                min_size = 40
                min_percentage = 0.5
                min_sharpness = 40

            # Apply the criteria
            if (face_size_score >= min_size and
                face_percentage >= min_percentage and
                laplacian_var >= min_sharpness):

                face_detail['is_clearly_identifiable'] = True
                clearly_identifiable_faces += 1

            result['face_details'].append(face_detail)

        # Image is problematic if it has clearly identifiable faces
        result['clearly_identifiable'] = clearly_identifiable_faces > 0

    except Exception as e:
        result['error'] = f"Error processing image: {str(e)}"

    return result

def is_image_safe_for_display(image_path: str, strict_mode: bool = False, ultra_conservative: bool = False) -> Dict[str, Any]:
    """
    Determine if an image is safe to display publicly (no clearly identifiable faces).

    Args:
        image_path (str): Path to the image file
        strict_mode (bool): If True, any face detection makes image unsafe
        ultra_conservative (bool): If True, uses even stricter criteria for identifiable faces

    Returns:
        Dict containing:
        - is_safe (bool): Whether image is safe to display
        - reason (str): Reason for the decision
        - face_info (dict): Detailed face detection results
    """

    # Use stricter parameters for ultra conservative mode
    if ultra_conservative:
        face_info = detect_faces_in_image(image_path, min_face_size=(20, 20), min_neighbors=3)
    else:
        face_info = detect_faces_in_image(image_path)

    result = {
        'is_safe': True,
        'reason': 'No faces detected',
        'face_info': face_info
    }

    if face_info['error']:
        result['is_safe'] = False
        result['reason'] = f"Error analyzing image: {face_info['error']}"
        return result

    if not face_info['has_faces']:
        result['is_safe'] = True
        result['reason'] = 'No faces detected'
    elif strict_mode:
        result['is_safe'] = False
        result['reason'] = f"Faces detected ({face_info['face_count']} faces) - strict mode"
    elif face_info['clearly_identifiable']:
        result['is_safe'] = False
        identifiable_count = sum(1 for face in face_info['face_details']
                               if face['is_clearly_identifiable'])
        result['reason'] = f"Contains {identifiable_count} clearly identifiable face(s)"
    else:
        result['is_safe'] = True
        result['reason'] = f"Faces present ({face_info['face_count']}) but not clearly identifiable"

    return result

def batch_analyze_images(image_directory: str, file_extensions: List[str] = ['.jpg', '.jpeg', '.png']) -> Dict[str, Dict]:
    """
    Analyze all images in a directory for face detection.

    Args:
        image_directory (str): Directory containing images
        file_extensions (list): List of file extensions to process

    Returns:
        Dict mapping filename to analysis results
    """

    results = {}

    if not os.path.exists(image_directory):
        return results

    for filename in os.listdir(image_directory):
        if any(filename.lower().endswith(ext) for ext in file_extensions):
            image_path = os.path.join(image_directory, filename)
            results[filename] = is_image_safe_for_display(image_path)

    return results

# Example usage and testing
if __name__ == "__main__":
    print("🔍 Face Detection for Privacy Protection")
    print("=" * 50)

    # Test with a few images from whatsapp_data
    test_images = [
        "whatsapp_data/00000004-PHOTO-2025-07-03-01-17-36.jpg",
        "whatsapp_data/00000006-PHOTO-2025-07-03-03-22-28.jpg",
        "whatsapp_data/00000010-PHOTO-2025-07-03-03-24-44.jpg"
    ]

    for image_path in test_images:
        if os.path.exists(image_path):
            print(f"\n📸 Analyzing: {os.path.basename(image_path)}")
            result = is_image_safe_for_display(image_path)

            print(f"   Safe to display: {'✅ YES' if result['is_safe'] else '❌ NO'}")
            print(f"   Reason: {result['reason']}")

            face_info = result['face_info']
            if face_info['has_faces']:
                print(f"   Faces detected: {face_info['face_count']}")
                for i, face in enumerate(face_info['face_details']):
                    identifiable = "🔴 IDENTIFIABLE" if face['is_clearly_identifiable'] else "🟢 Anonymous"
                    print(f"     Face {i+1}: {identifiable} (size: {face['min_dimension']}px, sharpness: {face['sharpness_score']:.1f})")
        else:
            print(f"\n❌ Image not found: {image_path}")

    print(f"\n📊 Batch Analysis Summary")
    print("-" * 30)

    # Analyze first 10 images as a sample
    batch_results = batch_analyze_images("whatsapp_data", ['.jpg', '.jpeg'])

    safe_count = sum(1 for result in batch_results.values() if result['is_safe'])
    total_count = len(batch_results)

    print(f"Total images analyzed: {total_count}")
    print(f"Safe to display: {safe_count}")
    print(f"Need review/filtering: {total_count - safe_count}")

    if total_count > 0:
        print(f"Safety rate: {(safe_count/total_count)*100:.1f}%")