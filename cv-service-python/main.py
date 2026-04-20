from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import numpy as np
import cv2
import traceback

from checker import analyze_photo
from auto_fix import auto_crop_to_dv_standard

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

# ✅ FIXED: теперь принимает файл
@app.post("/validate")
async def validate(file: UploadFile = File(...)):
    try:
        contents = await file.read()

        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return JSONResponse(status_code=400, content={"error": "Invalid image"})

        result = analyze_photo(img)
        return result

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "valid": False,
                "score": 0,
                "status": "ERROR",
                "issues": [str(e)],
            },
        )

# ✅ FIXED: возвращает image (как ждёт Go)
@app.post("/auto-fix")
async def auto_fix(file: UploadFile = File(...)):
    try:
        contents = await file.read()

        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        cropped, _, _ = auto_crop_to_dv_standard(img)

        _, buffer = cv2.imencode(".jpg", cropped)

        return Response(content=buffer.tobytes(), media_type="image/jpeg")

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})