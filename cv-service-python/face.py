import cv2
import mediapipe as mp
import numpy as np
import math

mp_face_mesh = mp.solutions.face_mesh
mp_face_detection = mp.solutions.face_detection

# 3D model points for solvePnP (standard face landmarks)
FACE_3D_POINTS = np.array([
    [0.0, 0.0, 0.0],          # Nose tip (landmark 1)
    [0.0, -330.0, -65.0],     # Chin (landmark 152)
    [-225.0, 170.0, -135.0],  # Left eye left corner (landmark 33)
    [225.0, 170.0, -135.0],   # Right eye right corner (landmark 263)
    [-150.0, -150.0, -125.0], # Left mouth corner (landmark 61)
    [150.0, -150.0, -125.0],  # Right mouth corner (landmark 291)
], dtype=np.float64)

def validate_face(img):
    issues = []
    metrics = {}
    score_contrib = 1.0  # For weighted scoring

    h, w, _ = img.shape

    # First, detect faces for bounding box
    bbox = None
    with mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5) as face_detection:
        results_det = face_detection.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

        if not results_det.detections:
            issues.append("No face detected")
            score_contrib *= 0.1
            return {"issues": issues, "metrics": metrics, "score_contrib": score_contrib}

        if len(results_det.detections) > 1:
            issues.append("Multiple faces detected")
            score_contrib *= 0.5

        detection = results_det.detections[0]
        bbox_rel = detection.location_data.relative_bounding_box
        bbox = {
            'x': int(bbox_rel.xmin * w),
            'y': int(bbox_rel.ymin * h),
            'width': int(bbox_rel.width * w),
            'height': int(bbox_rel.height * h)
        }

    # Use Face Mesh for landmarks
    with mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, min_detection_confidence=0.5) as face_mesh:
        results = face_mesh.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

        if not results.multi_face_landmarks:
            issues.append("Face landmarks not detected")
            score_contrib *= 0.7
            return {"issues": issues, "metrics": metrics, "score_contrib": score_contrib}

        landmarks = results.multi_face_landmarks[0].landmark

        # Improved crown detection: use forehead landmark + offset or bbox top
        forehead_y = landmarks[10].y * h  # Landmark 10: forehead top
        # Add offset up for crown (empirical, ~10% of face height)
        face_height = bbox['height']
        crown_y = max(0, forehead_y - 0.1 * face_height)
        chin_y = landmarks[152].y * h  # Chin
        head_height = chin_y - crown_y
        head_ratio = (head_height / h) * 100
        metrics["head_ratio"] = head_ratio
        if not (50 <= head_ratio <= 69):
            issues.append(f"Head height ratio {head_ratio:.1f}% not between 50-69%")
            score_contrib *= 0.8

        # Face center
        nose_tip = landmarks[1]  # Nose tip
        face_center_x = nose_tip.x * w
        face_center_y = nose_tip.y * h

        horiz_dev = abs(face_center_x - w/2) / w * 100
        vert_dev = abs(face_center_y - h/2) / h * 100

        metrics["horizontal_deviation"] = horiz_dev
        metrics["vertical_deviation"] = vert_dev

        if horiz_dev > 7:
            issues.append(f"Face not centered horizontally (deviation {horiz_dev:.1f}%)")
            score_contrib *= 0.9

        if vert_dev > 10:
            issues.append(f"Face not centered vertically (deviation {vert_dev:.1f}%)")
            score_contrib *= 0.9

        # Eye level
        left_eye_center = np.mean([(landmarks[33].y + landmarks[133].y)/2, (landmarks[33].x + landmarks[133].x)/2], axis=0)
        right_eye_center = np.mean([(landmarks[362].y + landmarks[263].y)/2, (landmarks[362].x + landmarks[263].x)/2], axis=0)
        eye_level_y = ((left_eye_center[0] + right_eye_center[0])/2) * h
        eye_level_ratio = (eye_level_y / h) * 100
        metrics["eye_level"] = eye_level_ratio
        if not (56 <= eye_level_ratio <= 69):
            issues.append(f"Eye level {eye_level_ratio:.1f}% not between 56-69%")
            score_contrib *= 0.85

        # Improved pose estimation using solvePnP
        # 2D points corresponding to FACE_3D_POINTS
        image_points = np.array([
            [landmarks[1].x * w, landmarks[1].y * h],      # Nose
            [landmarks[152].x * w, landmarks[152].y * h],  # Chin
            [landmarks[33].x * w, landmarks[33].y * h],    # Left eye
            [landmarks[263].x * w, landmarks[263].y * h],  # Right eye
            [landmarks[61].x * w, landmarks[61].y * h],    # Left mouth
            [landmarks[291].x * w, landmarks[291].y * h],  # Right mouth
        ], dtype=np.float64)

        # Camera matrix (assuming focal length ~w)
        focal_length = w
        center = (w / 2, h / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype=np.float64)

        dist_coeffs = np.zeros((4, 1))  # No distortion

        success, rotation_vector, translation_vector = cv2.solvePnP(
            FACE_3D_POINTS, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
        )

        if success:
            # Convert rotation vector to Euler angles
            rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
            yaw = math.degrees(math.atan2(rotation_matrix[2, 0], rotation_matrix[2, 2]))
            pitch = math.degrees(math.atan2(-rotation_matrix[2, 1], math.sqrt(rotation_matrix[2, 0]**2 + rotation_matrix[2, 2]**2)))
            roll = math.degrees(math.atan2(rotation_matrix[1, 0], rotation_matrix[0, 0]))

            metrics["face_angle"] = {"yaw": yaw, "pitch": pitch, "roll": roll}

            # Check pose thresholds
            if abs(yaw) > 15:
                issues.append(f"Face yawed {yaw:.1f} degrees")
                score_contrib *= 0.9
            if abs(pitch) > 15:
                issues.append(f"Face pitched {pitch:.1f} degrees")
                score_contrib *= 0.9
            if abs(roll) > 10:
                issues.append(f"Face rolled {roll:.1f} degrees")
                score_contrib *= 0.9
        else:
            # Fallback to geometric estimation
            left_eye = np.array([landmarks[33].x, landmarks[33].y])
            right_eye = np.array([landmarks[362].x, landmarks[362].y])
            eye_vector = right_eye - left_eye
            roll = math.degrees(math.atan2(eye_vector[1], eye_vector[0]))
            pitch = 0  # Simplified
            yaw = horiz_dev * 0.1
            metrics["face_angle"] = {"yaw": yaw, "pitch": pitch, "roll": roll}
            score_contrib *= 0.95

        # Glasses detection
        left_eye_region = img[int(landmarks[33].y*h-10):int(landmarks[33].y*h+10), int(landmarks[33].x*w-10):int(landmarks[33].x*w+10)]
        right_eye_region = img[int(landmarks[362].y*h-10):int(landmarks[362].y*h+10), int(landmarks[362].x*w-10):int(landmarks[362].x*w+10)]

        if left_eye_region.size > 0 and right_eye_region.size > 0:
            left_bright = np.mean(cv2.cvtColor(left_eye_region, cv2.COLOR_BGR2GRAY))
            right_bright = np.mean(cv2.cvtColor(right_eye_region, cv2.COLOR_BGR2GRAY))
            if left_bright > 200 or right_bright > 200:
                issues.append("Possible glasses detected (eye reflections)")
                score_contrib *= 0.95

    return {"issues": issues, "metrics": metrics, "score_contrib": score_contrib}