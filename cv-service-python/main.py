from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import asyncio
import cv2
from auto_fix import auto_crop_to_dv_standard
from config import DEFAULT_MODE, STRICT_MODE
from checker import analyze_photo
from image_utils import decode_upload_image, ensure_bgr
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


def process_image_sync(contents: bytes, image: UploadFile, mode: str) -> ValidationResponse:
    """
    Synchronous image processing: crop → validate → score
    """
    img = ensure_bgr(decode_upload_image(contents))
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

    result = analyze_photo(img, mode=mode)
    detail.update(result["detail"])

    return ValidationResponse(
        valid=result["valid"],
        score=float(result["score"]),
        pass_probability=float(result["pass_probability"]),
        features=result["features"],
        issues=result["issues"],
        warnings=result["warnings"],
        decision_reason=result["decision_reason"],
        metrics=result["metrics"],
        detail=detail,
    )


def process_auto_fix_sync(contents: bytes, image: UploadFile) -> bytes:
    """Synchronous auto-fix: crop only, return JPEG bytes"""
    img = ensure_bgr(decode_upload_image(contents))
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    # Apply auto-crop
    fixed_img, _, _ = auto_crop_to_dv_standard(img)
    if fixed_img is None:
        raise HTTPException(status_code=422, detail="Unable to auto-crop the provided image")

    # Encode as JPEG
    success, buffer = cv2.imencode('.jpg', fixed_img, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
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