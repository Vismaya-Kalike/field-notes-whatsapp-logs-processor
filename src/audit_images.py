from __future__ import annotations

import csv
import logging
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

import cv2

from src.config import Settings
from src.db.client import create_supabase_client
from src.privacy.face_detector import _get_net

logger = logging.getLogger(__name__)


def _max_confidence(image, net) -> float:
    h, w = image.shape[:2]
    max_conf = 0.0

    blob = cv2.dnn.blobFromImage(
        cv2.resize(image, (300, 300)),
        1.0, (300, 300), (104.0, 177.0, 123.0),
    )
    net.setInput(blob)
    dets = net.forward()
    for i in range(dets.shape[2]):
        max_conf = max(max_conf, float(dets[0, 0, i, 2]))

    tile_h, tile_w = h // 2, w // 2
    if tile_h < 50 or tile_w < 50:
        return max_conf

    step_h = int(tile_h * 0.75)
    step_w = int(tile_w * 0.75)
    for y in range(0, h - tile_h + 1, step_h):
        for x in range(0, w - tile_w + 1, step_w):
            tile = image[y : y + tile_h, x : x + tile_w]
            if tile.shape[0] >= 50 and tile.shape[1] >= 50:
                blob = cv2.dnn.blobFromImage(
                    cv2.resize(tile, (300, 300)),
                    1.0, (300, 300), (104.0, 177.0, 123.0),
                )
                net.setInput(blob)
                dets = net.forward()
                for i in range(dets.shape[2]):
                    max_conf = max(max_conf, float(dets[0, 0, i, 2]))

    return max_conf


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = Settings.from_env()
    supabase = create_supabase_client(settings.supabase_url, settings.supabase_secret_key)

    logger.info("Fetching all field images...")
    all_images = []
    offset = 0
    while True:
        resp = (
            supabase.table("field_images")
            .select("id, photo_url")
            .range(offset, offset + 999)
            .execute()
        )
        if not resp.data:
            break
        all_images.extend(resp.data)
        if len(resp.data) < 1000:
            break
        offset += 1000

    logger.info("Fetched %d images", len(all_images))

    net = _get_net()
    output_path = Path("data/image_audit.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "s3_url", "max_confidence"])

        with tempfile.TemporaryDirectory() as tmp_dir:
            for i, img in enumerate(all_images):
                image_id = img["id"]
                url = img["photo_url"]

                logger.info("Checking %d/%d (id=%s)", i + 1, len(all_images), image_id[:8])

                ext = Path(url).suffix or ".jpg"
                tmp_path = os.path.join(tmp_dir, f"{image_id}{ext}")

                try:
                    urllib.request.urlretrieve(url, tmp_path)
                    image = cv2.imread(tmp_path)
                    if image is None:
                        writer.writerow([image_id, url, "error"])
                        continue

                    conf = _max_confidence(image, net)
                    writer.writerow([image_id, url, f"{conf:.4f}"])
                    os.unlink(tmp_path)
                except Exception as e:
                    logger.exception("Failed on %s", image_id[:8])
                    writer.writerow([image_id, url, "error"])

    logger.info("Written to %s", output_path)
    print(f"\nAudit complete: {output_path}")


if __name__ == "__main__":
    main()
