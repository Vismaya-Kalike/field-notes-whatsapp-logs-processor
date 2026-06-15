from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).parent / "models"
_PROTOTXT = _MODEL_DIR / "deploy.prototxt"
_CAFFEMODEL = _MODEL_DIR / "res10_300x300_ssd_iter_140000_fp16.caffemodel"

_PROTOTXT_URL = (
    "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt"
)
_CAFFEMODEL_URL = (
    "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20180205_fp16/"
    "res10_300x300_ssd_iter_140000_fp16.caffemodel"
)

CONFIDENCE_THRESHOLD = 0.5


def _ensure_model() -> None:
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)

    if not _PROTOTXT.exists():
        logger.info("Downloading DNN face detector prototxt...")
        urllib.request.urlretrieve(_PROTOTXT_URL, _PROTOTXT)

    if not _CAFFEMODEL.exists():
        logger.info("Downloading DNN face detector model (~5MB)...")
        urllib.request.urlretrieve(_CAFFEMODEL_URL, _CAFFEMODEL)


def _load_net() -> cv2.dnn.Net:
    _ensure_model()
    return cv2.dnn.readNetFromCaffe(str(_PROTOTXT), str(_CAFFEMODEL))


_net: cv2.dnn.Net | None = None


def _get_net() -> cv2.dnn.Net:
    global _net
    if _net is None:
        _net = _load_net()
    return _net


def _detect_faces(image: np.ndarray) -> bool:
    blob = cv2.dnn.blobFromImage(
        cv2.resize(image, (300, 300)),
        1.0, (300, 300), (104.0, 177.0, 123.0),
    )
    net = _get_net()
    net.setInput(blob)
    detections = net.forward()

    for i in range(detections.shape[2]):
        if detections[0, 0, i, 2] > CONFIDENCE_THRESHOLD:
            return True
    return False


def _detect_faces_multiscale(image: np.ndarray) -> bool:
    if _detect_faces(image):
        return True

    h, w = image.shape[:2]
    if h < 300 and w < 300:
        return False

    overlap = 0.25
    tile_h, tile_w = h // 2, w // 2
    step_h = int(tile_h * (1 - overlap))
    step_w = int(tile_w * (1 - overlap))

    for y in range(0, h - tile_h + 1, step_h):
        for x in range(0, w - tile_w + 1, step_w):
            tile = image[y : y + tile_h, x : x + tile_w]
            if tile.shape[0] >= 50 and tile.shape[1] >= 50:
                if _detect_faces(tile):
                    return True

    return False


def is_image_safe(image_path: str) -> bool:
    try:
        if not os.path.exists(image_path):
            logger.warning("Image not found: %s", image_path)
            return False

        image = cv2.imread(image_path)
        if image is None:
            logger.warning("Could not load image: %s", image_path)
            return False

        if _detect_faces_multiscale(image):
            logger.info(
                "Face detected in %s — marking unsafe",
                os.path.basename(image_path),
            )
            return False

        return True

    except Exception:
        logger.exception("Face detection error on %s — treating as unsafe", image_path)
        return False
