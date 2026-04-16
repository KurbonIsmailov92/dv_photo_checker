from typing import Dict, List
from config import PASS_PROBABILITY_THRESHOLD, WEIGHT_BACKGROUND, WEIGHT_BLUR, WEIGHT_FACE_GEOMETRY, WEIGHT_LIGHTING


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(min(value, maximum), minimum)


def aggregate_feature_scores(feature_scores: Dict[str, float]) -> Dict[str, float]:
    return {
        "face_geometry_score": round(clamp(feature_scores.get("face_geometry_score", 0.0)), 3),
        "background_score": round(clamp(feature_scores.get("background_score", 0.0)), 3),
        "blur_score": round(clamp(feature_scores.get("blur_score", 0.0)), 3),
        "lighting_score": round(clamp(feature_scores.get("lighting_score", 0.0)), 3),
    }


def compute_final_score(feature_scores: Dict[str, float]) -> float:
    face_score = feature_scores.get("face_geometry_score", 0.0)
    background_score = feature_scores.get("background_score", 0.0)
    blur_score = feature_scores.get("blur_score", 0.0)
    lighting_score = feature_scores.get("lighting_score", 0.0)

    final_score = (
        face_score * WEIGHT_FACE_GEOMETRY
        + background_score * WEIGHT_BACKGROUND
        + blur_score * WEIGHT_BLUR
        + lighting_score * WEIGHT_LIGHTING
    )
    return round(clamp(final_score), 3)


def build_decision(final_score: float, issues: List[str], warnings: List[str]) -> Dict[str, object]:
    valid = final_score >= PASS_PROBABILITY_THRESHOLD and len(issues) == 0
    if valid:
        if warnings:
            decision_reason = "Photo passes with minor issues after crop. Warnings are shown for review."
        else:
            decision_reason = "Photo passes DV-style validation after crop."
    else:
        if len(issues) > 0:
            decision_reason = "Photo did not satisfy core biometric or background checks after crop."
        else:
            decision_reason = "Final probability is below the pass threshold."

    return {
        "valid": valid,
        "score": final_score,
        "pass_probability": final_score,
        "decision_reason": decision_reason,
    }
