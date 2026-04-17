from typing import Dict, Literal

Mode = Literal["strict", "balanced"]

DEFAULT_MODE: Mode = "balanced"
BALANCED_MODE: Mode = "balanced"
STRICT_MODE: Mode = "strict"

# Final decision thresholds (0..100 score)
SCORE_PASS_THRESHOLD = 80.0
SCORE_WARNING_THRESHOLD = 60.0
SCORE_MIN_FLOOR = 30.0  # Do not drop to unusable near-zero scores

# Legacy compatibility (for older modules that expect 0..1 threshold)
PASS_PROBABILITY_THRESHOLD = SCORE_WARNING_THRESHOLD / 100.0

# Weighted scoring (must sum to 1.0)
WEIGHT_FACE_GEOMETRY = 0.40
WEIGHT_BACKGROUND = 0.25
WEIGHT_BLUR = 0.20
WEIGHT_LIGHTING = 0.15

# Auto-crop target
CROP_TARGET_SIZE = (600, 600)
CROP_MARGIN_FACTOR = 0.03
TARGET_HEAD_PERCENT = (52.0, 68.0)  # expected after crop
TARGET_EYE_LEVEL = (50.0, 69.0)     # eye line from bottom

# Face detection / mesh settings
FACE_DETECTION_CONFIDENCE = 0.5
FALLBACK_CONFIDENCE = 0.3
DETECTION_RETRY_CONTRAST_ALPHA = 1.12  # used only for detection retry
DETECTION_RETRY_CONTRAST_BETA = 2.0

# Balanced validation thresholds (default mode)
BALANCED_THRESHOLDS: Dict[str, float | tuple[float, float]] = {
    "head_percent": (50.0, 70.0),
    "eye_level": (49.0, 70.0),
    "blur_variance_min": 52.0,
    "face_shadow_variance_max": 4800.0,
    "background_variance_max": 4200.0,  # softer for white/light-gray background
}

# Strict profile can be used from API mode=strict
STRICT_THRESHOLDS: Dict[str, float | tuple[float, float]] = {
    "head_percent": (52.0, 68.0),
    "eye_level": (50.0, 69.0),
    "blur_variance_min": 60.0,
    "face_shadow_variance_max": 4300.0,
    "background_variance_max": 2800.0,
}
