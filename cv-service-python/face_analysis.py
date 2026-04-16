import cv2
import numpy as np

FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)
EYE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_eye.xml"
)


def clamp(value, minimum=0.0, maximum=1.0):
    return max(min(value, maximum), minimum)


def detect_primary_face(gray):
    faces = FACE_CASCADE.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=6,
        minSize=(100, 100),
    )
    if len(faces) == 0:
        return None, 0
    primary = max(faces, key=lambda face: face[2] * face[3])
    return primary, len(faces)


def estimate_eye_centers(gray, face_rect):
    x, y, w, h = face_rect
    face_roi = gray[y:y + h, x:x + w]
    eyes = EYE_CASCADE.detectMultiScale(
        face_roi,
        scaleFactor=1.1,
        minNeighbors=8,
        minSize=(24, 24),
        maxSize=(int(w * 0.5), int(h * 0.5)),
    )

    centers = []
    for ex, ey, ew, eh in eyes:
        centers.append((x + ex + ew * 0.5, y + ey + eh * 0.5))

    if len(centers) < 2:
        return None

    centers = sorted(centers, key=lambda pt: pt[0])[:2]
    return centers


def compute_eye_level_ratio(face_rect, eye_centers):
    x, y, w, h = face_rect
    top_of_head = np.array([x + w * 0.5, y])
    chin_point = np.array([x + w * 0.5, y + h])
    eyes_center = np.array([np.mean([pt[0] for pt in eye_centers]), np.mean([pt[1] for pt in eye_centers])])
    dist_chin = np.linalg.norm(eyes_center - chin_point)
    dist_top = np.linalg.norm(eyes_center - top_of_head)
    if dist_top < 1e-6:
        return None
    return float(dist_chin / dist_top)


def estimate_pose(eye_centers):
    if not eye_centers or len(eye_centers) < 2:
        return 0.0, 0.0, 0.0

    left_eye, right_eye = eye_centers
    dx = right_eye[0] - left_eye[0]
    dy = right_eye[1] - left_eye[1]
    roll = float(np.degrees(np.arctan2(dy, dx)))
    yaw = 0.0
    pitch = 0.0
    return round(yaw, 2), round(pitch, 2), round(roll, 2)


def score_eye_level_ratio(ratio):
    if ratio is None:
        return 0.55
    ideal = 1.7
    diff = abs(ratio - ideal)
    score = clamp(1.0 - diff / 1.2)
    return max(score, 0.0)


def validate_face(img):
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    face_rect, face_count = detect_primary_face(gray)
    issues = []
    metrics = {}
    feature_scores = {}

    if face_rect is None:
        issues.append("No face detected")
        feature_scores["face_score"] = 0.0
        metrics["face_detected"] = False
        return {
            "issues": issues,
            "metrics": metrics,
            "feature_scores": feature_scores,
        }

    metrics["face_detected"] = True
    metrics["face_count"] = face_count
    metrics["face_rect"] = [int(face_rect[0]), int(face_rect[1]), int(face_rect[2]), int(face_rect[3])]

    x, y, face_w, face_h = face_rect
    face_center = (x + face_w * 0.5, y + face_h * 0.5)
    image_center = (w * 0.5, h * 0.5)

    head_ratio = face_h / float(h)
    metrics["head_ratio"] = round(head_ratio, 3)
    head_size_score = clamp((head_ratio - 0.35) / 0.35)
    if head_ratio < 0.35 or head_ratio > 0.72:
        issues.append(f"Head size appears too { 'small' if head_ratio < 0.35 else 'large' } for passport framing")

    center_distance = np.linalg.norm(np.array(face_center) - np.array(image_center))
    center_ratio = center_distance / np.linalg.norm(np.array([w * 0.5, h * 0.5]))
    center_score = clamp(1.0 - center_ratio * 1.3)
    metrics["face_center_offset"] = round(center_ratio, 3)
    if center_ratio > 0.18:
        issues.append("Face position is slightly off-center")

    eye_centers = estimate_eye_centers(gray, face_rect)
    if eye_centers is None:
        metrics["eyes_detected"] = 0
        issues.append("Could not detect both eye landmarks reliably")
        eye_level_score = 0.65
        pose_score = 0.70
    else:
        metrics["eyes_detected"] = 2
        eye_ratio = compute_eye_level_ratio(face_rect, eye_centers)
        metrics["eye_level_ratio"] = round(eye_ratio or 0.0, 3)
        eye_level_score = score_eye_level_ratio(eye_ratio)
        if eye_ratio is not None and (eye_ratio < 1.2 or eye_ratio > 2.2):
            issues.append("Eye level looks outside normal passport proportions")

        yaw, pitch, roll = estimate_pose(eye_centers)
        metrics["face_angle"] = {"yaw": yaw, "pitch": pitch, "roll": roll}
        pose_score = clamp(1.0 - abs(roll) / 35.0)
        if abs(roll) > 10:
            issues.append("Head tilt is noticeable")

    face_score = np.mean([head_size_score, center_score, eye_level_score, pose_score])
    if face_count > 1:
        issues.append("Multiple faces were detected")
        face_score *= 0.65

    feature_scores["face_score"] = clamp(face_score)
    feature_scores["face_center_score"] = round(center_score, 3)
    feature_scores["face_size_score"] = round(head_size_score, 3)
    feature_scores["eye_level_score"] = round(eye_level_score, 3)
    feature_scores["face_pose_score"] = round(pose_score, 3)

    return {"issues": issues, "metrics": metrics, "feature_scores": feature_scores}
