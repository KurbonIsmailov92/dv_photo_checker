from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import checker


def make_clean_photo(height: int = 600, width: int = 600) -> np.ndarray:
    base = np.full((height, width, 3), 245, dtype=np.uint8)
    gradient = np.linspace(0, 8, height, dtype=np.uint8).reshape(height, 1, 1)
    image = np.clip(base - gradient, 0, 255).astype(np.uint8)

    cv2.ellipse(image, (width // 2, int(height * 0.28)), (55, 72), 0, 0, 360, (175, 175, 175), -1)
    cv2.rectangle(
        image,
        (width // 2 - 95, int(height * 0.40)),
        (width // 2 + 95, int(height * 0.88)),
        (188, 188, 188),
        -1,
    )
    return image


def make_bad_background_photo(height: int = 600, width: int = 600) -> np.ndarray:
    rng = np.random.default_rng(42)
    image = rng.integers(120, 255, size=(height, width, 3), dtype=np.uint8)
    cv2.ellipse(image, (width // 2, int(height * 0.28)), (55, 72), 0, 0, 360, (175, 175, 175), -1)
    cv2.rectangle(
        image,
        (width // 2 - 95, int(height * 0.40)),
        (width // 2 + 95, int(height * 0.88)),
        (188, 188, 188),
        -1,
    )
    return image


def good_face_result(image, mode=None, enforce_rules=True, post_fix=False):
    h, w = image.shape[:2]
    face_rect = {
        "x": int(w * 0.40),
        "y": int(h * 0.14),
        "w": int(w * 0.20),
        "h": int(h * 0.28),
    }
    return {
        "issues": [],
        "warnings": [],
        "metrics": {
            "face_rect": face_rect,
            "head_percent": 60.0,
            "eye_level": 58.0,
            "face_top_y": round(h * 0.12, 2),
            "face_chin_y": round(h * 0.48, 2),
            "landmarks_found": True,
        },
        "feature_scores": {"face_geometry_score": 0.96},
    }


def ok_blur(image, mode=None):
    return {
        "issues": [],
        "warnings": [],
        "metrics": {"blur_variance": 140.0},
        "feature_scores": {"blur_score": 0.95},
    }


def ok_lighting(image, face_rect=None, mode=None, crop_applied=False, context="initial"):
    return {
        "issues": [],
        "warnings": [],
        "metrics": {
            "mean_brightness": 180.0,
            "brightness_variance": 25.0,
            "shadow_variance": 450.0,
        },
        "feature_scores": {"lighting_score": 0.95},
    }


class CheckerPipelineTests(unittest.TestCase):
    def test_ideal_light_background_passes_without_false_background_issues(self):
        image = make_clean_photo()

        with patch("checker.auto_crop_to_dv_standard", side_effect=lambda img: (img.copy(), False, {"reason": "already_target_size"})):
            with patch("checker.validate_face_geometry", side_effect=good_face_result):
                with patch("checker.validate_blur", side_effect=ok_blur):
                    with patch("checker.validate_lighting", side_effect=ok_lighting):
                        result = checker.analyze_photo(image)

        self.assertTrue(result["valid"])
        self.assertEqual([], [issue for issue in result["issues"] if "Background" in issue])

    def test_post_fix_validation_does_not_fail_service_generated_crop(self):
        source_image = make_clean_photo(height=900, width=900)
        fixed_image = make_clean_photo()

        def crop_result(_img):
            return fixed_image.copy(), True, {"reason": "face_landmarks", "crop_size": 700}

        def stage_aware_background(image, face_rect=None, mode=None, crop_applied=False, context="initial"):
            if context == "initial":
                return {
                    "issues": [],
                    "warnings": [],
                    "metrics": {"background_variance": 14.0, "background_edge_density": 0.0},
                    "feature_scores": {"background_score": 0.97},
                }
            return {
                "issues": ["Background contains visible structure or edges."],
                "warnings": [],
                "metrics": {"background_variance": 410.0, "background_edge_density": 0.08},
                "feature_scores": {"background_score": 0.40},
            }

        with patch("checker.auto_crop_to_dv_standard", side_effect=crop_result):
            with patch("checker.validate_face_geometry", side_effect=good_face_result):
                with patch("checker.validate_background", side_effect=stage_aware_background):
                    with patch("checker.validate_blur", side_effect=ok_blur):
                        with patch("checker.validate_lighting", side_effect=ok_lighting):
                            result = checker.analyze_photo(source_image)

        self.assertTrue(result["valid"])
        self.assertEqual([], [issue for issue in result["issues"] if "Background" in issue])
        self.assertIn(
            "Background contains visible structure or edges.",
            result["detail"]["pipeline"]["post_fix_validation"]["issues"],
        )

    def test_bad_background_still_fails(self):
        image = make_bad_background_photo()

        with patch("checker.auto_crop_to_dv_standard", side_effect=lambda img: (img.copy(), False, {"reason": "already_target_size"})):
            with patch("checker.validate_face_geometry", side_effect=good_face_result):
                with patch("checker.validate_blur", side_effect=ok_blur):
                    with patch("checker.validate_lighting", side_effect=ok_lighting):
                        result = checker.analyze_photo(image)

        self.assertFalse(result["valid"])
        self.assertTrue(any("Background" in issue for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()
