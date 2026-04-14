import cv2
import numpy as np
import logging
from rembg import remove

logger = logging.getLogger(__name__)

def validate_background(img):
    issues = []
    metrics = {}
    score_contrib = 1.0

    h, w = img.shape[:2]

    # Use rembg for background removal
    try:
        # Remove background
        img_no_bg = remove(img)
        # Convert to grayscale for analysis
        gray_no_bg = cv2.cvtColor(img_no_bg, cv2.COLOR_BGR2GRAY)
        # Foreground mask (where alpha > 0)
        alpha = img_no_bg[:, :, 3] if img_no_bg.shape[2] == 4 else np.ones((h, w), dtype=np.uint8) * 255
        foreground_mask = alpha > 128

        # Background uniformity: variance in non-foreground areas
        background_pixels = img[~foreground_mask]
        if background_pixels.size > 0:
            bg_variance = np.var(background_pixels)
            metrics["background_variance"] = bg_variance
            if bg_variance > 1000:
                issues.append(f"Background not uniform (variance {bg_variance:.1f})")
                score_contrib *= 0.8

            # Average background brightness
            bg_brightness = np.mean(background_pixels)
            metrics["background_brightness"] = bg_brightness
            if bg_brightness < 180:
                issues.append(f"Background too dark (brightness {bg_brightness:.1f})")
                score_contrib *= 0.9
        else:
            # If no background detected, assume uniform
            metrics["background_variance"] = 0
            metrics["background_brightness"] = 255

        # Edge density in background
        background_gray = gray_no_bg[~foreground_mask]
        if background_gray.size > 0:
            # Reshape for Canny
            bg_reshaped = background_gray.reshape(-1, 1) if background_gray.ndim == 1 else background_gray
            edges_bg = cv2.Canny(bg_reshaped.astype(np.uint8), 100, 200)
            edge_density = np.sum(edges_bg > 0) / background_gray.size * 100
            metrics["background_edge_density"] = edge_density
            if edge_density > 5:
                issues.append(f"Background has edges/shadows (density {edge_density:.1f}%)")
                score_contrib *= 0.85

    except Exception as e:
        # Fallback to simple method if rembg fails
        logger.warning(f"Rembg failed: {e}, using fallback")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        background_mask = thresh == 255
        if np.any(background_mask):
            bg_pixels = img[background_mask]
            variance = np.var(bg_pixels)
            metrics["background_variance"] = variance
            if variance > 1000:
                issues.append(f"Background not uniform (variance {variance:.1f})")
                score_contrib *= 0.8

        edges = cv2.Canny(gray, 100, 200)
        edge_density = np.sum(edges > 0) / edges.size * 100
        metrics["background_edge_density"] = edge_density
        if edge_density > 5:
            issues.append(f"Background has edges/shadows (density {edge_density:.1f}%)")
            score_contrib *= 0.85

    return {"issues": issues, "metrics": metrics, "score_contrib": score_contrib}