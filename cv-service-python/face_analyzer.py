import cv2
import numpy as np

from config import BALANCED_MODE, BALANCED_THRESHOLDS, DEFAULT_MODE, STRICT_MODE

try:
    import mediapipe as mp
    # For now, disable face detection due to API changes in mediapipe 0.10.x
    # TODO: Update to use FaceLandmarker with proper model loading
    MP_FACE_LANDMARKER = None
except ImportError:
    MP_FACE_LANDMARKER = None

LEFT_EYE_LANDMARKS = [33, 133, 160, 159, 158, 157]
RIGHT_EYE_LANDMARKS = [263, 362, 387, 386, 385, 384]
TOP_HEAD_LANDMARK = 10
CHIN_LANDMARK = 152


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(min(value, maximum), minimum)


def normalize_landmarks(image, landmarks):
    h, w = image.shape[:2]
    return [(int(max(0, min(w - 1, lm.x * w))), int(max(0, min(h - 1, lm.y * h)))) for lm in landmarks]


def detect_mesh_landmarks(image):
    if MP_FACE_LANDMARKER is None:
        return None

    # TODO: Implement with new FaceLandmarker API
    return None


def compute_eye_center(landmarks, indices):
    points = np.array([landmarks[i] for i in indices], dtype=np.float32)
    return tuple(np.mean(points, axis=0).tolist())


def face_geometry_score(head_percent: float, eye_level: float) -> float:
    head_target = 60.0
    eye_target = 59.0
    score_head = clamp(1.0 - abs(head_percent - head_target) / 40.0)
    score_eye = clamp(1.0 - abs(eye_level - eye_target) / 40.0)
    return float(np.mean([score_head, score_eye]))


def validate_face_geometry(image, mode: str = DEFAULT_MODE):
    issues = []
    warnings = []
    metrics = {}
    feature_scores = {}

    landmarks = detect_mesh_landmarks(image)
    if landmarks is None:
        issues.append("Face landmarks not found with MediaPipe Face Mesh")
        feature_scores["face_geometry_score"] = 0.30
        metrics["landmarks_found"] = False
        return {
            "issues": issues,
            "warnings": warnings,
            "metrics": metrics,
            "feature_scores": feature_scores,
        }

    metrics["landmarks_found"] = True
    top_y = landmarks[TOP_HEAD_LANDMARK][1]
    chin_y = landmarks[CHIN_LANDMARK][1]
    left_eye = compute_eye_center(landmarks, LEFT_EYE_LANDMARKS)
    right_eye = compute_eye_center(landmarks, RIGHT_EYE_LANDMARKS)
    eye_center_y = float((left_eye[1] + right_eye[1]) / 2.0)

    head_percent = float((chin_y - top_y) / 600.0 * 100.0)
    eye_level = float((600.0 - eye_center_y) / 600.0 * 100.0)

    metrics["head_percent"] = round(head_percent, 2)
    metrics["eye_level"] = round(eye_level, 2)
    metrics["face_top_y"] = int(top_y)
    metrics["face_chin_y"] = int(chin_y)
    metrics["eye_center_y"] = round(eye_center_y, 2)

    thresholds = STRICT_MODE if mode == STRICT_MODE else BALANCED_THRESHOLDS
    head_range = thresholds["head_percent"]
    eye_range = thresholds["eye_level"]

    if head_percent < head_range[0] or head_percent > head_range[1]:
        if mode == BALANCED_MODE and head_percent >= BALANCED_THRESHOLDS["head_percent"][0] and head_percent <= BALANCED_THRESHOLDS["head_percent"][1]:
            warnings.append(f"Head percent is slightly outside the ideal range ({head_percent:.1f}%)")
        else:
            issues.append(f"Head percent is outside the allowed range ({head_percent:.1f}%)")

    if eye_level < eye_range[0] or eye_level > eye_range[1]:
        if mode == BALANCED_MODE and eye_level >= BALANCED_THRESHOLDS["eye_level"][0] and eye_level <= BALANCED_THRESHOLDS["eye_level"][1]:
            warnings.append(f"Eye level is slightly outside the ideal range ({eye_level:.1f}%)")
        else:
            issues.append(f"Eye level is outside the allowed range ({eye_level:.1f}%)")

    score = face_geometry_score(head_percent, eye_level)
    feature_scores["face_geometry_score"] = round(score, 3)

    return {
        "issues": issues,
        "warnings": warnings,
        "metrics": metrics,
        "feature_scores": feature_scores,
    }
