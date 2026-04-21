from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import cv2
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from auto_fix import auto_crop_to_dv_standard
from checker import analyze_photo
from config import DEFAULT_MODE, STRICT_MODE
from image_utils import decode_upload_image

VALID_MODES = {DEFAULT_MODE, STRICT_MODE}
ALLOWED_BINARY_UPLOAD_TYPES = {"application/octet-stream"}

app = FastAPI(
    title="DV Photo Checker CV Service",
    version="2.2",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _normalize_mode(mode: str | None) -> str:
    return mode if mode in VALID_MODES else DEFAULT_MODE


def _decorate_validation_result(result: dict[str, Any]) -> dict[str, Any]:
    score = float(result.get("score", 0.0))
    result.setdefault("pass_probability", round(score / 100.0, 3))
    return result


async def _extract_request_image(
    request: Request,
    image: UploadFile | None,
    form_mode: str,
) -> tuple[bytes | str, str]:
    if image is not None:
        content_type = (image.content_type or "").lower()
        if content_type and not content_type.startswith("image/") and content_type not in ALLOWED_BINARY_UPLOAD_TYPES:
            raise HTTPException(status_code=400, detail="File must be an image")

        contents = await image.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty image file")

        return contents, _normalize_mode(form_mode)

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Request must be multipart/form-data or application/json",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    image_data = payload.get("image")
    if not isinstance(image_data, str) or not image_data.strip():
        raise HTTPException(status_code=400, detail="No image provided")

    return image_data, _normalize_mode(payload.get("mode"))


def _auto_fix_image(image_input: bytes | str) -> bytes:
    image = decode_upload_image(image_input)
    if image is None or image.size == 0:
        raise ValueError("Invalid image provided")

    fixed_image, _, _ = auto_crop_to_dv_standard(image)
    success, encoded = cv2.imencode(".jpg", fixed_image)
    if not success:
        raise RuntimeError("Failed to encode fixed image")

    return encoded.tobytes()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "cv-service"}


@app.post("/validate")
async def validate(
    request: Request,
    image: UploadFile | None = File(default=None),
    mode: str = Form(DEFAULT_MODE),
):
    try:
        image_input, resolved_mode = await _extract_request_image(request, image, mode)
        result = await run_in_threadpool(analyze_photo, image_input, resolved_mode)
        return _decorate_validation_result(result)
    except HTTPException:
        raise
    except Exception as exc:
        import traceback

        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "valid": False,
                "score": 0,
                "status": "ERROR",
                "issues": [f"Internal error: {str(exc)}"],
                "warnings": [],
                "decision_reason": "Internal server error during analysis",
            },
        )


@app.post("/auto-fix")
async def auto_fix(
    request: Request,
    image: UploadFile | None = File(default=None),
    mode: str = Form(DEFAULT_MODE),
):
    try:
        image_input, _ = await _extract_request_image(request, image, mode)
        fixed_bytes = await run_in_threadpool(_auto_fix_image, image_input)
        return Response(content=fixed_bytes, media_type="image/jpeg")
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal error: {str(exc)}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
