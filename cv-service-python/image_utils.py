from __future__ import annotations

import base64
import binascii

import cv2
import numpy as np

from config import DETECTION_RETRY_CONTRAST_ALPHA, DETECTION_RETRY_CONTRAST_BETA


def _decode_base64_payload(contents: str) -> bytes | None:
    payload = contents.strip()
    if not payload:
        return None

    if payload.startswith("data:"):
        _, _, payload = payload.partition(",")

    payload = "".join(payload.split())
    if not payload:
        return None

    padding = len(payload) % 4
    if padding:
        payload += "=" * (4 - padding)

    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        try:
            return base64.b64decode(payload, validate=False)
        except (binascii.Error, ValueError):
            return None


def decode_upload_image(contents: bytes | bytearray | memoryview | str) -> np.ndarray | None:
    """Decode raw bytes or a base64/data URL string to an OpenCV image."""
    if isinstance(contents, str):
        raw = _decode_base64_payload(contents)
    elif isinstance(contents, (bytes, bytearray, memoryview)):
        raw = bytes(contents)
    else:
        return None

    if not raw:
        return None

    nparr = np.frombuffer(raw, np.uint8)
    if nparr.size == 0:
        return None

    return cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)


def ensure_bgr(image: np.ndarray | None) -> np.ndarray | None:
    """
    Normalize image to 3-channel BGR.
    Supports grayscale, BGR, BGRA.
    """
    if image is None:
        return None
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim == 3 and image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    if image.ndim == 3 and image.shape[2] == 3:
        return image
    return None


def bgr_to_rgb(image_bgr: np.ndarray | None) -> np.ndarray | None:
    """Convert BGR image to RGB for MediaPipe."""
    if image_bgr is None:
        return None
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


def detection_retry_image(image_bgr: np.ndarray | None) -> np.ndarray | None:
    """
    Slight contrast lift for a second detection attempt.
    Used only in-memory for detector; never saved to output.
    """
    if image_bgr is None:
        return None
    return cv2.convertScaleAbs(
        image_bgr,
        alpha=DETECTION_RETRY_CONTRAST_ALPHA,
        beta=DETECTION_RETRY_CONTRAST_BETA,
    )
