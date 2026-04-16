import cv2
import numpy as np


def clamp(value, minimum=0.0, maximum=1.0):
    return max(min(value, maximum), minimum)


def compute_edge_density(gray, mask=None):
    edges = cv2.Canny(gray, 80, 180)
    if mask is not None and mask.shape == gray.shape:
        edges = edges[mask]
        denominator = np.count_nonzero(mask)
    else:
        denominator = gray.size
    if denominator == 0:
        return 0.0
    return float(np.count_nonzero(edges) / denominator)


def background_color_consistency(img, mask):
    if mask.sum() == 0:
        return 0.85
    background = img[mask]
    if background.size == 0:
        return 0.85
    background = background.reshape(-1, 3).astype(np.float32)
    mean = np.mean(background, axis=0)
    variance = np.mean(np.var(background, axis=0))
    return float(clamp(1.0 - variance / 2200.0))


def validate_background(img, face_rect=None):
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mask = np.ones((h, w), dtype=bool)
    if face_rect is not None:
        x, y, fw, fh = face_rect
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w, x + fw)
        y2 = min(h, y + fh)
        mask[y1:y2, x1:x2] = False

    edge_density = compute_edge_density(gray, mask=mask)
    color_consistency = background_color_consistency(img, mask)
    border_section = gray[0:int(h * 0.15), :]
    border_variance = float(np.var(border_section))
    border_score = clamp(1.0 - border_variance / 1800.0)

    background_score = np.mean([clamp(1.0 - edge_density * 6.5), color_consistency, border_score])
    background_score = clamp(background_score)

    issues = []
    if edge_density > 0.02:
        issues.append("Background contains too much edge activity")
    if color_consistency < 0.55:
        issues.append("Background color is not uniform enough for a visa-style photo")

    metrics = {
        "background_edge_density": round(edge_density, 4),
        "background_color_consistency": round(color_consistency, 3),
        "background_border_variance_score": round(border_score, 3),
    }

    return {"issues": issues, "metrics": metrics, "feature_scores": {"background_score": round(background_score, 3)}}
