from __future__ import annotations

import argparse
import logging
import tempfile
import urllib.request
from pathlib import Path

import boto3

from src.config import Settings
from src.db.client import create_supabase_client
from src.privacy.face_detector import is_image_safe

logger = logging.getLogger(__name__)


def _fetch_all_images(client, page_size: int = 1000) -> list[dict]:
    all_images = []
    offset = 0
    while True:
        resp = (
            client.table("field_images")
            .select("id, photo_url")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not resp.data:
            break
        all_images.extend(resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size
    return all_images


def _s3_key_from_url(url: str, bucket: str, region: str) -> str | None:
    prefix = f"https://{bucket}.s3.{region}.amazonaws.com/"
    if url.startswith(prefix):
        return url[len(prefix):]
    return None


def run(args: argparse.Namespace) -> None:
    settings = Settings.from_env()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    supabase = create_supabase_client(settings.supabase_url, settings.supabase_secret_key)

    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )

    logger.info("Fetching all field images...")
    images = _fetch_all_images(supabase)
    logger.info("Fetched %d images", len(images))

    if not images:
        print("No images to reprocess.")
        return

    safe = 0
    unsafe = 0
    errors = 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        for i, img in enumerate(images):
            image_id = img["id"]
            url = img["photo_url"]

            logger.info("Checking image %d/%d (id=%s)", i + 1, len(images), image_id[:8])

            ext = Path(url).suffix or ".jpg"
            tmp_path = Path(tmp_dir) / f"{image_id}{ext}"

            try:
                urllib.request.urlretrieve(url, tmp_path)
            except Exception:
                logger.exception("Failed to download %s", url)
                errors += 1
                continue

            if is_image_safe(str(tmp_path)):
                safe += 1
                tmp_path.unlink(missing_ok=True)
                continue

            unsafe += 1
            tmp_path.unlink(missing_ok=True)

            if args.dry_run:
                logger.info("[DRY RUN] Would delete image %s", image_id[:8])
                continue

            s3_key = _s3_key_from_url(url, settings.s3_bucket_name, settings.aws_region)
            if s3_key:
                try:
                    s3.delete_object(Bucket=settings.s3_bucket_name, Key=s3_key)
                    logger.info("Deleted from S3: %s", s3_key)
                except Exception:
                    logger.exception("Failed to delete S3 object: %s", s3_key)

            try:
                supabase.table("field_images").delete().eq("id", image_id).execute()
                logger.info("Deleted from DB: %s", image_id[:8])
            except Exception:
                logger.exception("Failed to delete DB row: %s", image_id)
                errors += 1

    print(f"\n{'=' * 60}")
    print("IMAGE REPROCESS SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total images: {len(images)}")
    print(f"Safe (kept): {safe}")
    print(f"Faces detected (removed): {unsafe}")
    if errors:
        print(f"Errors: {errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-check existing images for face detection")
    parser.add_argument("--dry-run", action="store_true", help="Check only, don't delete")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
