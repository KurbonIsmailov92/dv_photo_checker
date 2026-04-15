# =============================================
#  DV Photo Validator — FIXED PRODUCTION
# =============================================

# === Python CV ===
FROM python:3.11-slim AS python-builder
WORKDIR /app/cv-service-python
COPY cv-service-python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cv-service-python/ .

# === Go backend ===
FROM golang:1.22-alpine AS go-builder
WORKDIR /app/backend-go
COPY backend-go/go.mod backend-go/go.sum ./
RUN go mod download
COPY backend-go/ .
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/main .

# === Final runtime ===
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python app (FULL, not partial libs)
COPY --from=python-builder /app/cv-service-python /app/cv-service-python

# Go binary
COPY --from=go-builder /app/main /app/main

WORKDIR /app

EXPOSE 8080
EXPOSE 8000

# Install full CV runtime deps (cv2, numpy, etc.)
RUN pip install --no-cache-dir -r /app/cv-service-python/requirements.txt

# Start both services
CMD ["sh", "-c", "cd /app/cv-service-python && uvicorn main:app --host 0.0.0.0 --port 8000 & cd /app && ./main"]