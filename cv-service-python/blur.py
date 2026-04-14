import cv2
import numpy as np

def validate_blur(img):
    issues = []
    metrics = {}
    score_contrib = 1.0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    metrics["blur_score"] = laplacian_var

    # Threshold for blur
    if laplacian_var < 100:  # Higher is sharper
        issues.append(f"Image is blurry (Laplacian variance {laplacian_var:.1f})")
        score_contrib *= 0.8

    return {"issues": issues, "metrics": metrics, "score_contrib": score_contrib}