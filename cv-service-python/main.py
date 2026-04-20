import sys
import os
from pathlib import Path

# === Важно: Добавляем папку в PYTHONPATH ===
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from checker import analyze_photo
from auto_fix import auto_crop_to_dv_standard

app = FastAPI(
    title="DV Photo Checker CV Service",
    description="Computer Vision service for DV Lottery photo validation",
    version="2.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "cv-service"}

@app.post("/validate")
async def validate_photo(data: dict):
    try:
        # Ожидаем base64 или bytes изображения
        image_data = data.get("image")
        mode = data.get("mode", "balanced")

        if not image_data:
            return JSONResponse(status_code=400, content={"error": "No image provided"})

        result = analyze_photo(image_data, mode=mode)
        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "valid": False,
                "score": 0,
                "status": "ERROR",
                "issues": [f"Server error: {str(e)}"]
            }
        )

@app.post("/auto-fix")
async def auto_fix_photo(data: dict):
    try:
        from image_utils import decode_upload_image
        image_data = data.get("image")
        if not image_data:
            return JSONResponse(status_code=400, content={"error": "No image provided"})
        
        img = decode_upload_image(image_data)
        cropped, _, _ = auto_crop_to_dv_standard(img)
        
        return {"success": True, "message": "Photo cropped successfully"}
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)