# DV Photo Validator Pro

A production-ready system to validate and auto-fix photos for US DV Lottery applications, similar or superior to ASTAR Photo Validator.

## Features

- **Advanced Face Detection**: MediaPipe Face Mesh with 468 landmarks for precise measurements
- **Crown Detection**: Hybrid forehead landmark + bounding box with empirical offset
- **Pose Estimation**: solvePnP with 3D face model for accurate yaw/pitch/roll
- **Background Segmentation**: U2Net/rembg for real background removal and uniformity analysis
- **Weighted Scoring**: Robust scoring system (face 40%, background 30%, lighting 15%, blur 15%)
- **Auto-Fix**: Crop, resize, and background normalization with rembg
- **Explainable Results**: Detailed issues and metrics

## Architecture

- **Backend**: Go with Gin framework
- **CV Service**: Python with FastAPI, OpenCV, MediaPipe
- **Communication**: REST API

## Quick Start

### Using Docker (Recommended)

```bash
docker-compose up --build
```

### Manual Setup

#### Backend (Go)

```bash
cd backend-go
go mod tidy
go run main.go
```

#### CV Service (Python)

```bash
cd cv-service-python
pip install -r requirements.txt
uvicorn main:app --reload
```

## API Usage

### Validate Image
```bash
curl -X POST -F "image=@photo.jpg" -F "auto_fix=true" http://localhost:8080/validate
```

Response:
```json
{
  "valid": true,
  "score": 95,
  "pass_probability": 0.92,
  "issues": [],
  "metrics": {
    "head_ratio": 55.2,
    "eye_level": 62.1,
    "brightness": 120,
    "blur_score": 350,
    "face_angle": {
      "yaw": 2.1,
      "pitch": -1.5,
      "roll": 0.8
    }
  }
}
```

### CLI
```bash
go run main.go -validate photo.jpg -auto-fix
```

## Validation Rules

- **Resolution**: Exactly 600x600 px
- **Format**: JPEG, <240KB
- **Face**: One face, head 50-69% (crown to chin with landmark accuracy)
- **Eye Level**: 56-69% from bottom
- **Centering**: <7% horiz, <10% vert deviation
- **Pose**: Yaw/Pitch/Roll <15° using solvePnP
- **Background**: Uniform via rembg segmentation, low variance
- **Lighting**: 70-230 brightness, no face shadows
- **Blur**: Laplacian >100
- **Glasses**: Heuristic eye region detection

## Scoring System

**Weighted Algorithm** (robust against single failures):
- Face validation: 40%
- Background: 30%
- Lighting: 15%
- Blur: 15%

Score = 100 × (face_score × 0.4 + background_score × 0.3 + lighting_score × 0.15 + blur_score × 0.15)

Pass Probability = Score / 100

Valid if Score ≥ 80 and no critical issues.

## Project Structure

```
/backend-go
  main.go
  models/response.go

/cv-service-python
  main.py
  face.py (landmarks, pose)
  background.py (edges, segmentation)
  blur.py
  lighting.py
  auto_fix.py (crop, resize)
```

## License

MIT