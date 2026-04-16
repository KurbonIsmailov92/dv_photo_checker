import cv2
import numpy as np
from typing import Tuple

try:
    import mediapipe as mp
    # Temporarily disabled due to API changes in mediapipe 0.10.x
    MP_FACE_MESH = None
except ImportError:
    MP_FACE_MESH = None

TOP_HEAD_LANDMARK = 10
CHIN_LANDMARK = 152
LEFT_EYE_LANDMARKS = [33, 133, 160, 159, 158, 157]
RIGHT_EYE_LANDMARKS = [263, 362, 387, 386, 385, 384]


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(min(value, maximum), minimum)


def _get_mesh_landmarks(image: np.ndarray):
    if MP_FACE_MESH is None:
        return None

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = MP_FACE_MESH.process(rgb)
    if not results.multi_face_landmarks:
        return None

    h, w = image.shape[:2]
    return [
        (int(max(0, min(w - 1, lm.x * w))), int(max(0, min(h - 1, lm.y * h))))
        for lm in results.multi_face_landmarks[0].landmark
    ]


def _average_points(points):
    arr = np.array(points, dtype=np.float32)
    return tuple(np.mean(arr, axis=0).tolist())


def auto_crop_to_dv_standard(image: np.ndarray) -> Tuple[np.ndarray, bool, dict]:
    """Crop the image to a 600x600 DV-style frame without changing lighting or color."""
    h, w = image.shape[:2]
    if h == 600 and w == 600:
        return image.copy(), False, {"reason": "already 600x600"}

    landmarks = _get_mesh_landmarks(image)
    if landmarks is None or len(landmarks) <= CHIN_LANDMARK:
        side = min(h, w)
        x0 = max(0, (w - side) // 2)
        y0 = max(0, (h - side) // 2)
        cropped = image[y0:y0 + side, x0:x0 + side]
        resized = cv2.resize(cropped, (600, 600), interpolation=cv2.INTER_AREA)
        return resized, True, {"reason": "no_mesh_landmarks", "fallback": "center_square"}

    top_x, top_y = landmarks[TOP_HEAD_LANDMARK]
    chin_x, chin_y = landmarks[CHIN_LANDMARK]
    left_eye = _average_points([landmarks[i] for i in LEFT_EYE_LANDMARKS])
    right_eye = _average_points([landmarks[i] for i in RIGHT_EYE_LANDMARKS])
    eye_center_x = float((left_eye[0] + right_eye[0]) / 2.0)
    eye_center_y = float((left_eye[1] + right_eye[1]) / 2.0)

    head_height = max(1, chin_y - top_y)
    target_head_ratio = 0.60
    crop_size = int(head_height / target_head_ratio)
    crop_size = int(crop_size * 1.08)
    crop_size = clamp(crop_size, min(h, w) * 0.40, min(h, w))
    crop_size = int(crop_size)

    target_eye_bottom_ratio = 0.59
    target_eye_y = crop_size * (1.0 - target_eye_bottom_ratio)
    y0 = int(eye_center_y - target_eye_y)
    x0 = int(eye_center_x - crop_size * 0.5)

    y0 = int(clamp(y0, 0, h - crop_size))
    x0 = int(clamp(x0, 0, w - crop_size))

    if crop_size > min(h, w):
        crop_size = min(h, w)
        x0 = max(0, min(x0, w - crop_size))
        y0 = max(0, min(y0, h - crop_size))

    cropped = image[y0:y0 + crop_size, x0:x0 + crop_size]
    if cropped.size == 0:
        side = min(h, w)
        cropped = image[0:side, 0:side]

    resized = cv2.resize(cropped, (600, 600), interpolation=cv2.INTER_AREA)
    return resized, True, {
        "crop_x": x0,
        "crop_y": y0,
        "crop_size": crop_size,
        "face_head_height": head_height,
        "eye_center_y": round(eye_center_y, 2),
    }
