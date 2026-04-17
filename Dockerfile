# =============================================
#  DV Photo Checker — CLEAN & WORKING
# =============================================

# ---------- Python builder ----------
FROM python:3.11-slim AS python-builder

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
    pip install --no-cache-dir --prefix=/install -r requirements.txt

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
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python зависимости
COPY --from=python-builder /install /usr/local
COPY --from=python-builder /app/cv-service-python /app/cv-service-python

# Go бинарник
COPY --from=go-builder /app/main /app/main

# Порты
EXPOSE 8080
EXPOSE 8000

# Запуск (важно: exec для сигналов)
CMD ["sh", "-c", "uvicorn cv-service-python.main:app --host 0.0.0.0 --port 8000 & exec /app/main"]