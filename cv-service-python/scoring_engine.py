from typing import Dict, Any

FEATURE_WEIGHTS = {
    "face_score": 0.35,
    "blur_score": 0.18,
    "lighting_score": 0.18,
    "background_score": 0.15,
    "exif_score": 0.08,
    "manipulation_score": 0.06,
}


def aggregate_features(feature_scores: Dict[str, float]) -> Dict[str, Any]:
    final_score = 0.0
    normalized_scores = {}
    for feature, weight in FEATURE_WEIGHTS.items():
        value = float(feature_scores.get(feature, 0.0))
        normalized_scores[feature] = round(value, 3)
        final_score += value * weight

    final_score = max(min(final_score, 1.0), 0.0)
    pass_probability = round(final_score, 3)
    valid = pass_probability >= 0.92

    sorted_by_score = sorted(FEATURE_WEIGHTS.keys(), key=lambda k: normalized_scores.get(k, 0.0))
    lowest = sorted_by_score[:2]
    insights = []
    for name in lowest:
        score = normalized_scores.get(name, 0.0)
        if score < 0.92:
            insights.append(f"{name.replace('_', ' ')} is lower than expected ({score:.2f})")

    if valid:
        decision_reason = "Probabilistic biometric validation indicates a strong pass probability."
    elif insights:
        decision_reason = "; ".join(insights)
    else:
        decision_reason = "Final probability is below threshold, indicating at least one biometric signal is weak."

    return {
        "final_score": round(final_score, 3),
        "pass_probability": pass_probability,
        "valid": valid,
        "feature_scores": normalized_scores,
        "decision_reason": decision_reason,
    }
