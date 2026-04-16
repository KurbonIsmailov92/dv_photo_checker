from typing import Literal

Mode = Literal["strict", "balanced"]

DEFAULT_MODE: Mode = "balanced"
STRICT_MODE: Mode = "strict"
BALANCED_MODE: Mode = "balanced"

PASS_PROBABILITY_THRESHOLD = 0.92

WEIGHT_FACE_GEOMETRY = 0.35
WEIGHT_BACKGROUND = 0.25
WEIGHT_BLUR = 0.20
WEIGHT_LIGHTING = 0.20

HEAD_PERCENT_RANGE = (50.0, 70.0)
EYE_LEVEL_RANGE = (49.0, 70.0)

BALANCED_WARNING_MARGIN = 2.0
STRICT_WARNING_MARGIN = 0.0

BLUR_VARIANCE_MIN = 52.0
SHADOW_VARIANCE_MAX = 4800.0
BACKGROUND_VARIANCE_MAX = 2200.0

# Perception thresholds for balanced mode. These are intentionally softer than strict limits.
BALANCED_THRESHOLDS = {
    "head_percent": (48.0, 72.0),
    "eye_level": (47.0, 72.0),
    "blur_variance": 48.0,
    "shadow_variance": 5200.0,
    "background_variance": 2600.0,
}

STRICT_THRESHOLDS = {
    "head_percent": HEAD_PERCENT_RANGE,
    "eye_level": EYE_LEVEL_RANGE,
    "blur_variance": BLUR_VARIANCE_MIN,
    "shadow_variance": SHADOW_VARIANCE_MAX,
    "background_variance": BACKGROUND_VARIANCE_MAX,
}
