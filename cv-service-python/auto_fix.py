import cv2

from face import detect_primary_face


def auto_fix_image(img, metrics):
    h, w = img.shape[:2]
    if w == 600 and h == 600:
        return img

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    detection, _ = detect_primary_face(gray)
    if detection is None:
        return cv2.resize(img, (600, 600), interpolation=cv2.INTER_LINEAR)

    x, y, face_w, face_h = detection
    face_center_x = x + face_w / 2
    face_center_y = y + face_h / 2

    crop_size = int(max(face_w, face_h) * 1.8)
    crop_size = max(crop_size, min(h, w) // 2)
    half = crop_size // 2

    x1 = max(0, int(face_center_x - half))
    y1 = max(0, int(face_center_y - half))
    x2 = min(w, x1 + crop_size)
    y2 = min(h, y1 + crop_size)

    if x2 - x1 < crop_size:
        x1 = max(0, x2 - crop_size)
    if y2 - y1 < crop_size:
        y1 = max(0, y2 - crop_size)

    cropped = img[y1:y2, x1:x2]
    if cropped.size == 0:
        return cv2.resize(img, (600, 600), interpolation=cv2.INTER_LINEAR)

    return cv2.resize(cropped, (600, 600), interpolation=cv2.INTER_LINEAR)
