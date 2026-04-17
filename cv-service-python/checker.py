from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from auto_fix import auto_crop_to_dv_standard
from blur_analysis import validate_blur
from config import (
    BALANCED_MODE,
    BALANCED_THRESHOLDS,
    DEFAULT_MODE,
    SCORE_MIN_FLOOR,
    SCORE_PASS_THRESHOLD,
    SCORE_WARNING_THRESHOLD,
    STRICT_MODE,
    STRICT_THRESHOLDS,
    WEIGHT_BACKGROUND,
    WEIGHT_BLUR,
    WEIGHT_FACE_GEOMETRY,
    WEIGHT_LIGHTING,
)
from face_analyzer import validate_face_geometry
from image_utils import ensure_bgr
from lighting_analysis import validate_lighting


def _clamp(value: float, min_v: float = 0.0, max_v: float = 1.0) -> float:
    return max(min(value, max_v), min_v)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _background_ring_mask(height: int, width: int, face_rect: tuple[int, int, int, int] | None) -> np.ndarray:
    """
    Background is measured on outer frame only, excluding face area.
    This is robust for passport-like photos where background is near image borders.
    """
    border = max(18, int(min(height, width) * 0.08))
    mask = np.zeros((height, width), dtype=bool)
    mask[:border, :] = True
    mask[-border:, :] = True
    mask[:, :border] = True
    mask[:, -border:] = True
    if face_rect is not None:
        x, y, fw, fh = face_rect
        x2 = min(width, x + fw)
        y2 = min(height, y + fh)
        mask[max(0, y):y2, max(0, x):x2] = False
    return mask


def _validate_background_soft(img_bgr: np.ndarray, face_rect: tuple[int, int, int, int] | None, mode: str):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    mask = _background_ring_mask(h, w, face_rect)
    pixels = gray[mask]
    variance = float(np.var(pixels)) if pixels.size else float(np.var(gray))
    edges = cv2.Canny(gray, 80, 180).astype(bool)
    edge_density = float(np.count_nonzero(edges & mask) / max(1, int(mask.sum())))

    thresholds = STRICT_THRESHOLDS if mode == STRICT_MODE else BALANCED_THRESHOLDS
    variance_max = 4200 if mode == BALANCED_MODE else 3500
    issues: list[str] = []
    warnings: list[str] = []
    if variance > variance_max:
        if mode == BALANCED_MODE and variance <= variance_max + 250.0:
            warnings.append(f"Background variance is slightly elevated ({variance:.0f}).")
        else:
            issues.append(f"Background variance is too high ({variance:.0f}).")
    if edge_density > 0.05:
        warnings.append("Background has noticeable structure near frame edges.")

    variance_score = _clamp(1.0 - variance / (variance_max + 1800.0))
    edge_score = _clamp(1.0 - edge_density * 10.0)
    return {
        "issues": issues,
        "warnings": warnings,
        "metrics": {
            "background_variance": round(variance, 2),
            "background_edge_density": round(edge_density, 4),
        },
        "feature_scores": {"background_score": round(float(np.mean([variance_score, edge_score])), 3)},
    }


def _compute_score(features: dict[str, float]) -> float:
    weighted = (
        features.get("face_geometry_score", 0.0) * WEIGHT_FACE_GEOMETRY
        + features.get("background_score", 0.0) * WEIGHT_BACKGROUND
        + features.get("blur_score", 0.0) * WEIGHT_BLUR
        + features.get("lighting_score", 0.0) * WEIGHT_LIGHTING
    )
    raw = _clamp(weighted) * 100.0
    return float(max(SCORE_MIN_FLOOR, round(raw, 1)))


def _decision(score: float, issues: list[str]) -> tuple[bool, str, str]:
    if issues:
        return False, "Photo has critical issues that prevent validation", "FAIL"
    if score >= SCORE_PASS_THRESHOLD:
        return True, "Photo passes DV validation standards", "PASS"
    if score >= SCORE_WARNING_THRESHOLD:
        return True, "Photo passes with minor quality concerns", "WARNING"
    return False, "Photo quality is below minimum standards", "FAIL"


def analyze_photo(image_bgr: np.ndarray, mode: str = DEFAULT_MODE) -> dict[str, Any]:
    """
    Full checker pipeline:
    1) crop-only auto-fix to 600x600,
    2) run all checks on final image only,
    3) compute stable weighted score.
    """
    img = ensure_bgr(image_bgr)
    if img is None:
        raise ValueError("Invalid image")

    cropped, crop_applied, crop_info = auto_crop_to_dv_standard(img)

    if np.max(cropped) < 10:  # полностью чёрное
        cropped = cv2.convertScaleAbs(cropped, alpha=1.1, beta=10)

    issues: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}
    features: dict[str, float] = {}

    face = validate_face_geometry(cropped, mode=mode)
    issues.extend(face["issues"])
    warnings.extend(face["warnings"])
    metrics.update(face["metrics"])
    features.update(face["feature_scores"])

    face_rect = None
    fr = metrics.get("face_rect")
    if isinstance(fr, dict) and all(k in fr for k in ("x", "y", "w", "h")):
        face_rect = (int(fr["x"]), int(fr["y"]), int(fr["w"]), int(fr["h"]))

    background = _validate_background_soft(cropped, face_rect, mode=mode)
    issues.extend(background["issues"])
    warnings.extend(background["warnings"])
    metrics.update(background["metrics"])
    features.update(background["feature_scores"])

    blur = validate_blur(cropped, mode=mode)
    issues.extend(blur["issues"])
    warnings.extend(blur["warnings"])
    metrics.update(blur["metrics"])
    features.update(blur["feature_scores"])

    lighting = validate_lighting(cropped, face_rect=face_rect, mode=mode)
    issues.extend(lighting["issues"])
    warnings.extend(lighting["warnings"])
    metrics.update(lighting["metrics"])
    features.update(lighting["feature_scores"])

    # Защита от полного краха
    if not features or "face_geometry_score" not in features:
        features["face_geometry_score"] = 0.4
        features["background_score"] = 0.6
        features["blur_score"] = 0.7
        features["lighting_score"] = 0.6

    score = _compute_score(features)
    valid, reason, status = _decision(score, issues)

    return {
        "valid": valid,
        "score": float(score),
        "pass_probability": float(score),
        "features": features,
        "issues": _dedupe(issues),
        "warnings": _dedupe(warnings),
        "decision_reason": reason,
        "metrics": metrics,
        "detail": {
            "status": status,
            "after_crop": crop_applied,
            "crop_info": crop_info,
        },
        "cropped_image": cropped,
    }
