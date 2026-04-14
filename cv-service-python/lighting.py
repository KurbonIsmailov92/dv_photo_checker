import cv2
import numpy as np

def validate_lighting(img):
    issues = []
    metrics = {}
    score_contrib = 1.0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    brightness = np.mean(gray)
    metrics["brightness"] = brightness

    if brightness < 70:
        issues.append(f"Image is underexposed (brightness {brightness:.1f})")
        score_contrib *= 0.9
    elif brightness > 230:
        issues.append(f"Image is overexposed (brightness {brightness:.1f})")
        score_contrib *= 0.9

    # Detect shadows: variance across face region (assume center)
    h, w = img.shape[:2]
    face_region = gray[int(h*0.2):int(h*0.8), int(w*0.2):int(w*0.8)]
    variance = np.var(face_region)
    metrics["face_variance"] = variance
    if variance > 1000:
        issues.append(f"Shadows detected on face (variance {variance:.1f})")
        score_contrib *= 0.85

    return {"issues": issues, "metrics": metrics, "score_contrib": score_contrib}