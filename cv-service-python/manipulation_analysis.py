import cv2
import numpy as np


def clamp(value, minimum=0.0, maximum=1.0):
    return max(min(value, maximum), minimum)


def recompression_artifact_score(gray):
    h, w = gray.shape[:2]
    grid_size = 8
    boundaries = []
    for y in range(grid_size, h, grid_size):
        horizontal = np.abs(gray[y, :] - gray[y - 1, :]).astype(np.float32)
        boundaries.append(np.mean(horizontal))
    for x in range(grid_size, w, grid_size):
        vertical = np.abs(gray[:, x] - gray[:, x - 1]).astype(np.float32)
        boundaries.append(np.mean(vertical))
    if not boundaries:
        return 1.0, 0.0
    score = clamp(1.0 - np.median(boundaries) / 40.0)
    return score, float(np.median(boundaries))


def resampling_artifact_score(gray):
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    periodic_x = np.mean(np.abs(grad_x[:, 8:] - grad_x[:, :-8]))
    periodic_y = np.mean(np.abs(grad_y[8:, :] - grad_y[:-8, :]))
    score = clamp(1.0 - (periodic_x + periodic_y) / 100.0)
    return score, float((periodic_x + periodic_y) / 2.0)


def pixel_grid_consistency_score(gray):
    diff_x = np.abs(gray[:, 1:].astype(np.int16) - gray[:, :-1].astype(np.int16))
    diff_y = np.abs(gray[1:, :].astype(np.int16) - gray[:-1, :].astype(np.int16))
    grid_ping = np.mean(np.minimum(diff_x[:, 7:-7], 20)) + np.mean(np.minimum(diff_y[7:-7, :], 20))
    score = clamp(1.0 - grid_ping / 35.0)
    return score, float(grid_ping)


def validate_manipulation(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    recompression_score, recompression_metric = recompression_artifact_score(gray)
    resampling_score, resampling_metric = resampling_artifact_score(gray)
    grid_score, grid_metric = pixel_grid_consistency_score(gray)

    manipulation_score = np.mean([recompression_score, resampling_score, grid_score])
    manipulation_score = clamp(manipulation_score)

    issues = []
    if manipulation_score < 0.55:
        issues.append("Image shows signs of recompression or resampling artifacts")
    elif manipulation_score < 0.75:
        issues.append("Image may have undergone resizing or editing")

    metrics = {
        "recompression_artifact_metric": round(recompression_metric, 3),
        "resampling_artifact_metric": round(resampling_metric, 3),
        "pixel_grid_inconsistency_metric": round(grid_metric, 3),
    }

    return {"issues": issues, "metrics": metrics, "feature_scores": {"manipulation_score": round(manipulation_score, 3)}}
