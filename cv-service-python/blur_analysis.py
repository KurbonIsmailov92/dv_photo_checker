import cv2
import numpy as np


def clamp(value, minimum=0.0, maximum=1.0):
    return max(min(value, maximum), minimum)


def validate_blur(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    tiles = 4
    variances = []

    for row in range(tiles):
        for col in range(tiles):
            y0 = int(h * row / tiles)
            y1 = int(h * (row + 1) / tiles)
            x0 = int(w * col / tiles)
            x1 = int(w * (col + 1) / tiles)
            tile = gray[y0:y1, x0:x1]
            if tile.size == 0:
                continue
            variances.append(float(cv2.Laplacian(tile, cv2.CV_64F).var()))

    if not variances:
        variances = [float(np.var(gray))]

    median_var = float(np.median(variances))
    metrics = {
        "blur_median_variance": round(median_var, 2),
        "blur_tile_variances": [round(float(v), 2) for v in variances],
    }

    blur_score = clamp((median_var - 30.0) / 180.0)
    if blur_score < 0.45:
        issues = ["Image blur is likely to affect biometric recognition"]
    else:
        issues = []

    return {"issues": issues, "metrics": metrics, "feature_scores": {"blur_score": round(blur_score, 3)}}
