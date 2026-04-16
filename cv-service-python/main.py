from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Dict, Any
import cv2
from face_analyzer import validate_face_geometry
from background_analysis import validate_background
from blur_analysis import validate_blur
from lighting_analysis import validate_lighting
from auto_fix import auto_crop_to_dv_standard
from scoring_engine import aggregate_feature_scores, compute_final_score, build_decision
from config import DEFAULT_MODE, STRICT_MODE
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
    warnings: List[str]
    decision_reason: str
    metrics: Dict[str, Any]
    detail: Dict[str, Any] = {}

@app.post("/validate", response_model=ValidationResponse)
async def validate_image(
    image: UploadFile = File(...),
    mode: str = Form(DEFAULT_MODE)
):
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    mode = mode if mode in {DEFAULT_MODE, STRICT_MODE} else DEFAULT_MODE
    contents = await image.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    height, width = img.shape[:2]
    detail = {
        "width": width,
        "height": height,
        "file_size_kb": round(len(contents) / 1024.0, 2),
        "format": image.content_type,
        "filename": image.filename,
        "mode": mode,
    }

    if width != 600 or height != 600:
        detail["recommended_resolution"] = "600x600"
    if not image.filename.lower().endswith('.jpg') and not image.filename.lower().endswith('.jpeg'):
        detail["recommended_format"] = "JPEG"

    cropped_image, crop_applied, crop_info = auto_crop_to_dv_standard(img)
    detail["after_crop"] = crop_applied
    detail["crop_info"] = crop_info

    issues: List[str] = []
    warnings: List[str] = []
    metrics: Dict[str, Any] = {}
    combined_feature_scores: Dict[str, float] = {}

    face_result = validate_face_geometry(cropped_image, mode=mode)
    issues.extend(face_result["issues"])
    warnings.extend(face_result["warnings"])
    metrics.update(face_result["metrics"])
    combined_feature_scores.update(face_result["feature_scores"])

    background_result = validate_background(cropped_image, face_rect=None, mode=mode)
    issues.extend(background_result["issues"])
    warnings.extend(background_result["warnings"])
    metrics.update(background_result["metrics"])
    combined_feature_scores.update(background_result["feature_scores"])

    blur_result = validate_blur(cropped_image, mode=mode)
    issues.extend(blur_result["issues"])
    warnings.extend(blur_result["warnings"])
    metrics.update(blur_result["metrics"])
    combined_feature_scores.update(blur_result["feature_scores"])

    lighting_result = validate_lighting(cropped_image, face_rect=None, mode=mode)
    issues.extend(lighting_result["issues"])
    warnings.extend(lighting_result["warnings"])
    metrics.update(lighting_result["metrics"])
    combined_feature_scores.update(lighting_result["feature_scores"])

    feature_scores = aggregate_feature_scores(combined_feature_scores)
    final_score = compute_final_score(feature_scores)
    decision = build_decision(final_score, issues, warnings)

    return ValidationResponse(
        valid=decision["valid"],
        score=decision["score"],
        pass_probability=decision["pass_probability"],
        features=feature_scores,
        issues=list(dict.fromkeys(issues)),
        warnings=list(dict.fromkeys(warnings)),
        decision_reason=decision["decision_reason"],
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

    fixed_img, _, _ = auto_crop_to_dv_standard(img)
    if fixed_img is None:
        raise HTTPException(status_code=422, detail="Unable to auto-crop the provided image")

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