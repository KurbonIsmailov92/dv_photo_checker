from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from auto_fix import auto_crop_to_dv_standard
from background_analysis import validate_background
from blur_analysis import validate_blur
from config import (
    DEFAULT_MODE,
    SCORE_MIN_FLOOR,
    SCORE_PASS_THRESHOLD,
    SCORE_WARNING_THRESHOLD,
    WEIGHT_BACKGROUND,
    WEIGHT_BLUR,
    WEIGHT_FACE_GEOMETRY,
    WEIGHT_LIGHTING,
)
from face_analyzer import validate_face_geometry
from image_utils import decode_upload_image, ensure_bgr
from lighting_analysis import validate_lighting

SOURCE_STAGE = "initial_validation"
POST_FIX_STAGE = "post_fix_validation"


def _clamp(value: float, min_v: float = 0.0, max_v: float = 1.0) -> float:
    return max(min(value, max_v), min_v)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _extract_face_rect(metrics: dict[str, Any]) -> tuple[int, int, int, int] | None:
    fr = metrics.get("face_rect")
    if not isinstance(fr, (dict, list, tuple)):
        return None

    try:
        if isinstance(fr, dict):
            return (
                int(fr.get("x", 0)),
                int(fr.get("y", 0)),
                int(fr.get("w", 0)),
                int(fr.get("h", 0)),
            )
        if len(fr) >= 4:
            return tuple(int(x) for x in fr[:4])
    except (TypeError, ValueError):
        return None

    return None


def _decode_image_input(image_input) -> np.ndarray | None:
    if isinstance(image_input, np.ndarray):
        return image_input
    return decode_upload_image(image_input)


def _merge_component_results(
    components: dict[str, dict[str, Any]],
    names: tuple[str, ...],
) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}
    feature_scores: dict[str, float] = {}

    for name in names:
        component = components.get(name, {})
        issues.extend(component.get("issues", []))
        warnings.extend(component.get("warnings", []))
        metrics.update(component.get("metrics", {}))
        feature_scores.update(component.get("feature_scores", {}))

    return {
        "issues": _dedupe(issues),
        "warnings": _dedupe(warnings),
        "metrics": metrics,
        "feature_scores": feature_scores,
    }


def _run_validation_components(
    image: np.ndarray,
    mode: str,
    *,
    stage: str,
    crop_applied: bool,
    enforce_geometry: bool,
) -> dict[str, dict[str, Any]]:
    face = validate_face_geometry(
        image,
        mode=mode,
        enforce_rules=enforce_geometry,
        post_fix=(stage == POST_FIX_STAGE and crop_applied),
    )
    face_rect = _extract_face_rect(face.get("metrics", {}))

    background = validate_background(
        image,
        face_rect=face_rect,
        mode=mode,
        crop_applied=crop_applied,
        context="post_fix" if stage == POST_FIX_STAGE else "initial",
    )
    blur = validate_blur(image, mode=mode)
    lighting = validate_lighting(
        image,
        face_rect=face_rect,
        mode=mode,
        crop_applied=crop_applied,
        context="post_fix" if stage == POST_FIX_STAGE else "initial",
    )

    return {
        "face": face,
        "background": background,
        "blur": blur,
        "lighting": lighting,
    }


def _score_from_features(features: dict[str, float]) -> float:
    weighted = (
        features.get("face_geometry_score", 0.45) * WEIGHT_FACE_GEOMETRY
        + features.get("background_score", 0.60) * WEIGHT_BACKGROUND
        + features.get("blur_score", 0.70) * WEIGHT_BLUR
        + features.get("lighting_score", 0.60) * WEIGHT_LIGHTING
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


def _select_final_components(
    source_components: dict[str, dict[str, Any]],
    post_fix_components: dict[str, dict[str, Any]],
    *,
    crop_applied: bool,
) -> dict[str, dict[str, Any]]:
    if not crop_applied:
        return post_fix_components

    return {
        "face": post_fix_components["face"],
        "background": source_components["background"],
        "blur": source_components["blur"],
        "lighting": source_components["lighting"],
    }


def analyze_photo(image_input, mode: str = DEFAULT_MODE) -> dict[str, Any]:
    """
    End-to-end DV validation pipeline:
    1. initial validation of source quality
    2. auto-fix / crop
    3. post-fix validation of final framing
    """
    try:
        image_bgr = _decode_image_input(image_input)
        img = ensure_bgr(image_bgr)
        if img is None or img.size == 0:
            raise ValueError("Invalid or empty image received")

        source_components = _run_validation_components(
            img,
            mode,
            stage=SOURCE_STAGE,
            crop_applied=False,
            enforce_geometry=False,
        )
        source_summary = _merge_component_results(source_components, ("face", "background", "blur", "lighting"))

        cropped, crop_applied, crop_info = auto_crop_to_dv_standard(img)
        if np.max(cropped) < 15:
            cropped = cv2.convertScaleAbs(cropped, alpha=1.15, beta=12)

        post_fix_components = _run_validation_components(
            cropped,
            mode,
            stage=POST_FIX_STAGE,
            crop_applied=bool(crop_applied),
            enforce_geometry=True,
        )
        post_fix_summary = _merge_component_results(post_fix_components, ("face", "background", "blur", "lighting"))

        final_components = _select_final_components(
            source_components,
            post_fix_components,
            crop_applied=bool(crop_applied),
        )
        final_summary = _merge_component_results(final_components, ("face", "background", "blur", "lighting"))

        if "face_geometry_score" not in final_summary["feature_scores"]:
            final_summary["feature_scores"]["face_geometry_score"] = 0.45
        if "background_score" not in final_summary["feature_scores"]:
            final_summary["feature_scores"]["background_score"] = 0.65
        if "blur_score" not in final_summary["feature_scores"]:
            final_summary["feature_scores"]["blur_score"] = 0.70
        if "lighting_score" not in final_summary["feature_scores"]:
            final_summary["feature_scores"]["lighting_score"] = 0.60

        score = _score_from_features(final_summary["feature_scores"])
        valid, reason, status = _decision(score, final_summary["issues"])

        return {
            "valid": valid,
            "score": round(float(score), 1),
            "status": status,
            "issues": final_summary["issues"],
            "warnings": final_summary["warnings"],
            "decision_reason": reason,
            "metrics": final_summary["metrics"],
            "detail": {
                "after_crop": bool(crop_applied),
                "crop_info": crop_info,
                "quality_source": SOURCE_STAGE if crop_applied else POST_FIX_STAGE,
                "pipeline": {
                    SOURCE_STAGE: source_summary,
                    "auto_fix": {
                        "applied": bool(crop_applied),
                        "crop_info": crop_info,
                    },
                    POST_FIX_STAGE: post_fix_summary,
                },
            },
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
            "metrics": {},
        }
