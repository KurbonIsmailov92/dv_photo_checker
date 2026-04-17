import cv2
import numpy as np

from config import BALANCED_MODE, BALANCED_THRESHOLDS, STRICT_MODE, STRICT_THRESHOLDS


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(min(value, maximum), minimum)


def _median_laplacian_variance(gray: np.ndarray) -> float:
    h, w = gray.shape[:2]
    tile = 4
    variances = []
    for row in range(tile):
        for col in range(tile):
            y0 = int(h * row / tile)
            y1 = int(h * (row + 1) / tile)
            x0 = int(w * col / tile)
            x1 = int(w * (col + 1) / tile)
            patch = gray[y0:y1, x0:x1]
            if patch.size == 0:
                continue
            variances.append(float(cv2.Laplacian(patch, cv2.CV_64F).var()))
    return float(np.median(variances)) if variances else 0.0


def validate_blur(img, mode: str = BALANCED_MODE):
    issues = []
    warnings = []
    metrics = {}
    feature_scores = {}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur_variance = _median_laplacian_variance(gray)
    metrics["blur_variance"] = round(blur_variance, 2)

    thresholds = STRICT_THRESHOLDS if mode == STRICT_MODE else BALANCED_THRESHOLDS
    blur_threshold = thresholds["blur_variance_min"]
    blur_score = clamp((blur_variance - 30.0) / 140.0)
    feature_scores["blur_score"] = round(blur_score, 3)

    if blur_variance < blur_threshold:
        if mode == BALANCED_MODE and blur_variance >= blur_threshold - 6.0:
            warnings.append(f"Blur variance is slightly low ({blur_variance:.1f}), but the image may still be acceptable.")
        else:
            issues.append(f"Blur variance is too low ({blur_variance:.1f}).")

    return {
        "issues": issues,
        "warnings": warnings,
        "metrics": metrics,
        "feature_scores": feature_scores,
    }
