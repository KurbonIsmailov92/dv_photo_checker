# DV Photo Validator Pro

DV Photo Validator Pro checks and auto-fixes photos for US DV Lottery applications.

## Architecture

- `backend-go`: Go + Gin HTTP backend and UI
- `cv-service-python`: FastAPI service for image analysis
- Communication between services happens over HTTP

## Features

- Face geometry validation with MediaPipe landmarks and fallback face-box detection
- Weighted 0-100 scoring based on face geometry, background, blur, and lighting
- Auto-fix endpoint that crops and exports a DV-friendly 600x600 JPEG
- Structured response with issues, warnings, metrics, and crop metadata
- Support for both multipart uploads and JSON base64 payloads

## Quick Start

### Docker Compose

```bash
docker-compose up --build
```

### Render

Render can build the repository root with the top-level `Dockerfile`. That image starts both the Go backend and the Python CV service in one container, and the Go backend talks to the Python service over `http://127.0.0.1:8000`.

### Manual Run

Backend:

```bash
cd backend-go
go mod tidy
go run main.go
```

CV service:

```bash
cd cv-service-python
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

## API

Validate an image:

```bash
curl -X POST -F "image=@photo.jpg" http://localhost:8080/validate
```

Auto-fix an image:

```bash
curl -X POST -F "image=@photo.jpg" http://localhost:8080/auto-fix --output fixed.jpg
```

Example validation response:

```json
{
  "valid": true,
  "score": 91.4,
  "pass_probability": 0.914,
  "status": "PASS",
  "issues": [],
  "warnings": [],
  "decision_reason": "Photo passes DV standards",
  "metrics": {
    "head_percent": 58.1,
    "eye_level": 61.7,
    "blur_variance": 143.2,
    "mean_brightness": 132.4
  }
}
```

## Telegram Bot

Create `.env` in the project root:

```env
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
BACKEND_URL=http://localhost:8080
```

Then run:

```bash
cd telegram-bot
go mod tidy
go run .
```

## Project Structure

```text
/backend-go
  main.go
  models/response.go
  static/index.html

/cv-service-python
  main.py
  checker.py
  face_analyzer.py
  blur_analysis.py
  lighting_analysis.py
  auto_fix.py
  image_utils.py
```

## License

MIT
