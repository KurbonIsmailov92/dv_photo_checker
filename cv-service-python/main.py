from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import cv2
import numpy as np
from face import validate_face
from background import validate_background
from blur import validate_blur
from lighting import validate_lighting
from auto_fix import auto_fix_image
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DV Photo Validator Pro CV Service", version="2.0.0")

class ValidationResponse(BaseModel):
    valid: bool
    score: int
    pass_probability: float
    issues: List[str]
    metrics: Dict[str, Any]
    detail: Dict[str, Any] = {}
    fixed_image: Optional[bytes] = None  # Base64 encoded if auto_fix

@app.post("/validate", response_model=ValidationResponse)
async def validate_image(
    image: UploadFile = File(...),
    auto_fix: bool = Form(False)
):
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Read image
    contents = await image.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    # Basic image validation
    issues = []
    metrics = {}
    score = 100
    pass_probability = 1.0

    # Check resolution
    height, width = img.shape[:2]
    if width != 600 or height != 600:
        issues.append(f"Resolution must be 600x600, got {width}x{height}")
        score -= 50
        pass_probability *= 0.5

    # Check format (assuming JPEG)
    if not image.filename.lower().endswith('.jpg') and not image.filename.lower().endswith('.jpeg'):
        issues.append("Format must be JPEG")
        score -= 20
        pass_probability *= 0.8

    # Check file size
    if len(contents) > 240 * 1024:
        issues.append(f"File size must be < 240KB, got {len(contents)/1024:.1f}KB")
        score -= 20
        pass_probability *= 0.9

    # Face validation (now includes pose, eye level, glasses)
    face_result = validate_face(img)
    issues.extend(face_result["issues"])
    metrics.update(face_result["metrics"])
    face_score = face_result["score_contrib"]

    # Background validation
    bg_result = validate_background(img)
    issues.extend(bg_result["issues"])
    metrics.update(bg_result["metrics"])
    bg_score = bg_result["score_contrib"]

    # Blur validation
    blur_result = validate_blur(img)
    issues.extend(blur_result["issues"])
    metrics.update(blur_result["metrics"])
    blur_score = blur_result["score_contrib"]

    # Lighting validation
    light_result = validate_lighting(img)
    issues.extend(light_result["issues"])
    metrics.update(light_result["metrics"])
    light_score = light_result["score_contrib"]

    # Weighted scoring
    weights = {
        "face": 0.4,
        "background": 0.3,
        "lighting": 0.15,
        "blur": 0.15
    }
    overall_score = 100 * (face_score * weights["face"] + bg_score * weights["background"] + light_score * weights["lighting"] + blur_score * weights["blur"])
    pass_probability = overall_score / 100.0

    score = int(overall_score)
    valid = len(issues) == 0 and score >= 80  # Threshold for valid

    detail = {
        "width": width,
        "height": height,
        "file_size_kb": len(contents) / 1024,
        "format": image.content_type
    }

    fixed_image = None
    if auto_fix and not valid:
        fixed_img = auto_fix_image(img, metrics)
        if fixed_img is not None:
            _, buffer = cv2.imencode('.jpg', fixed_img)
            fixed_image = buffer.tobytes()

    return ValidationResponse(
        valid=valid,
        score=score,
        pass_probability=pass_probability,
        issues=issues,
        metrics=metrics,
        detail=detail,
        fixed_image=fixed_image
    )

@app.get("/health")
async def health():
    return {"status": "ok"}