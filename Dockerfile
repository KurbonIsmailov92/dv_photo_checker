# =============================================
#  DV Photo Validator — FIXED Dockerfile
# =============================================

# === 1. Python CV ===
FROM python:3.11-slim AS python-builder
WORKDIR /app/cv-service-python
COPY cv-service-python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cv-service-python/ .

# === 2. Go backend ===
FROM golang:1.22-alpine AS go-builder
WORKDIR /app/backend-go
COPY backend-go/go.mod backend-go/go.sum ./
RUN go mod download
COPY backend-go/ .
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/main .

# === 3. Final image ===
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python
COPY --from=python-builder /app/cv-service-python /app/cv-service-python
COPY --from=python-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Go
COPY --from=go-builder /app/main /app/main

WORKDIR /app

EXPOSE 8080

# 🔥 Запуск двух сервисов
CMD ["sh", "-c", "cd /app/cv-service-python && uvicorn main:app --host 0.0.0.0 --port 8000 & cd /app && ./main"]