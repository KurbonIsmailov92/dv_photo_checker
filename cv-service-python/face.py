import cv2
import numpy as np


FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)
EYE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_eye.xml"
)


def detect_primary_face(gray):
    faces = FACE_CASCADE.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(120, 120),
    )
    if len(faces) == 0:
        return None, 0

    primary = max(faces, key=lambda face: face[2] * face[3])
    return primary, len(faces)


def validate_face(img):
    issues = []
    metrics = {}
    score_contrib = 1.0

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    detection, face_count = detect_primary_face(gray)
    if detection is None:
        issues.append("No face detected")
        return {"issues": issues, "metrics": metrics, "score_contrib": 0.1}

    if face_count > 1:
        issues.append("Multiple faces detected")
        score_contrib *= 0.5

    x, y, face_w, face_h = detection
    x = max(0, x)
    y = max(0, y)
    face_w = min(face_w, w - x)
    face_h = min(face_h, h - y)

    head_ratio = (face_h / h) * 100
    metrics["head_ratio"] = head_ratio
    if not (50 <= head_ratio <= 69):
        issues.append(f"Head height ratio {head_ratio:.1f}% not between 50-69%")
        score_contrib *= 0.8

    face_center_x = x + face_w / 2
    face_center_y = y + face_h / 2

    horiz_dev = abs(face_center_x - w / 2) / w * 100
    vert_dev = abs(face_center_y - h / 2) / h * 100
    metrics["horizontal_deviation"] = horiz_dev
    metrics["vertical_deviation"] = vert_dev

    if horiz_dev > 7:
        issues.append(f"Face not centered horizontally (deviation {horiz_dev:.1f}%)")
        score_contrib *= 0.9

    if vert_dev > 10:
        issues.append(f"Face not centered vertically (deviation {vert_dev:.1f}%)")
        score_contrib *= 0.9

    eye_level_ratio = ((y + face_h * 0.4) / h) * 100
    face_roi_gray = gray[y : y + face_h, x : x + face_w]
    eyes = EYE_CASCADE.detectMultiScale(
        face_roi_gray,
        scaleFactor=1.1,
        minNeighbors=8,
        minSize=(20, 20),
    )
    if len(eyes) >= 2:
        eyes = sorted(eyes, key=lambda eye: eye[0])[:2]
        eye_centers = [eye_y + eye_h / 2 for _, eye_y, _, eye_h in eyes]
        eye_level_ratio = ((y + float(np.mean(eye_centers))) / h) * 100

    metrics["eye_level"] = eye_level_ratio
    if not (56 <= eye_level_ratio <= 69):
        issues.append(f"Eye level {eye_level_ratio:.1f}% not between 56-69%")
        score_contrib *= 0.85

    # Haar cascades do not provide reliable 3D pose, so keep a neutral estimate.
    metrics["face_angle"] = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

    if len(eyes) >= 2:
        bright_eyes = []
        for eye_x, eye_y, eye_w, eye_h in eyes[:2]:
            eye_region = face_roi_gray[eye_y : eye_y + eye_h, eye_x : eye_x + eye_w]
            if eye_region.size > 0:
                bright_eyes.append(float(np.mean(eye_region)))
        if bright_eyes and max(bright_eyes) > 210:
            issues.append("Possible glasses detected (eye reflections)")
            score_contrib *= 0.95

    return {"issues": issues, "metrics": metrics, "score_contrib": score_contrib}
