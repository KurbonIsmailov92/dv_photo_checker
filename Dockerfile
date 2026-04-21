# =============================================
#  DV Photo Checker — FINAL WORKING VERSION
# =============================================

# ---------- Go Builder ----------
FROM golang:1.22-alpine AS go-builder

WORKDIR /build
COPY backend-go/go.mod backend-go/go.sum ./
RUN go mod download
COPY backend-go/ .
RUN CGO_ENABLED=0 GOOS=linux go build -o /main .

# ---------- Final Image ----------
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем Python сервис **плоско** (самый надёжный способ)
COPY cv-service-python/ /app/

# Устанавливаем зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем Go бинарник
COPY --from=go-builder /main /app/main

EXPOSE 8080

# Запуск обоих сервисов (Python + Go)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 & sleep 6 && exec /app/main"]