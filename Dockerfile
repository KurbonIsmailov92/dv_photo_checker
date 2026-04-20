# =============================================
#  DV Photo Checker — Render FIXED
# =============================================

# ---------- Python builder ----------
FROM python:3.11-slim AS python-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
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


# ---------- Go builder ----------
FROM golang:1.22-alpine AS go-builder

WORKDIR /app/backend-go
COPY backend-go/go.mod backend-go/go.sum ./
RUN go mod download
COPY backend-go/ .
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/main .


# ---------- Final image ----------
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

# Копируем Python зависимости и код
COPY --from=python-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-builder /app/cv-service-python /app/cv-service-python

# Копируем Go бинарник
COPY --from=go-builder /app/main /app/main

EXPOSE 8080

# Запуск: Python сервис в фоне + Go как главный процесс
CMD ["sh", "-c", "cd /app/cv-service-python && uvicorn main:app --host 0.0.0.0 --port 8000 & sleep 6 && cd /app && exec /app/main"]