# =============================================
#  DV Photo Checker — STABLE VERSION
# =============================================

FROM golang:1.22-alpine AS go-builder

WORKDIR /build
COPY backend-go/go.mod backend-go/go.sum ./
RUN go mod download
COPY backend-go/ .
RUN CGO_ENABLED=0 GOOS=linux go build -o /main .


FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY cv-service-python/ /app/

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --retries 10 --timeout 120 --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/app

COPY --from=go-builder /main /app/main

EXPOSE 8080
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8000 & until curl -s http://localhost:8000/health; do sleep 1; done; exec /app/main"]