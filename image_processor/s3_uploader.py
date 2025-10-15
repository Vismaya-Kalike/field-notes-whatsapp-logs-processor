"""
S3 Image Uploader for educational field reports
Handles uploading images to S3 and generating public URLs
"""

import os
import boto3
from typing import Optional
from image_processor.constants import DEFAULT_S3_REGION, SUPPORTED_IMAGE_EXTENSIONS


class S3ImageUploader:
    """
    Handles uploading images to S3 bucket
    """

    def __init__(self, aws_access_key: str, aws_secret_key: str,
                 aws_region: str, s3_bucket: str):
        """
        Initialize S3 uploader

        Args:
            aws_access_key: AWS access key ID
            aws_secret_key: AWS secret access key
            aws_region: AWS region
            s3_bucket: S3 bucket name
        """
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.aws_region = aws_region
        self.s3_bucket = s3_bucket

        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            region_name=self.aws_region
        )

        print(f"Initialized S3 uploader for bucket: {self.s3_bucket}")

    def _get_content_type(self, file_path: str) -> str:
        """
        Determine content type based on file extension

        Args:
            file_path: Path to the image file

        Returns:
            MIME content type string
        """
        file_extension = file_path.lower().split('.')[-1]

        content_type_map = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp',
            'bmp': 'image/bmp'
        }

        return content_type_map.get(file_extension, 'image/jpeg')

    def upload_image(self, file_path: str, s3_key: str) -> Optional[str]:
        """
        Upload image to S3 and return the public URL

        Args:
            file_path: Local path to the image file
            s3_key: S3 key (path within bucket)

        Returns:
            Public URL of uploaded image, or None if upload failed
        """
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                return None

            # Determine content type
            content_type = self._get_content_type(file_path)

            # Upload without ACL (bucket must be configured for public access if needed)
            self.s3_client.upload_file(
                file_path,
                self.s3_bucket,
                s3_key,
                ExtraArgs={'ContentType': content_type}
            )

            # Generate public URL
            url = f"https://{self.s3_bucket}.s3.{self.aws_region}.amazonaws.com/{s3_key}"
            return url

        except Exception as e:
            print(f"Error uploading {file_path} to S3: {e}")
            return None

    def generate_s3_key(self, year: int, month: int, facilitator_name: str,
                       filename: str) -> str:
        """
        Generate a consistent S3 key for organizing uploaded images

        Args:
            year: Year of the report
            month: Month of the report
            facilitator_name: Name of the facilitator
            filename: Original filename

        Returns:
            S3 key string
        """
        safe_facilitator_name = facilitator_name.replace(' ', '_').replace('/', '_')
        return f"reports/{year}/{month:02d}/{safe_facilitator_name}/{filename}"

    def is_supported_image(self, filename: str) -> bool:
        """
        Check if the file is a supported image format

        Args:
            filename: Name of the file to check

        Returns:
            True if supported image format, False otherwise
        """
        file_extension = '.' + filename.lower().split('.')[-1]
        return file_extension in SUPPORTED_IMAGE_EXTENSIONS