import cv2
import numpy as np
from typing import Tuple
from face_analyzer import detect_face_landmarks, detect_face_rect
from config import TARGET_HEAD_PERCENT, TARGET_EYE_LEVEL, CROP_TARGET_SIZE, CROP_MARGIN_FACTOR

# Face landmark indices (same as in face_analyzer)
TOP_HEAD_LANDMARK = 10
CHIN_LANDMARK = 152
LEFT_EYE_LANDMARKS = [33, 133, 160, 159, 158, 157]
RIGHT_EYE_LANDMARKS = [263, 362, 387, 386, 385, 384]


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp value to range [minimum, maximum]"""
    return max(min(value, maximum), minimum)


def compute_eye_center(landmarks, indices):
    """Compute center point of eye landmarks"""
    points = np.array([landmarks[i] for i in indices], dtype=np.float32)
    return tuple(np.mean(points, axis=0).tolist())


def calculate_crop_region(image: np.ndarray, landmarks) -> Tuple[int, int, int]:
    """
    Calculate optimal crop region based on face landmarks
    Returns: (x0, y0, crop_size)
    """
    h, w = image.shape[:2]

    if not landmarks or len(landmarks) <= max(TOP_HEAD_LANDMARK, CHIN_LANDMARK, max(LEFT_EYE_LANDMARKS + RIGHT_EYE_LANDMARKS)):
        # Fallback: center crop
        side = min(h, w)
        x0 = (w - side) // 2
        y0 = (h - side) // 2
        return x0, y0, side

    # Get face geometry
    top_y = landmarks[TOP_HEAD_LANDMARK][1]
    chin_y = landmarks[CHIN_LANDMARK][1]
    head_height = max(chin_y - top_y, 1.0)

    # Calculate eye center
    left_eye = compute_eye_center(landmarks, LEFT_EYE_LANDMARKS)
    right_eye = compute_eye_center(landmarks, RIGHT_EYE_LANDMARKS)
    eye_center_x = (left_eye[0] + right_eye[0]) / 2.0
    eye_center_y = (left_eye[1] + right_eye[1]) / 2.0

    # Target: head should be TARGET_HEAD_PERCENT[0]-TARGET_HEAD_PERCENT[1] % of final image
    # Eye level should be TARGET_EYE_LEVEL[0]-TARGET_EYE_LEVEL[1] % from bottom
    target_head_ratio = (TARGET_HEAD_PERCENT[0] + TARGET_HEAD_PERCENT[1]) / 2.0 / 100.0
    target_eye_ratio = (TARGET_EYE_LEVEL[0] + TARGET_EYE_LEVEL[1]) / 2.0 / 100.0

    # Calculate crop size to achieve target head ratio
    crop_size = int(head_height / target_head_ratio)

    # Add margin
    crop_size = int(crop_size * (1.0 + CROP_MARGIN_FACTOR))

    # Fit inside image; do not inflate crop (avoids wrong head framing)
    crop_size = min(crop_size, min(h, w))

    # Position crop so eye center is at target position
    target_eye_y_in_crop = crop_size * (1.0 - target_eye_ratio)
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
    Only crops, no color/lighting adjustments.

    Returns:
        cropped_image: 600x600 image
        crop_applied: True if cropping was done
        crop_info: dict with crop details
    """
    if image is None:
        raise ValueError("Invalid image provided")

    h, w = image.shape[:2]
    target_w, target_h = CROP_TARGET_SIZE

    # If already target size, return as-is
    if h == target_h and w == target_w:
        return image.copy(), False, {"reason": "already_target_size"}

    # Detect landmarks first; fallback to face rectangle detector.
    landmarks = detect_face_landmarks(image)
    fallback_face_rect = detect_face_rect(image) if landmarks is None else None

    crop_info = {
        "original_width": w,
        "original_height": h,
        "target_width": target_w,
        "target_height": target_h,
    }

    if landmarks is None:
        if fallback_face_rect is not None:
            # Crop based on face box when mesh landmarks are unavailable.
            x, y, fw, fh = fallback_face_rect
            cx = x + fw / 2.0
            cy = y + fh * 0.38  # approximate eye center
            target_head_ratio = (TARGET_HEAD_PERCENT[0] + TARGET_HEAD_PERCENT[1]) / 2.0 / 100.0
            target_eye_ratio = (TARGET_EYE_LEVEL[0] + TARGET_EYE_LEVEL[1]) / 2.0 / 100.0
            head_height = max(1.0, fh * 1.2)
            crop_size = int(head_height / target_head_ratio * (1.0 + CROP_MARGIN_FACTOR))
            crop_size = min(crop_size, min(h, w))
            x0 = int(cx - crop_size / 2.0)
            y0 = int(cy - crop_size * (1.0 - target_eye_ratio))
            x0 = max(0, min(x0, w - crop_size))
            y0 = max(0, min(y0, h - crop_size))
            crop_info["reason"] = "face_box_crop"
            crop_info["fallback"] = "mp_or_haar_face_box"
            crop_info["crop_x"] = x0
            crop_info["crop_y"] = y0
            crop_info["crop_size"] = crop_size
            cropped = image[y0:y0 + crop_size, x0:x0 + crop_size]
            resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_AREA)
            return resized, True, crop_info

        # Last fallback: center crop largest square.
        crop_info["reason"] = "no_face_detected"
        crop_info["fallback"] = "center_square"
        side = min(h, w)
        x0 = (w - side) // 2
        y0 = (h - side) // 2
        cropped = image[y0:y0 + side, x0:x0 + side]
        resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_AREA)
        return resized, True, crop_info

    # Calculate optimal crop region
    x0, y0, crop_size = calculate_crop_region(image, landmarks)

    crop_info["reason"] = "face_based_crop"
    crop_info["crop_x"] = x0
    crop_info["crop_y"] = y0
    crop_info["crop_size"] = crop_size
    crop_info["face_detected"] = True

    # Extract crop
    cropped = image[y0:y0 + crop_size, x0:x0 + crop_size]

    # Resize to target size
    resized = cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_AREA)

    return resized, True, crop_info
