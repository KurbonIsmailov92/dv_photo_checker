# =============================================
#  DV Photo Checker — FIXED & STABLE
# =============================================

FROM python:3.11-slim AS python-builder

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/cv-service-python

COPY cv-service-python/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY cv-service-python/ .

# === Go builder ===
FROM golang:1.22-alpine AS go-builder
WORKDIR /app/backend-go
COPY backend-go/go.mod backend-go/go.sum ./
RUN go mod download
COPY backend-go/ .
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/main .

# === Final image ===
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем Python окружение
COPY --from=python-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin
COPY --from=python-builder /app/cv-service-python /app/cv-service-python

# Копируем Go binary
COPY --from=go-builder /app/main /app/main

# Проверка MediaPipe (исправленная версия)
RUN python -c "
import mediapipe as mp
import cv2
print('✅ MediaPipe version:', mp.__version__)
print('✅ Has solutions:', hasattr(mp, 'solutions'))
print('✅ Face Mesh available:', hasattr(mp.solutions, 'face_mesh'))
print('✅ OpenCV version:', cv2.__version__)
"

EXPOSE 8080  # Go API
EXPOSE 8000  # Python CV Service

CMD ["sh", "-c", "cd /app/cv-service-python && uvicorn main:app --host 0.0.0.0 --port 8000 & ./main"]