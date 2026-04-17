"""
Configuration for DV Photo Validator.
Contains thresholds and settings for image validation.
"""

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

# Face positioning targets (percentage from top/bottom)
# These are reference values; actual cropping uses fixed ratios (0.60/0.58)
TARGET_HEAD_PERCENT = (50.0, 70.0)   # Head should be 50-70% of final image height
TARGET_EYE_LEVEL = (49.0, 70.0)      # Eye line should be 49-70% from bottom

# MediaPipe Face Mesh settings
# Note: detect_face_landmarks tries multiple confidence levels internally (0.5, 0.35, 0.25)
FACE_DETECTION_CONFIDENCE = 0.5      # Primary confidence level
FALLBACK_CONFIDENCE = 0.3            # Secondary fallback

# Image enhancement for detection retry
DETECTION_RETRY_CONTRAST_ALPHA = 1.12  # Contrast multiplier
DETECTION_RETRY_CONTRAST_BETA = 2.0    # Brightness offset

# ============================================================================
# BALANCED MODE THRESHOLDS (default for general use)
# ============================================================================
# Balanced mode is more permissive to approve more valid photos
# while still catching obvious issues
BALANCED_THRESHOLDS: Dict[str, float | tuple[float, float]] = {
    # Face geometry constraints
    "head_percent": (50.0, 70.0),      # Head size 50-70% of image
    "eye_level": (49.0, 70.0),         # Eye position 49-70% from bottom
    
    # Image quality constraints
    "blur_variance_min": 52.0,          # Laplacian variance threshold (higher = sharper)
    "face_shadow_variance_max": 4800.0, # Maximum face shadow variance (lower = less shadow)
    "background_variance_max": 4200.0,  # Maximum background noise
}

# ============================================================================
# STRICT MODE THRESHOLDS (for demanding applications like ASTAR-like systems)
# ============================================================================
# Strict mode enforces tighter constraints for maximum photo quality
STRICT_THRESHOLDS: Dict[str, float | tuple[float, float]] = {
    # Face geometry constraints (tighter than balanced)
    "head_percent": (52.0, 68.0),      # Head size 52-68% of image
    "eye_level": (50.0, 69.0),         # Eye position 50-69% from bottom
    
    # Image quality constraints (stricter)
    "blur_variance_min": 60.0,          # Higher minimum sharpness requirement
    "face_shadow_variance_max": 4300.0, # Stricter shadow limit
    "background_variance_max": 3500.0,  # Stricter background cleanliness
}
