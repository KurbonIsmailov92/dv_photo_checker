import io
from PIL import Image, ExifTags

SUSPICIOUS_SOFTWARE = [
    "Adobe Photoshop",
    "Lightroom",
    "Photoshop",
    "GIMP",
    "Affinity Photo",
    "Pixelmator",
    "Snapseed",
    "VSCO",
    "Canva",
]


def safe_get_exif(image_bytes):
    try:
        image = Image.open(io.BytesIO(image_bytes))
        exif = image._getexif()
        if not exif:
            return {}
        return {
            ExifTags.TAGS.get(tag, tag): value
            for tag, value in exif.items()
            if isinstance(tag, int)
        }
    except Exception:
        return {}


def analyze_exif(image_bytes):
    exif = safe_get_exif(image_bytes)
    issues = []
    metrics = {}

    if not exif:
        metrics["exif_present"] = False
        score = 0.84
        issues.append("No EXIF metadata found")
        return {"issues": issues, "metrics": metrics, "feature_scores": {"exif_score": score}}

    metrics["exif_present"] = True
    datetime_original = exif.get("DateTimeOriginal") or exif.get("DateTime")
    modify_date = exif.get("ModifyDate") or exif.get("DateTimeDigitized")
    software = exif.get("Software") or exif.get("ImageSoftware")

    metrics["DateTimeOriginal"] = datetime_original or None
    metrics["ModifyDate"] = modify_date or None
    metrics["Software"] = software or None

    score = 1.0
    if not datetime_original and not modify_date:
        issues.append("Original capture date metadata is missing")
        score -= 0.12

    if software:
        normalized = str(software).lower()
        for candidate in SUSPICIOUS_SOFTWARE:
            if candidate.lower() in normalized:
                issues.append(f"Image appears to have been edited with {candidate}")
                score -= 0.25
                break

    score = max(min(score, 1.0), 0.0)
    return {"issues": issues, "metrics": metrics, "feature_scores": {"exif_score": round(score, 3)}}
