import cv2
import numpy as np

from config import BALANCED_MODE, BALANCED_THRESHOLDS, STRICT_MODE


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(min(value, maximum), minimum)


def compute_background_variance(gray: np.ndarray, face_rect=None) -> float:
    h, w = gray.shape[:2]
    mask = np.ones((h, w), dtype=bool)
    if face_rect is not None:
        x, y, fw, fh = face_rect
        mask[y:y + fh, x:x + fw] = False

    background_pixels = gray[mask]
    if background_pixels.size == 0:
        return float(np.var(gray))
    return float(np.var(background_pixels))


def compute_edge_density(gray: np.ndarray, face_rect=None) -> float:
    h, w = gray.shape[:2]
    mask = np.ones((h, w), dtype=bool)
    if face_rect is not None:
        x, y, fw, fh = face_rect
        mask[y:y + fh, x:x + fw] = False

    edges = cv2.Canny(gray, 80, 180).astype(bool)
    valid_pixels = mask.sum()
    if valid_pixels == 0:
        return 0.0
    return float(np.count_nonzero(edges & mask) / valid_pixels)


def validate_background(img, face_rect=None, mode: str = BALANCED_MODE):
    issues = []
    warnings = []
    metrics = {}
    feature_scores = {}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    variance = compute_background_variance(gray, face_rect=face_rect)
    edge_density = compute_edge_density(gray, face_rect=face_rect)

    metrics["background_variance"] = round(variance, 2)
    metrics["background_edge_density"] = round(edge_density, 4)

    color_uniformity_score = clamp(1.0 - min(variance, 9000.0) / 9000.0)
    edge_score = clamp(1.0 - edge_density * 8.0)
    background_score = clamp(np.mean([color_uniformity_score, edge_score]))
    feature_scores["background_score"] = round(background_score, 3)

    thresholds = STRICT_MODE if mode == STRICT_MODE else BALANCED_THRESHOLDS
    bg_limit = thresholds["background_variance"]

    if variance > bg_limit:
        if mode == BALANCED_MODE and variance <= bg_limit + 400.0:
            warnings.append(f"Background variance is slightly elevated ({variance:.0f}).")
        else:
            issues.append(f"Background variance is too high ({variance:.0f}).")

    if edge_density > 0.035:
        issues.append("Background contains visible structure or edges.")

    return {
        "issues": issues,
        "warnings": warnings,
        "metrics": metrics,
        "feature_scores": feature_scores,
    }
