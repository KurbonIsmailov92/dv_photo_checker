from __future__ import annotations

import cv2
import numpy as np

from config import (
    BALANCED_MODE,
    BALANCED_THRESHOLDS,
    DEFAULT_MODE,
    FACE_DETECTION_CONFIDENCE,
    FALLBACK_CONFIDENCE,
    STRICT_MODE,
    STRICT_THRESHOLDS,
    TARGET_EYE_LEVEL,
    TARGET_HEAD_PERCENT,
)
from image_utils import bgr_to_rgb, detection_retry_image, ensure_bgr

try:
    import mediapipe as mp
except ImportError:
    mp = None

# Face landmark indices in MediaPipe mesh
LEFT_EYE_LANDMARKS = [33, 133, 160, 159, 158, 157]
RIGHT_EYE_LANDMARKS = [263, 362, 387, 386, 385, 384]
TOP_HEAD_LANDMARK = 10
CHIN_LANDMARK = 152


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(min(value, maximum), minimum)


def _build_mesh(min_confidence: float):
    if mp is None:
        return None
    return mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=min_confidence,
        min_tracking_confidence=min_confidence,
    )


def _build_face_detector(min_confidence: float):
    if mp is None:
        return None
    return mp.solutions.face_detection.FaceDetection(
        model_selection=1,
        min_detection_confidence=min_confidence,
    )


_FACE_MESH_PRIMARY = _build_mesh(FACE_DETECTION_CONFIDENCE)
_FACE_MESH_FALLBACK = _build_mesh(FALLBACK_CONFIDENCE)
_MP_FACE_DETECT_PRIMARY = _build_face_detector(FACE_DETECTION_CONFIDENCE)
_MP_FACE_DETECT_FALLBACK = _build_face_detector(FALLBACK_CONFIDENCE)
_HAAR_FACE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def _mesh_to_pixels(landmarks, width: int, height: int) -> list[tuple[float, float]]:
    return [(lm.x * width, lm.y * height) for lm in landmarks]


def _run_mesh(mesh, image_bgr: np.ndarray, target_shape: tuple[int, int]) -> list[tuple[float, float]] | None:
    if mesh is None:
        return None
    rgb = bgr_to_rgb(image_bgr)
    if rgb is None:
        return None
    result = mesh.process(rgb)
    if not result.multi_face_landmarks:
        return None
    h_t, w_t = target_shape[:2]
    h_s, w_s = image_bgr.shape[:2]
    scale_x = float(w_t) / float(w_s)
    scale_y = float(h_t) / float(h_s)
    pts = _mesh_to_pixels(result.multi_face_landmarks[0].landmark, w_s, h_s)
    return [(x * scale_x, y * scale_y) for x, y in pts]


def detect_face_landmarks(image: np.ndarray | None) -> list[tuple[float, float]] | None:
    image = ensure_bgr(image)
    if image is None:
        return None

    h, w = image.shape[:2]
    # 3 попытки
    variants = [
        image,
        cv2.resize(image, (int(w * 1.4), int(h * 1.4)), interpolation=cv2.INTER_CUBIC),  # CUBIC лучше для лица
        detection_retry_image(image),
    ]

    for variant in variants:
        if variant is None:
            continue
        for mesh in (_FACE_MESH_PRIMARY, _FACE_MESH_FALLBACK):
            if mesh is None:
                continue
            rgb = bgr_to_rgb(variant)
            if rgb is None:
                continue
            result = mesh.process(rgb)
            if result.multi_face_landmarks:
                # Возвращаем landmarks в оригинальном масштабе
                return _mesh_to_pixels(result.multi_face_landmarks[0].landmark, w, h)
    return None


def face_rect_from_landmarks(
    landmarks: list[tuple[float, float]],
    width: int,
    height: int,
    pad_ratio: float = 0.08,
) -> tuple[int, int, int, int]:
    xs = [x for x, _ in landmarks]
    ys = [y for _, y in landmarks]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    pad_x = (x_max - x_min) * pad_ratio + 4.0
    pad_y = (y_max - y_min) * pad_ratio + 4.0
    x0 = int(max(0, np.floor(x_min - pad_x)))
    y0 = int(max(0, np.floor(y_min - pad_y)))
    x1 = int(min(width - 1, np.ceil(x_max + pad_x)))
    y1 = int(min(height - 1, np.ceil(y_max + pad_y)))
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def detect_face_rect_mp(image: np.ndarray | None) -> tuple[int, int, int, int] | None:
    image = ensure_bgr(image)
    if image is None:
        return None
    rgb = bgr_to_rgb(image)
    h, w = image.shape[:2]
    for detector in (_MP_FACE_DETECT_PRIMARY, _MP_FACE_DETECT_FALLBACK):
        if detector is None:
            continue
        result = detector.process(rgb)
        if not result.detections:
            continue
        det = max(result.detections, key=lambda d: d.score[0] if d.score else 0.0)
        box = det.location_data.relative_bounding_box
        x = int(max(0, box.xmin * w))
        y = int(max(0, box.ymin * h))
        fw = int(min(w - x, box.width * w))
        fh = int(min(h - y, box.height * h))
        if fw > 0 and fh > 0:
            return x, y, fw, fh
    return None


def detect_face_rect_haar(image: np.ndarray | None) -> tuple[int, int, int, int] | None:
    image = ensure_bgr(image)
    if image is None or _HAAR_FACE is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    faces = _HAAR_FACE.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(max(30, int(0.15 * min(h, w))), max(30, int(0.15 * min(h, w)))),
    )
    if len(faces) == 0:
        return None
    x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
    return int(x), int(y), int(fw), int(fh)


def detect_face_rect(image: np.ndarray | None) -> tuple[int, int, int, int] | None:
    landmarks = detect_face_landmarks(image)
    if landmarks is not None:
        h, w = image.shape[:2]
        return face_rect_from_landmarks(landmarks, w, h)
    return detect_face_rect_mp(image) or detect_face_rect_haar(image)


def compute_eye_center(landmarks: list[tuple[float, float]], indices: list[int]) -> tuple[float, float]:
    points = np.array([landmarks[i] for i in indices], dtype=np.float32)
    center = np.mean(points, axis=0)
    return float(center[0]), float(center[1])


def calculate_face_geometry(landmarks: list[tuple[float, float]], image_height: int) -> tuple[float | None, float | None]:
    if not landmarks:
        return None, None
    if len(landmarks) <= max(CHIN_LANDMARK, TOP_HEAD_LANDMARK):
        return None, None
    top_y = landmarks[TOP_HEAD_LANDMARK][1]
    chin_y = landmarks[CHIN_LANDMARK][1]
    head_percent = ((chin_y - top_y) / float(image_height)) * 100.0
    left_eye = compute_eye_center(landmarks, LEFT_EYE_LANDMARKS)
    right_eye = compute_eye_center(landmarks, RIGHT_EYE_LANDMARKS)
    eye_center_y = (left_eye[1] + right_eye[1]) / 2.0
    eye_level = ((float(image_height) - eye_center_y) / float(image_height)) * 100.0
    return float(head_percent), float(eye_level)


def approximate_geometry_from_face_rect(face_rect: tuple[int, int, int, int], image_height: int) -> tuple[float, float, float]:
    x, y, fw, fh = face_rect
    top_y = max(0.0, y - 0.18 * fh)
    chin_y = min(float(image_height - 1), y + 1.02 * fh)
    eye_center_y = y + 0.38 * fh
    head_percent = ((chin_y - top_y) / float(image_height)) * 100.0
    eye_level = ((float(image_height) - eye_center_y) / float(image_height)) * 100.0
    return float(head_percent), float(eye_level), float(eye_center_y)


def face_geometry_score(head_percent: float, eye_level: float) -> float:
    head_target = sum(TARGET_HEAD_PERCENT) / 2.0
    eye_target = sum(TARGET_EYE_LEVEL) / 2.0
    head_score = clamp(1.0 - abs(head_percent - head_target) / 18.0)
    eye_score = clamp(1.0 - abs(eye_level - eye_target) / 18.0)
    return float(np.mean([head_score, eye_score]))


def validate_face_geometry(image, mode: str = DEFAULT_MODE):
    issues: list[str] = []
    warnings: list[str] = []
    metrics: dict = {}
    feature_scores: dict = {}

    image = ensure_bgr(image)
    if image is None:
        issues.append("Invalid image provided")
        feature_scores["face_geometry_score"] = 0.35
        return {"issues": issues, "warnings": warnings, "metrics": metrics, "feature_scores": feature_scores}

    h, w = image.shape[:2]
    thresholds = STRICT_THRESHOLDS if mode == STRICT_MODE else BALANCED_THRESHOLDS
    head_min, head_max = thresholds["head_percent"]
    eye_min, eye_max = thresholds["eye_level"]

    landmarks = detect_face_landmarks(image)
    if landmarks is not None:
        metrics["landmarks_found"] = True
        face_rect = face_rect_from_landmarks(landmarks, w, h)
        head_percent, eye_level = calculate_face_geometry(landmarks, h)
    else:
        metrics["landmarks_found"] = False
        face_rect = detect_face_rect_mp(image) or detect_face_rect_haar(image)
        if face_rect is None:
            warnings.append("Face landmarks not found with MediaPipe Face Mesh")
            feature_scores["face_geometry_score"] = 0.45
            return {"issues": issues, "warnings": warnings, "metrics": metrics, "feature_scores": feature_scores}
        head_percent, eye_level, eye_center_y = approximate_geometry_from_face_rect(face_rect, h)
        warnings.append("Face Mesh unavailable; geometry estimated from face box.")
        metrics["eye_center_y"] = round(eye_center_y, 2)

    metrics["face_rect"] = {"x": face_rect[0], "y": face_rect[1], "w": face_rect[2], "h": face_rect[3]}
    metrics["head_percent"] = round(float(head_percent), 2)
    metrics["eye_level"] = round(float(eye_level), 2)

    if head_percent < head_min or head_percent > head_max:
        (warnings if mode == BALANCED_MODE else issues).append(
            f"Head percent is outside allowed range ({head_percent:.1f}%)"
        )
    if eye_level < eye_min or eye_level > eye_max:
        (warnings if mode == BALANCED_MODE else issues).append(
            f"Eye level is outside allowed range ({eye_level:.1f}%)"
        )

    base = face_geometry_score(head_percent, eye_level)
    if not metrics["landmarks_found"]:
        base *= 0.85
    feature_scores["face_geometry_score"] = round(float(base), 3)

    return {"issues": issues, "warnings": warnings, "metrics": metrics, "feature_scores": feature_scores}
