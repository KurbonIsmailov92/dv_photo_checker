from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Dict, Any
import cv2
import numpy as np
from face_analysis import validate_face
from background_analysis import validate_background
from blur_analysis import validate_blur
from lighting_analysis import validate_lighting
from exif_analysis import analyze_exif
from manipulation_analysis import validate_manipulation
from scoring_engine import aggregate_features
from auto_fix import auto_fix_image
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DV Photo Validator Pro CV Service", version="3.0.0")

class ValidationResponse(BaseModel):
    valid: bool
    score: float
    pass_probability: float
    features: Dict[str, float]
    issues: List[str]
    decision_reason: str
    metrics: Dict[str, Any]
    detail: Dict[str, Any] = {}

@app.post("/validate", response_model=ValidationResponse)
async def validate_image(image: UploadFile = File(...)):
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    contents = await image.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    issues: List[str] = []
    metrics: Dict[str, Any] = {}
    feature_scores: Dict[str, float] = {}

    height, width = img.shape[:2]
    detail = {
        "width": width,
        "height": height,
        "file_size_kb": round(len(contents) / 1024.0, 2),
        "format": image.content_type,
        "filename": image.filename,
    }

    if width != 600 or height != 600:
        detail["recommended_resolution"] = "600x600"
    if not image.filename.lower().endswith('.jpg') and not image.filename.lower().endswith('.jpeg'):
        detail["recommended_format"] = "JPEG"

    exif_result = analyze_exif(contents)
    issues.extend(exif_result["issues"])
    metrics.update(exif_result["metrics"])
    feature_scores.update(exif_result["feature_scores"])

    face_result = validate_face(img)
    issues.extend(face_result["issues"])
    metrics.update(face_result["metrics"])
    feature_scores.update(face_result["feature_scores"])

    face_rect = None
    if face_result["metrics"].get("face_rect"):
        face_rect = tuple(face_result["metrics"]["face_rect"])

    background_result = validate_background(img, face_rect=face_rect)
    issues.extend(background_result["issues"])
    metrics.update(background_result["metrics"])
    feature_scores.update(background_result["feature_scores"])

    blur_result = validate_blur(img)
    issues.extend(blur_result["issues"])
    metrics.update(blur_result["metrics"])
    feature_scores.update(blur_result["feature_scores"])

    lighting_result = validate_lighting(img, face_rect=face_rect)
    issues.extend(lighting_result["issues"])
    metrics.update(lighting_result["metrics"])
    feature_scores.update(lighting_result["feature_scores"])

    manipulation_result = validate_manipulation(img)
    issues.extend(manipulation_result["issues"])
    metrics.update(manipulation_result["metrics"])
    feature_scores.update(manipulation_result["feature_scores"])

    scoring = aggregate_features(feature_scores)
    issues = list(dict.fromkeys(issues))

    return ValidationResponse(
        valid=scoring["valid"],
        score=scoring["final_score"],
        pass_probability=scoring["pass_probability"],
        features=scoring["feature_scores"],
        issues=issues,
        decision_reason=scoring["decision_reason"],
        metrics=metrics,
        detail=detail,
    )

@app.post("/auto-fix")
async def auto_fix_image_endpoint(image: UploadFile = File(...)):
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    contents = await image.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    fixed_img = auto_fix_image(img, {})
    if fixed_img is None:
        raise HTTPException(status_code=422, detail="Unable to auto-fix the provided image")

    success, buffer = cv2.imencode('.jpg', fixed_img)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to encode fixed image")

    return Response(content=buffer.tobytes(), media_type="image/jpeg")

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)