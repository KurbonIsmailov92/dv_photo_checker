import cv2
import numpy as np

from config import BALANCED_MODE, BALANCED_THRESHOLDS, STRICT_MODE


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(min(value, maximum), minimum)


def _face_shadow_variance(gray: np.ndarray, face_rect=None) -> float:
    if face_rect is None:
        return float(np.var(gray))
    x, y, fw, fh = face_rect
    face_region = gray[y:y + fh, x:x + fw]
    if face_region.size == 0:
        return float(np.var(gray))
    return float(np.var(face_region))


def validate_lighting(img, face_rect=None, mode: str = BALANCED_MODE):
    issues = []
    warnings = []
    metrics = {}
    feature_scores = {}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(np.mean(gray))
    brightness_variance = float(np.var(gray))
    shadow_variance = _face_shadow_variance(gray, face_rect=face_rect)

    metrics["mean_brightness"] = round(mean_brightness, 2)
    metrics["brightness_variance"] = round(brightness_variance, 2)
    metrics["shadow_variance"] = round(shadow_variance, 2)

    hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten()
    hist_score = clamp(-np.sum([p * np.log2(p) for p in hist / hist.sum() if p > 0]) / 5.0)

    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.sqrt(np.square(grad_x) + np.square(grad_y))
    gradient_score = clamp(1.0 - float(np.mean(grad_mag)) / 70.0)

    lighting_score = clamp(np.mean([hist_score, gradient_score, 1.0 - min(shadow_variance, 9000.0) / 9000.0]))
    feature_scores["lighting_score"] = round(lighting_score, 3)

    thresholds = STRICT_MODE if mode == STRICT_MODE else BALANCED_THRESHOLDS
    shadow_limit = thresholds["shadow_variance"]

    if shadow_variance > shadow_limit:
        if mode == BALANCED_MODE and shadow_variance <= shadow_limit + 600.0:
            warnings.append(f"Face shadow variance is elevated ({shadow_variance:.0f}), but may still be acceptable.")
        else:
            issues.append(f"Face shadow variance is too high ({shadow_variance:.0f}).")

    if mean_brightness < 55:
        warnings.append(f"Image is a bit dark ({mean_brightness:.1f}).")
    elif mean_brightness > 235:
        warnings.append(f"Image is a bit bright ({mean_brightness:.1f}).")

    return {
        "issues": issues,
        "warnings": warnings,
        "metrics": metrics,
        "feature_scores": feature_scores,
    }
