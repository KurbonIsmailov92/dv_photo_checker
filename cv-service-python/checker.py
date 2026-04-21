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
    """Ограничивает значение в диапазоне."""
    return max(min(value, max_v), min_v)


def _dedupe(items: list[str]) -> list[str]:
    """Удаляет дубликаты, сохраняя порядок."""
    return list(dict.fromkeys(items))


def _background_ring_mask(height: int, width: int, face_rect: tuple[int, int, int, int] | None) -> np.ndarray:
    """
    Создаёт маску только для внешней рамки изображения (background),
    исключая область лица.
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


def _validate_background_soft(img_bgr: np.ndarray, face_rect: tuple | None, mode: str):
    """Проверка фона только по внешней рамке."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    mask = _background_ring_mask(h, w, face_rect)
    pixels = gray[mask]

    variance = float(np.var(pixels)) if pixels.size > 0 else float(np.var(gray))
    edges = cv2.Canny(gray, 80, 180).astype(bool)
    edge_density = float(np.count_nonzero(edges & mask) / max(1, int(mask.sum())))

    variance_max = 4200 if mode == BALANCED_MODE else 3500

    issues: list[str] = []
    warnings: list[str] = []

    if variance > variance_max:
        if mode == BALANCED_MODE and variance <= variance_max + 300:
            warnings.append(f"Background variance is slightly elevated ({variance:.0f}).")
        else:
            issues.append(f"Background variance is too high ({variance:.0f}).")

    if edge_density > 0.06:
        warnings.append("Background has noticeable structures near edges.")

    variance_score = _clamp(1.0 - variance / (variance_max + 2000.0))
    edge_score = _clamp(1.0 - edge_density * 12.0)

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
    """Вычисление итогового weighted score."""
    weighted = (
        features.get("face_geometry_score", 0.45) * WEIGHT_FACE_GEOMETRY +
        features.get("background_score", 0.60) * WEIGHT_BACKGROUND +
        features.get("blur_score", 0.70) * WEIGHT_BLUR +
        features.get("lighting_score", 0.60) * WEIGHT_LIGHTING
    )
    raw = _clamp(weighted) * 100.0
    return float(max(SCORE_MIN_FLOOR, round(raw, 1)))


def _decision(score: float, issues: list[str]) -> tuple[bool, str, str]:
    if issues:
        return False, "Photo has critical issues", "FAIL"
    if score >= SCORE_PASS_THRESHOLD:
        return True, "Photo passes DV standards", "PASS"
    if score >= SCORE_WARNING_THRESHOLD:
        return True, "Photo passes with minor concerns", "WARNING"
    return False, "Photo quality is below standards", "FAIL"


def analyze_photo(image_bgr: np.ndarray, mode: str = DEFAULT_MODE) -> dict[str, Any]:
def analyze_photo(image_input, mode: str = DEFAULT_MODE) -> dict[str, Any]:
    """
    Основная функция анализа фото для DV Lottery.
    Поддерживает как numpy array, так и base64 строку.
    """
    try:
        # === КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: обработка base64 ===
        if isinstance(image_input, str):
            from image_utils import decode_upload_image
            image_bgr = decode_upload_image(image_input)
        else:
            image_bgr = image_input

        img = ensure_bgr(image_bgr)
        if img is None or img.size == 0:
            raise ValueError("Invalid or empty image received")

        # 1. Авто-кроп (только обрезка + resize)
        cropped, crop_applied, crop_info = auto_crop_to_dv_standard(img)

        # Защита от полностью тёмного изображения
        if np.max(cropped) < 15:
            cropped = cv2.convertScaleAbs(cropped, alpha=1.15, beta=12)

        issues: list[str] = []
        warnings: list[str] = []
        metrics: dict[str, Any] = {}
        features: dict[str, float] = {}

        # 2. Анализ лица
        face = validate_face_geometry(cropped, mode=mode)
        issues.extend(face.get("issues", []))
        warnings.extend(face.get("warnings", []))
        metrics.update(face.get("metrics", {}))
        features.update(face.get("feature_scores", {}))

        # 3. Безопасное извлечение face_rect
        face_rect = None
        fr = metrics.get("face_rect")
        if isinstance(fr, (dict, list, tuple)) and len(fr) >= 4:
            try:
                if isinstance(fr, dict):
                    face_rect = (
                        int(fr.get("x", 0)),
                        int(fr.get("y", 0)),
                        int(fr.get("w", 0)),
                        int(fr.get("h", 0))
                    )
                else:
                    face_rect = tuple(int(x) for x in fr[:4])
            except (ValueError, TypeError):
                face_rect = None

        # 4. Остальные проверки
        background = _validate_background_soft(cropped, face_rect, mode)
        issues.extend(background.get("issues", []))
        warnings.extend(background.get("warnings", []))
        metrics.update(background.get("metrics", {}))
        features.update(background.get("feature_scores", {}))

        blur = validate_blur(cropped, mode=mode)
        issues.extend(blur.get("issues", []))
        warnings.extend(blur.get("warnings", []))
        metrics.update(blur.get("metrics", {}))
        features.update(blur.get("feature_scores", {}))s

        lighting = validate_lighting(cropped, face_rect=face_rect, mode=mode)
        issues.extend(lighting.get("issues", []))
        warnings.extend(lighting.get("warnings", []))
        metrics.update(lighting.get("metrics", {}))
        features.update(lighting.get("feature_scores", {}))

        # 5. Защита от полного краха scoring
        if not features or "face_geometry_score" not in features:
            features["face_geometry_score"] = 0.45
            features["background_score"] = 0.65
            features["blur_score"] = 0.70
            features["lighting_score"] = 0.60

        score = _compute_score(features)
        valid, reason, status = _decision(score, issues)

        return {
            "valid": valid,
            "score": round(float(score), 1),
            "status": status,
            "issues": _dedupe(issues),
            "warnings": _dedupe(warnings),
            "decision_reason": reason,
            "metrics": metrics,
            "detail": {
                "after_crop": bool(crop_applied),
                "crop_info": crop_info,
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "valid": False,
            "score": 35.0,
            "status": "ERROR",
            "issues": [f"Processing error: {str(e)}"],
            "warnings": [],
            "decision_reason": "Internal server error during analysis",
            "metrics": {}
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "valid": False,
            "score": 35.0,
            "status": "ERROR",
            "issues": [f"Processing error: {str(e)}"],
            "warnings": [],
            "decision_reason": "Internal server error during analysis",
            "metrics": {}
        }