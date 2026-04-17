import cv2
import numpy as np

from config import DETECTION_RETRY_CONTRAST_ALPHA, DETECTION_RETRY_CONTRAST_BETA


def decode_upload_image(contents: bytes) -> np.ndarray | None:
    """Decode bytes to BGR image for OpenCV processing."""
    nparr = np.frombuffer(contents, np.uint8)
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
