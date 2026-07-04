from __future__ import annotations

import logging
import os

import boto3

logger = logging.getLogger(__name__)

CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
}


class S3Uploader:
    def __init__(
        self,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        aws_region: str,
        bucket_name: str,
    ) -> None:
        self.bucket = bucket_name
        self.region = aws_region
        self.client = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region,
        )

    def upload(
        self,
        file_path: str,
        year: int,
        month: int,
        facilitator_name: str,
        filename: str,
    ) -> str | None:
        if not os.path.exists(file_path):
            logger.warning("File not found for upload: %s", file_path)
            return None

        safe_name = facilitator_name.replace(" ", "_").replace("/", "_")
        s3_key = f"reports/{year}/{month:02d}/{safe_name}/{filename}"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        content_type = CONTENT_TYPES.get(ext, "image/jpeg")

        try:
            self.client.upload_file(
                file_path,
                self.bucket,
                s3_key,
                ExtraArgs={"ContentType": content_type},
            )
            return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}"
        except Exception:
            logger.exception("S3 upload failed for %s", file_path)
            return None
