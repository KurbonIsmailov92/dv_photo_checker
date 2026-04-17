"""
Minimal auto-crop to DV standard (600x600).
Only crops + resizes, no filters or adjustments.
"""

import logging
import cv2
import numpy as np
from typing import Tuple
from face_analyzer import detect_face_landmarks, detect_face_rect
from config import CROP_TARGET_SIZE, CROP_MARGIN_FACTOR

logger = logging.getLogger(__name__)

# Face landmark indices (same as in face_analyzer)
TOP_HEAD_LANDMARK = 10
CHIN_LANDMARK = 152
LEFT_EYE_LANDMARKS = [33, 133, 160, 159, 158, 157]
RIGHT_EYE_LANDMARKS = [263, 362, 387, 386, 385, 384]

# Soft target ratios for positioning
TARGET_HEAD_RATIO = 0.60  # Head should be ~60% of image height
TARGET_EYE_RATIO = 0.58   # Eye level should be ~58% from bottom


def compute_eye_center(landmarks, indices):
    """Compute center point of eye landmarks."""
    points = np.array([landmarks[i] for i in indices], dtype=np.float32)
    return tuple(np.mean(points, axis=0).tolist())


def calculate_crop_region(image: np.ndarray, landmarks) -> Tuple[int, int, int]:
    """
    Calculate optimal crop region based on face landmarks.
    
    Returns: (x0, y0, crop_size)
    """
    h, w = image.shape[:2]

    # Validate landmarks
    if (not landmarks or 
        len(landmarks) <= max(TOP_HEAD_LANDMARK, CHIN_LANDMARK, max(LEFT_EYE_LANDMARKS + RIGHT_EYE_LANDMARKS))):
        # Fallback: center crop largest square
        side = min(h, w)
        x0 = (w - side) // 2
        y0 = (h - side) // 2
        logger.debug("Using fallback center crop for landmarks")
        return x0, y0, side

    # Get face geometry from landmarks
    top_y = landmarks[TOP_HEAD_LANDMARK][1]
    chin_y = landmarks[CHIN_LANDMARK][1]
    head_height = max(chin_y - top_y, 1.0)

    # Calculate eye center
    left_eye = compute_eye_center(landmarks, LEFT_EYE_LANDMARKS)
    right_eye = compute_eye_center(landmarks, RIGHT_EYE_LANDMARKS)
    eye_center_x = (left_eye[0] + right_eye[0]) / 2.0
    eye_center_y = (left_eye[1] + right_eye[1]) / 2.0

    # Calculate crop size based on head height
    crop_size = int(head_height / TARGET_HEAD_RATIO)
    crop_size = int(crop_size * (1.0 + CROP_MARGIN_FACTOR))
    crop_size = min(crop_size, min(h, w))

    # Position crop so eye is at target level
    target_eye_y_in_crop = crop_size * (1.0 - TARGET_EYE_RATIO)
    y0 = int(eye_center_y - target_eye_y_in_crop)

    # Center horizontally on face
    x0 = int(eye_center_x - crop_size / 2.0)

    # Clamp to image boundaries
    y0 = max(0, min(y0, h - crop_size))
    x0 = max(0, min(x0, w - crop_size))

    return x0, y0, crop_size


def auto_crop_to_dv_standard(image: np.ndarray) -> Tuple[np.ndarray, bool, dict]:
    """
    Crop image to 600x600 DV standard using face detection.
    
    Strategy:
    1. Use MediaPipe landmarks for precise positioning (preferred)
    2. Fallback to face box detection (MediaPipe Face Detection or Haar Cascade)
    3. Last resort: center crop
    
    Returns:
        cropped_image: 600x600 image
        crop_applied: True if any cropping was done
        crop_info: metadata about the cropping process
    """
    if image is None:
        raise ValueError("Invalid image provided")

    h, w = image.shape[:2]
    target_w, target_h = CROP_TARGET_SIZE

    # If already target size, return as-is
    if h == target_h and w == target_w:
        logger.debug("Image already target size, returning as-is")
        return image.copy(), False, {"reason": "already_target_size"}

    crop_info = {
        "original_width": w,
        "original_height": h,
        "target_width": target_w,
        "target_height": target_h,
    }

    # Try landmarks first (most accurate)
    landmarks = detect_face_landmarks(image)
    if landmarks is not None:
        x0, y0, crop_size = calculate_crop_region(image, landmarks)
        crop_info["reason"] = "face_landmarks"
        crop_info["crop_x"] = x0
        crop_info["crop_y"] = y0
        crop_info["crop_size"] = crop_size
        cropped = image[y0:y0 + crop_size, x0:x0 + crop_size]
        resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_AREA)
        logger.debug(f"Cropped using landmarks: {crop_size}x{crop_size} from ({x0},{y0})")
        return resized, True, crop_info

    # Fallback to face box detection
    face_rect = detect_face_rect(image)
    if face_rect is not None:
        x, y, fw, fh = face_rect
        cx = x + fw / 2.0
        cy = y + fh * 0.38  # approximate eye center
        head_height = max(1.0, fh * 1.2)
        crop_size = int(head_height / TARGET_HEAD_RATIO * (1.0 + CROP_MARGIN_FACTOR))
        crop_size = min(crop_size, min(h, w))
        x0 = int(cx - crop_size / 2.0)
        y0 = int(cy - crop_size * (1.0 - TARGET_EYE_RATIO))
        x0 = max(0, min(x0, w - crop_size))
        y0 = max(0, min(y0, h - crop_size))
        
        crop_info["reason"] = "face_box"
        crop_info["crop_x"] = x0
        crop_info["crop_y"] = y0
        crop_info["crop_size"] = crop_size
        cropped = image[y0:y0 + crop_size, x0:x0 + crop_size]
        resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_AREA)
        logger.debug(f"Cropped using face box: {crop_size}x{crop_size} from ({x0},{y0})")
        return resized, True, crop_info

    # Last resort: center crop
    crop_info["reason"] = "center_crop"
    side = min(h, w)
    x0 = (w - side) // 2
    y0 = (h - side) // 2
    cropped = image[y0:y0 + side, x0:x0 + side]
    resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_AREA)
    logger.debug(f"Using fallback center crop: {side}x{side}")
    return resized, True, crop_info
