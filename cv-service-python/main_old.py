from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Dict, Any
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import asyncio
from face_analyzer import validate_face_geometry
from background_analysis import validate_background
from blur_analysis import validate_blur
from lighting_analysis import validate_lighting
from auto_fix import auto_crop_to_dv_standard
from config import (
    DEFAULT_MODE, STRICT_MODE, WEIGHT_FACE_GEOMETRY, WEIGHT_BACKGROUND,
    WEIGHT_BLUR, WEIGHT_LIGHTING, SCORE_PASS_THRESHOLD, SCORE_WARNING_THRESHOLD
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DV Photo Validator Pro CV Service", version="4.0.0")

class ValidationResponse(BaseModel):
    valid: bool
    score: float  # 0-100 scale
    pass_probability: float  # Same as score for backward compatibility
    features: Dict[str, float]  # 0-1 scale individual scores
    issues: List[str]
    warnings: List[str]
    decision_reason: str
    metrics: Dict[str, Any]
    detail: Dict[str, Any] = {}


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """Clamp value to range [minimum, maximum]"""
    return max(min(value, maximum), minimum)


def compute_overall_score(feature_scores: Dict[str, float]) -> float:
    """
    Compute overall score (0-100) from weighted feature scores
    """
    face_score = feature_scores.get("face_geometry_score", 0.0)
    background_score = feature_scores.get("background_score", 0.0)
    blur_score = feature_scores.get("blur_score", 0.0)
    lighting_score = feature_scores.get("lighting_score", 0.0)

    # Weighted sum (0-1 scale)
    weighted_score = (
        face_score * WEIGHT_FACE_GEOMETRY +
        background_score * WEIGHT_BACKGROUND +
        blur_score * WEIGHT_BLUR +
        lighting_score * WEIGHT_LIGHTING
    )

    # Convert to 0-100 scale
    return round(clamp(weighted_score) * 100.0, 1)


def determine_validation_result(score: float, issues: List[str]) -> tuple[bool, str]:
    """
    Determine if photo passes validation based on score and issues
    Returns: (valid, decision_reason)
    """
    if len(issues) > 0:
        return False, "Photo has critical issues that prevent validation"

    if score >= SCORE_PASS_THRESHOLD:
        return True, "Photo passes DV validation standards"
    elif score >= SCORE_WARNING_THRESHOLD:
        return True, "Photo passes with minor quality concerns"
    else:
        return False, "Photo quality is below minimum standards"


def process_image_sync(contents: bytes, image: UploadFile, mode: str) -> ValidationResponse:
    """
    Synchronous image processing: crop → validate → score
    """
    # Decode image
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    height, width = img.shape[:2]
    detail = {
        "width": width,
        "height": height,
        "file_size_kb": round(len(contents) / 1024.0, 2),
        "format": image.content_type or "unknown",
        "filename": image.filename or "unknown",
        "mode": mode,
    }

    # Step 1: Auto-crop to 600x600
    cropped_image, crop_applied, crop_info = auto_crop_to_dv_standard(img)
    detail["after_crop"] = crop_applied
    detail["crop_info"] = crop_info

    # Step 2: Validate cropped image (600x600)
    issues = []
    warnings = []
    metrics = {}
    combined_feature_scores = {}

    # Face geometry validation
    face_result = validate_face_geometry(cropped_image, mode=mode)
    issues.extend(face_result["issues"])
    warnings.extend(face_result["warnings"])
    metrics.update(face_result["metrics"])
    combined_feature_scores.update(face_result["feature_scores"])

    # Background validation
    background_result = validate_background(cropped_image, face_rect=None, mode=mode)
    issues.extend(background_result["issues"])
    warnings.extend(background_result["warnings"])
    metrics.update(background_result["metrics"])
    combined_feature_scores.update(background_result["feature_scores"])

    # Blur validation
    blur_result = validate_blur(cropped_image, mode=mode)
    issues.extend(blur_result["issues"])
    warnings.extend(blur_result["warnings"])
    metrics.update(blur_result["metrics"])
    combined_feature_scores.update(blur_result["feature_scores"])

    # Lighting validation
    lighting_result = validate_lighting(cropped_image, face_rect=None, mode=mode)
    issues.extend(lighting_result["issues"])
    warnings.extend(lighting_result["warnings"])
    metrics.update(lighting_result["metrics"])
    combined_feature_scores.update(lighting_result["feature_scores"])

    # Step 3: Compute final score (0-100 scale)
    final_score = compute_overall_score(combined_feature_scores)

    # Step 4: Determine validation result
    valid, decision_reason = determine_validation_result(final_score, issues)

    # Ensure no duplicate issues/warnings
    issues = list(dict.fromkeys(issues))
    warnings = list(dict.fromkeys(warnings))

    return ValidationResponse(
        valid=valid,
        score=final_score,  # 0-100 scale
        pass_probability=final_score,  # Same as score
        features=combined_feature_scores,  # 0-1 scale
        issues=issues,
        warnings=warnings,
        decision_reason=decision_reason,
        metrics=metrics,
        detail=detail,
    )


def process_auto_fix_sync(contents: bytes, image: UploadFile) -> bytes:
    """Synchronous auto-fix: crop only, return JPEG bytes"""
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    # Apply auto-crop
    fixed_img, _, _ = auto_crop_to_dv_standard(img)
    if fixed_img is None:
        raise HTTPException(status_code=422, detail="Unable to auto-crop the provided image")

    # Encode as JPEG
    success, buffer = cv2.imencode('.jpg', fixed_img)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to encode fixed image")

    return buffer.tobytes()


@app.post("/validate", response_model=ValidationResponse)
async def validate_image(
    image: UploadFile = File(...),
    mode: str = Form(DEFAULT_MODE)
):
    """Validate photo quality and DV compliance"""
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    mode = mode if mode in {DEFAULT_MODE, STRICT_MODE} else DEFAULT_MODE
    contents = await image.read()

    # Run synchronous processing in thread pool
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, process_image_sync, contents, image, mode)

    return result


@app.post("/auto-fix")
async def auto_fix_image_endpoint(image: UploadFile = File(...)):
    """Auto-crop image to 600x600 DV standard"""
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    contents = await image.read()

    # Run synchronous processing in thread pool
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        fixed_img_bytes = await loop.run_in_executor(executor, process_auto_fix_sync, contents, image)

    return Response(content=fixed_img_bytes, media_type="image/jpeg")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "version": "4.0.0"}
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


def process_auto_fix_sync(contents: bytes, image: UploadFile) -> bytes:
    """Synchronous auto-fix processing function to run in thread pool."""
    import numpy as np
    import cv2
    
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

    return buffer.tobytes()

@app.post("/validate", response_model=ValidationResponse)
async def validate_image(
    image: UploadFile = File(...),
    mode: str = Form(DEFAULT_MODE)
):
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    mode = mode if mode in {DEFAULT_MODE, STRICT_MODE} else DEFAULT_MODE
    contents = await image.read()
    
    # Run synchronous image processing in thread pool
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, process_image_sync, contents, image, mode)
    
    return result

@app.post("/auto-fix")
async def auto_fix_image_endpoint(image: UploadFile = File(...)):
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    contents = await image.read()
    
    # Run synchronous image processing in thread pool
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        fixed_img_bytes = await loop.run_in_executor(executor, process_auto_fix_sync, contents, image)
    
    return Response(content=fixed_img_bytes, media_type="image/jpeg")

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)