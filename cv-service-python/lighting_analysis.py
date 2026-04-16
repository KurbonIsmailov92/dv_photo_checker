import cv2
import numpy as np


def clamp(value, minimum=0.0, maximum=1.0):
    return max(min(value, maximum), minimum)


def local_histogram_score(gray):
    hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
    hist = hist.flatten() / hist.sum()
    entropy = -np.sum([p * np.log2(p) for p in hist if p > 0])
    return clamp(entropy / 5.0)


def gradient_uniformity_score(gray):
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.sqrt(np.square(grad_x) + np.square(grad_y))
    mean_grad = np.mean(grad_mag)
    return clamp(1.0 - mean_grad / 60.0)


def lighting_balance_score(gray, face_rect=None):
    h, w = gray.shape[:2]
    if face_rect:
        x, y, fw, fh = face_rect
        face_region = gray[y:y + fh, x:x + fw]
    else:
        face_region = gray[int(h * 0.2):int(h * 0.8), int(w * 0.2):int(w * 0.8)]

    background_mask = np.ones_like(gray, dtype=bool)
    if face_rect:
        x, y, fw, fh = face_rect
        background_mask[y:y + fh, x:x + fw] = False
    else:
        background_mask[int(h * 0.3):int(h * 0.7), int(w * 0.3):int(w * 0.7)] = False

    background_region = gray[background_mask]
    if background_region.size == 0 or face_region.size == 0:
        return 0.7, 0.7, 0.7

    face_mean = float(np.mean(face_region))
    back_mean = float(np.mean(background_region))
    face_std = float(np.std(face_region))
    back_std = float(np.std(background_region))

    brightness_diff = abs(face_mean - back_mean) / 80.0
    uniformity = clamp(1.0 - brightness_diff)
    face_contrast = clamp((face_std - 20.0) / 70.0)
    background_uniformity = clamp(1.0 - back_std / 80.0)

    return round(uniformity, 3), round(face_contrast, 3), round(background_uniformity, 3)


def validate_lighting(img, face_rect=None):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(np.mean(gray))
    variance = float(np.var(gray))

    hist_score = local_histogram_score(gray)
    gradient_score = gradient_uniformity_score(gray)
    balance_score, contrast_score, background_uniformity = lighting_balance_score(gray, face_rect=face_rect)

    lighting_score = np.mean([hist_score, gradient_score, balance_score, contrast_score, background_uniformity])
    lighting_score = clamp(lighting_score)

    issues = []
    if mean_brightness < 60:
        issues.append("Image is underexposed")
    elif mean_brightness > 220:
        issues.append("Image is overexposed")
    if gradient_score < 0.4:
        issues.append("Lighting is uneven across the scene")
    if abs(balance_score - 1.0) > 0.35:
        issues.append("Face lighting does not match surrounding background lighting")

    metrics = {
        "mean_brightness": round(mean_brightness, 2),
        "brightness_variance": round(variance, 2),
        "histogram_entropy_score": round(hist_score, 3),
        "gradient_uniformity_score": round(gradient_score, 3),
        "face_background_balance_score": round(balance_score, 3),
        "face_contrast_score": round(contrast_score, 3),
        "background_uniformity_score": round(background_uniformity, 3),
    }

    return {"issues": issues, "metrics": metrics, "feature_scores": {"lighting_score": round(lighting_score, 3)}}
