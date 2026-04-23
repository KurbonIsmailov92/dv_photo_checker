from __future__ import annotations

import cv2
import numpy as np

from config import BALANCED_MODE, STRICT_MODE


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(min(value, maximum), minimum)


def _corner_mask(h: int, w: int, corner: int) -> np.ndarray:
    mask = np.zeros((h, w), dtype=bool)
    c = max(4, min(corner, h // 3, w // 3))
    mask[:c, :c] = True
    mask[:c, -c:] = True
    mask[-c:, :c] = True
    mask[-c:, -c:] = True
    return mask


def _subject_exclusion_mask(h: int, w: int, face_rect=None) -> np.ndarray:
    mask = np.zeros((h, w), dtype=bool)
    if face_rect is None:
        return mask

    x, y, fw, fh = [int(v) for v in face_rect]
    expand_x = int(max(24, fw * 0.9))
    expand_top = int(max(18, fh * 0.55))
    expand_bottom = int(max(42, fh * 1.9))

    x0 = max(0, x - expand_x)
    y0 = max(0, y - expand_top)
    x1 = min(w, x + fw + expand_x)
    y1 = min(h, y + fh + expand_bottom)
    mask[y0:y1, x0:x1] = True
    return mask


def _background_mask(h: int, w: int, face_rect=None, crop_applied: bool = False) -> np.ndarray:
    border_ratio = 0.05 if crop_applied else 0.08
    border = max(16, int(min(h, w) * border_ratio))

    mask = np.zeros((h, w), dtype=bool)
    mask[:border, :] = True
    mask[-border:, :] = True
    mask[:, :border] = True
    mask[:, -border:] = True

    subject_mask = _subject_exclusion_mask(h, w, face_rect=face_rect)
    mask &= ~subject_mask

    minimum_pixels = max(1, int(h * w * 0.035))
    if int(mask.sum()) < minimum_pixels:
        mask = _corner_mask(h, w, max(border, int(min(h, w) * 0.13)))
        mask &= ~subject_mask

    if int(mask.sum()) == 0:
        mask = _corner_mask(h, w, max(12, int(min(h, w) * 0.1)))

    return mask


def _background_stats(gray: np.ndarray, mask: np.ndarray) -> tuple[float, float, float, float]:
    pixels = gray[mask]
    if pixels.size == 0:
        pixels = gray.reshape(-1)

    p05, p50, p95 = np.percentile(pixels, [5, 50, 95])
    variance = float(np.var(pixels))
    mad = float(np.median(np.abs(pixels - p50)))
    tonal_range = float(p95 - p05)
    mean_value = float(np.mean(pixels))
    return variance, tonal_range, mad, mean_value


def compute_background_variance(gray: np.ndarray, face_rect=None, crop_applied: bool = False) -> float:
    mask = _background_mask(*gray.shape[:2], face_rect=face_rect, crop_applied=crop_applied)
    variance, _, _, _ = _background_stats(gray, mask)
    return variance


def compute_edge_density(gray: np.ndarray, face_rect=None, crop_applied: bool = False) -> float:
    mask = _background_mask(*gray.shape[:2], face_rect=face_rect, crop_applied=crop_applied)
    blurred = cv2.GaussianBlur(gray, (7, 7), 1.2)
    edges = cv2.Canny(blurred, 72, 156)
    edges = cv2.morphologyEx(edges, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8))
    edge_pixels = (edges > 0).astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(edge_pixels, connectivity=8)
    filtered = np.zeros_like(edge_pixels, dtype=bool)
    min_component_area = max(10, int(min(gray.shape[:2]) * 0.012))
    for label in range(1, num_labels):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area >= min_component_area:
            filtered[labels == label] = True
    valid_pixels = int(mask.sum())
    if valid_pixels == 0:
        return 0.0
    return float(np.count_nonzero(filtered & mask) / valid_pixels)


def validate_background(
    img,
    face_rect=None,
    mode: str = BALANCED_MODE,
    *,
    crop_applied: bool = False,
    context: str = "initial",
):
    issues = []
    warnings = []
    metrics = {}
    feature_scores = {}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    mask = _background_mask(h, w, face_rect=face_rect, crop_applied=crop_applied)
    variance, tonal_range, mad, mean_value = _background_stats(gray, mask)
    edge_density = compute_edge_density(gray, face_rect=face_rect, crop_applied=crop_applied)

    metrics["background_variance"] = round(variance, 2)
    metrics["background_edge_density"] = round(edge_density, 4)
    metrics["background_tonal_range"] = round(tonal_range, 2)
    metrics["background_mad"] = round(mad, 2)
    metrics["background_mean_brightness"] = round(mean_value, 2)
    metrics["background_mask_ratio"] = round(float(mask.mean()), 4)

    uniformity_reference = 76.0 if crop_applied else 68.0
    edge_reference = 0.070 if crop_applied else 0.058
    uniformity_score = clamp(1.0 - tonal_range / uniformity_reference)
    edge_score = clamp(1.0 - edge_density / edge_reference)
    background_score = clamp(float(np.mean([uniformity_score, edge_score])))
    feature_scores["background_score"] = round(background_score, 3)

    if mode == STRICT_MODE:
        tonal_warn = 30.0
        tonal_issue = 42.0
        edge_warn = 0.026
        edge_issue = 0.041
    else:
        tonal_warn = 34.0
        tonal_issue = 48.0
        edge_warn = 0.030
        edge_issue = 0.046

    if context == "post_fix" and crop_applied:
        tonal_warn += 8.0
        tonal_issue += 10.0
        edge_warn += 0.012
        edge_issue += 0.014

    if tonal_range > tonal_issue:
        issues.append(f"Background tonal range is too wide ({tonal_range:.1f}).")
    elif tonal_range > tonal_warn:
        warnings.append(f"Background tonal range is slightly elevated ({tonal_range:.1f}).")

    if edge_density > edge_issue:
        issues.append("Background contains visible structure or edges.")
    elif edge_density > edge_warn:
        warnings.append("Background shows mild edge structure near the frame border.")

    if mean_value < 120:
        warnings.append(f"Background is darker than expected ({mean_value:.1f}).")

    return {
        "issues": issues,
        "warnings": warnings,
        "metrics": metrics,
        "feature_scores": feature_scores,
    }
