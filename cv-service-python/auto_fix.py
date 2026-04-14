import cv2
import numpy as np
import mediapipe as mp
from rembg import remove

mp_face_mesh = mp.solutions.face_mesh

def auto_fix_image(img, metrics):
    h, w = img.shape[:2]

    # If already 600x600, skip resize
    if w == 600 and h == 600:
        return img

    # Use face mesh to find face
    with mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, min_detection_confidence=0.5) as face_mesh:
        results = face_mesh.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if not results.multi_face_landmarks:
            return None

        landmarks = results.multi_face_landmarks[0].landmark

        # Get face bounding box from landmarks
        x_coords = [lm.x * w for lm in landmarks]
        y_coords = [lm.y * h for lm in landmarks]
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)

        # Expand slightly
        margin = 0.1
        x_min = max(0, x_min - margin * (x_max - x_min))
        x_max = min(w, x_max + margin * (x_max - x_min))
        y_min = max(0, y_min - margin * (y_max - y_min))
        y_max = min(h, y_max + margin * (y_max - y_min))

        # Crop
        cropped = img[int(y_min):int(y_max), int(x_min):int(x_max)]

        # Resize to 600x600
        resized = cv2.resize(cropped, (600, 600), interpolation=cv2.INTER_LINEAR)

        # Optional: background normalization using rembg
        try:
            # Remove background and composite on white
            no_bg = remove(resized)
            # Create white background
            white_bg = np.ones_like(resized) * 255
            # Composite: where alpha > 0, use original, else white
            if no_bg.shape[2] == 4:
                alpha = no_bg[:, :, 3] / 255.0
                for c in range(3):
                    white_bg[:, :, c] = (1 - alpha) * 255 + alpha * no_bg[:, :, c]
                resized = white_bg.astype(np.uint8)
        except Exception as e:
            # If rembg fails, keep original resized
            pass

        return resized