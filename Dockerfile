# =============================================
#  DV Photo Checker — Render FULL WORKING
# =============================================

# ---------- 1. Go Builder ----------
FROM golang:1.22-alpine AS go-builder

WORKDIR /app/backend-go
COPY backend-go/go.mod backend-go/go.sum ./
RUN go mod download
COPY backend-go/ .
RUN CGO_ENABLED=0 GOOS=linux go build -o /main .

# ---------- 2. Final Image ----------
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1\
    libgomp1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем Python сервис
COPY cv-service-python/ /cv-service-python/

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/cv-service-python/requirements.txt

# Копируем Go бинарник из builder
COPY --from=go-builder /main /app/main

EXPOSE 8080

# Запуск: Python CV Service в фоне + Go API
CMD ["sh", "-c", "uvicorn cv-service-python.main:app --host 0.0.0.0 --port 8000 & sleep 8 && exec /app/main"]