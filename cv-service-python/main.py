import sys
from pathlib import Path

# Добавляем текущую директорию в PYTHONPATH
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Импорты после настройки пути
from checker import analyze_photo
from auto_fix import auto_crop_to_dv_standard

app = FastAPI(
    title="DV Photo Checker CV Service",
    version="2.1"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "cv-service"}

@app.post("/validate")
async def validate(data: dict):
    try:
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
                "issues": [f"Internal error: {str(e)}"]
            }
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)