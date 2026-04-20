# =============================================
#  DV Photo Checker — Render FINAL FIXED
# =============================================

# ---------- Go builder ----------
FROM golang:1.22-alpine AS go-builder

WORKDIR /app/backend-go
COPY backend-go/go.mod backend-go/go.sum ./
RUN go mod download
COPY backend-go/ .
RUN CGO_ENABLED=0 GOOS=linux go build -o /main .

# ---------- Python + Final image ----------
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python сервис
COPY cv-service-python/ /app/cv-service-python/
COPY cv-service-python/requirements.txt /app/cv-service-python/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/cv-service-python/requirements.txt

# Go бинарник из builder stage
COPY --from=go-builder /main /app/main

EXPOSE 8080

# Запуск Python + Go
CMD ["sh", "-c", "uvicorn cv-service-python.main:app --host 0.0.0.0 --port 8000 & sleep 8 && exec /app/main"]