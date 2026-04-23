from __future__ import annotations

import logging
import cv2
import numpy as np

from config import (
    BALANCED_MODE,
    BALANCED_THRESHOLDS,
    DEFAULT_MODE,
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

logger = logging.getLogger(__name__)

# Face landmark indices in MediaPipe mesh
LEFT_EYE_LANDMARKS = [33, 133, 160, 159, 158, 157]
RIGHT_EYE_LANDMARKS = [263, 362, 387, 386, 385, 384]
LEFT_BROW_LANDMARKS = [70, 63, 105, 66, 107]
RIGHT_BROW_LANDMARKS = [336, 296, 334, 293, 300]
FOREHEAD_LANDMARKS = [10, 67, 109, 338, 297]
TOP_HEAD_LANDMARK = 10
CHIN_LANDMARK = 152

# MediaPipe confidence levels for detection attempts (progressive fallback)
CONFIDENCE_LEVELS = [0.5, 0.35, 0.25]


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(min(value, maximum), minimum)


def _build_mesh(min_confidence: float):
    """Create MediaPipe Face Mesh detector with given confidence level."""
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
    """Create MediaPipe Face Detection detector with given confidence level."""
    if mp is None:
        return None
    return mp.solutions.face_detection.FaceDetection(
        model_selection=1,
        min_detection_confidence=min_confidence,
    )


# Lazy-loaded detectors (initialized on first use to avoid import errors)
_FACE_MESHES = None
_MP_FACE_DETECTORS = None
_FACE_MESH_PRIMARY = None
_FACE_MESH_FALLBACK = None
_MP_FACE_DETECT_PRIMARY = None
_MP_FACE_DETECT_FALLBACK = None


def _init_detectors():
    """Initialize detectors on first use (lazy loading)."""
    global _FACE_MESHES, _MP_FACE_DETECTORS, _FACE_MESH_PRIMARY, _FACE_MESH_FALLBACK
    global _MP_FACE_DETECT_PRIMARY, _MP_FACE_DETECT_FALLBACK
    
    if _FACE_MESHES is None:
        _FACE_MESHES = [_build_mesh(conf) for conf in CONFIDENCE_LEVELS]
        _MP_FACE_DETECTORS = [_build_face_detector(conf) for conf in CONFIDENCE_LEVELS]
        _FACE_MESH_PRIMARY = _FACE_MESHES[0]
        _FACE_MESH_FALLBACK = _FACE_MESHES[1]
        _MP_FACE_DETECT_PRIMARY = _MP_FACE_DETECTORS[0]
        _MP_FACE_DETECT_FALLBACK = _MP_FACE_DETECTORS[1]
        logger.debug("MediaPipe detectors initialized")

_HAAR_FACE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def _mesh_to_pixels(landmarks, width: int, height: int) -> list[tuple[float, float]]:
    """Convert MediaPipe landmarks to pixel coordinates."""
    return [(lm.x * width, lm.y * height) for lm in landmarks]


def detect_face_landmarks(image: np.ndarray | None) -> list[tuple[float, float]] | None:
    """
    Robustly detect face landmarks using MediaPipe Face Mesh.
    
    Strategy:
    1. Try original image with high confidence (0.5)
    2. Try upscaled 1.4x with medium confidence (0.35)
    3. Try contrast-enhanced with low confidence (0.25)
    
    Returns landmarks in original image coordinates, or None if all attempts fail.
    """
    _init_detectors()
    
    image = ensure_bgr(image)
    if image is None:
        return None

    h, w = image.shape[:2]
    
    # Prepare variants to try
    variants = [
        (image, "original"),
        (cv2.resize(image, (int(w * 1.4), int(h * 1.4)), interpolation=cv2.INTER_CUBIC), "upscaled_1.4x"),
        (detection_retry_image(image), "contrast_enhanced"),
    ]

    # Try each variant with progressively lower confidence thresholds
    for variant, variant_name in variants:
        if variant is None:
            continue
            
        for mesh, conf_level in zip(_FACE_MESHES, CONFIDENCE_LEVELS):
            if mesh is None:
                continue
            
            rgb = bgr_to_rgb(variant)
            if rgb is None:
                continue
            
            try:
                result = mesh.process(rgb)
                if result.multi_face_landmarks:
                    landmarks = _mesh_to_pixels(result.multi_face_landmarks[0].landmark, w, h)
                    logger.debug(f"Face landmarks detected via {variant_name} at confidence {conf_level}")
                    return landmarks
            except Exception as e:
                logger.debug(f"MediaPipe error on {variant_name} with conf={conf_level}: {e}")
                continue
    
    logger.debug("Face landmarks detection failed on all variants")
    return None


def face_rect_from_landmarks(
    landmarks: list[tuple[float, float]],
    width: int,
    height: int,
    pad_ratio: float = 0.08,
) -> tuple[int, int, int, int]:
    """Calculate face bounding box from landmarks."""
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
    """Detect face bounding box using MediaPipe Face Detection."""
    _init_detectors()
    
    image = ensure_bgr(image)
    if image is None:
        return None
    
    rgb = bgr_to_rgb(image)
    if rgb is None:
        return None
        
    h, w = image.shape[:2]
    
    # Try detectors with different confidence levels
    for detector in _MP_FACE_DETECTORS:
        if detector is None:
            continue
        try:
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
        except Exception as e:
            logger.debug(f"MediaPipe Face Detection error: {e}")
            continue
    
    return None


def detect_face_rect_haar(image: np.ndarray | None) -> tuple[int, int, int, int] | None:
    """Fallback face detection using Haar Cascade."""
    image = ensure_bgr(image)
    if image is None or _HAAR_FACE is None:
        return None
    try:
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
    except Exception as e:
        logger.debug(f"Haar Cascade error: {e}")
        return None


def detect_face_rect(image: np.ndarray | None) -> tuple[int, int, int, int] | None:
    """
    Detect face bounding box with fallback chain:
    1. Use landmarks if available
    2. Try MediaPipe Face Detection
    3. Fallback to Haar Cascade
    """
    landmarks = detect_face_landmarks(image)
    if landmarks is not None:
        h, w = image.shape[:2]
        return face_rect_from_landmarks(landmarks, w, h)
    
    result = detect_face_rect_mp(image)
    if result is not None:
        return result
    
    return detect_face_rect_haar(image)


def compute_eye_center(landmarks: list[tuple[float, float]], indices: list[int]) -> tuple[float, float]:
    """Compute center point of eye landmarks."""
    points = np.array([landmarks[i] for i in indices], dtype=np.float32)
    center = np.mean(points, axis=0)
    return float(center[0]), float(center[1])


def _mean_point(landmarks: list[tuple[float, float]], indices: list[int]) -> tuple[float, float]:
    points = np.array([landmarks[i] for i in indices], dtype=np.float32)
    center = np.mean(points, axis=0)
    return float(center[0]), float(center[1])


def estimate_crown_y_from_landmarks(
    landmarks: list[tuple[float, float]],
    image_height: int,
    face_rect: tuple[int, int, int, int] | None = None,
) -> float | None:
    """
    Estimate the actual crown instead of using landmark 10 directly.

    MediaPipe landmark 10 typically sits around the upper forehead, not the hairline/crown.
    We extrapolate upward using the brow-to-forehead span, then clamp by a face-height-based
    fallback band so the estimate remains stable across slight tilt and hairstyle variation.
    """
    required = LEFT_BROW_LANDMARKS + RIGHT_BROW_LANDMARKS + FOREHEAD_LANDMARKS + [CHIN_LANDMARK]
    if not landmarks or len(landmarks) <= max(required):
        return None

    forehead_y = min(float(landmarks[i][1]) for i in FOREHEAD_LANDMARKS)
    left_brow = _mean_point(landmarks, LEFT_BROW_LANDMARKS)
    right_brow = _mean_point(landmarks, RIGHT_BROW_LANDMARKS)
    brow_center_y = (left_brow[1] + right_brow[1]) / 2.0
    chin_y = float(landmarks[CHIN_LANDMARK][1])

    if face_rect is None:
        xs = [x for x, _ in landmarks]
        ys = [y for _, y in landmarks]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        face_rect = (
            int(np.floor(x_min)),
            int(np.floor(y_min)),
            int(max(1.0, x_max - x_min)),
            int(max(1.0, y_max - y_min)),
        )

    _, _, _, fh = face_rect
    brow_to_forehead = max(6.0, brow_center_y - forehead_y)
    face_span = max(1.0, chin_y - forehead_y)
    min_extension = max(0.22 * fh, 0.12 * face_span)
    max_extension = max(0.36 * fh, min_extension + 1.0)
    extension = np.clip(brow_to_forehead * 1.45, min_extension, max_extension)
    crown_y = max(0.0, forehead_y - float(extension))
    return min(crown_y, forehead_y - 2.0)


def estimate_head_geometry_from_landmarks(
    landmarks: list[tuple[float, float]],
    image_height: int,
    face_rect: tuple[int, int, int, int] | None = None,
) -> tuple[float | None, float | None, float | None]:
    """Calculate head percent and eye level using an estimated crown position."""
    if not landmarks:
        return None, None, None
    if len(landmarks) <= max(CHIN_LANDMARK, TOP_HEAD_LANDMARK):
        return None, None, None

    crown_y = estimate_crown_y_from_landmarks(landmarks, image_height, face_rect=face_rect)
    if crown_y is None:
        crown_y = float(landmarks[TOP_HEAD_LANDMARK][1])

    chin_y = float(landmarks[CHIN_LANDMARK][1])
    head_percent = ((chin_y - crown_y) / float(image_height)) * 100.0

    left_eye = compute_eye_center(landmarks, LEFT_EYE_LANDMARKS)
    right_eye = compute_eye_center(landmarks, RIGHT_EYE_LANDMARKS)
    eye_center_y = (left_eye[1] + right_eye[1]) / 2.0
    eye_level = ((float(image_height) - eye_center_y) / float(image_height)) * 100.0

    return float(head_percent), float(eye_level), float(crown_y)


def approximate_geometry_from_face_rect(
    face_rect: tuple[int, int, int, int],
    image_height: int,
) -> tuple[float, float, float, float]:
    """Estimate head percent and eye level from face bounding box."""
    x, y, fw, fh = face_rect
    top_y = max(0.0, y - 0.30 * fh)
    chin_y = min(float(image_height - 1), y + 1.02 * fh)
    eye_center_y = y + 0.38 * fh
    head_percent = ((chin_y - top_y) / float(image_height)) * 100.0
    eye_level = ((float(image_height) - eye_center_y) / float(image_height)) * 100.0
    return float(head_percent), float(eye_level), float(eye_center_y), float(top_y)


def face_geometry_score(head_percent: float, eye_level: float) -> float:
    """Calculate geometry score from head percent and eye level."""
    head_target = sum(TARGET_HEAD_PERCENT) / 2.0
    eye_target = sum(TARGET_EYE_LEVEL) / 2.0
    head_score = clamp(1.0 - abs(head_percent - head_target) / 18.0)
    eye_score = clamp(1.0 - abs(eye_level - eye_target) / 18.0)
    return float(np.mean([head_score, eye_score]))


def validate_face_geometry(
    image,
    mode: str = DEFAULT_MODE,
    *,
    enforce_rules: bool = True,
    post_fix: bool = False,
):
    """
    Validate face geometry using landmarks or face box estimation.
    
    This function is called on the final 600x600 cropped image.
    It determines if the face is properly positioned.
    """
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

    if post_fix:
        tolerance = 1.0 if mode == STRICT_MODE else 1.5
        head_min -= tolerance
        head_max += tolerance
        eye_min -= tolerance
        eye_max += tolerance

    # Detect landmarks first
    landmarks = detect_face_landmarks(image)
    if landmarks is not None:
        metrics["landmarks_found"] = True
        face_rect = face_rect_from_landmarks(landmarks, w, h)
        head_percent, eye_level, crown_y = estimate_head_geometry_from_landmarks(landmarks, h, face_rect=face_rect)
        logger.debug("Face geometry from MediaPipe landmarks")
    else:
        # Fallback to face box detection
        metrics["landmarks_found"] = False
        face_rect = detect_face_rect_mp(image) or detect_face_rect_haar(image)
        
        if face_rect is None:
            # No face detected at all
            issues.append("No face detected in image")
            feature_scores["face_geometry_score"] = 0.35
            logger.warning("Face detection failed completely")
            return {"issues": issues, "warnings": warnings, "metrics": metrics, "feature_scores": feature_scores}
        
        # Use face box for geometry estimation
        head_percent, eye_level, eye_center_y, crown_y = approximate_geometry_from_face_rect(face_rect, h)
        metrics["eye_center_y"] = round(eye_center_y, 2)
        logger.debug("Face geometry estimated from face box (landmarks not found)")

    metrics["face_rect"] = {"x": face_rect[0], "y": face_rect[1], "w": face_rect[2], "h": face_rect[3]}
    metrics["head_percent"] = round(float(head_percent), 2)
    metrics["eye_level"] = round(float(eye_level), 2)
    
    # Add landmark coordinates for visualization
    if landmarks is not None and len(landmarks) > max(TOP_HEAD_LANDMARK, CHIN_LANDMARK):
        metrics["face_top_y"] = round(float(crown_y), 2)
        metrics["face_chin_y"] = round(float(landmarks[CHIN_LANDMARK][1]), 2)
        # Nose tip is landmark 1
        metrics["face_nose_y"] = round(float(landmarks[1][1]), 2) if len(landmarks) > 1 else None
    else:
        # Estimate from face rect if using fallback
        if face_rect is not None:
            x, y, fw, fh = face_rect
            metrics["face_top_y"] = round(float(crown_y), 2)
            metrics["face_chin_y"] = round(float(min(float(h - 1), y + 1.02 * fh)), 2)
            metrics["face_nose_y"] = round(float(y + 0.38 * fh), 2)

    # Check geometry constraints
    if enforce_rules:
        if head_percent < head_min or head_percent > head_max:
            deviation = min(abs(head_percent - head_min), abs(head_percent - head_max))
            target = warnings if mode == BALANCED_MODE or (post_fix and deviation <= 1.5) else issues
            target.append(f"Head percent is outside allowed range ({head_percent:.1f}%)")

        if eye_level < eye_min or eye_level > eye_max:
            deviation = min(abs(eye_level - eye_min), abs(eye_level - eye_max))
            target = warnings if mode == BALANCED_MODE or (post_fix and deviation <= 1.5) else issues
            target.append(f"Eye level is outside allowed range ({eye_level:.1f}%)")

    # Calculate score (slightly penalize if using face box instead of landmarks)
    base = face_geometry_score(head_percent, eye_level)
    if not metrics["landmarks_found"]:
        base *= 0.90  # 10% penalty for face box estimation
    
    feature_scores["face_geometry_score"] = round(float(base), 3)

    return {"issues": issues, "warnings": warnings, "metrics": metrics, "feature_scores": feature_scores}
