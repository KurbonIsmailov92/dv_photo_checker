FROM golang:1.22-alpine AS go-builder

WORKDIR /build

COPY backend-go/go.mod backend-go/go.sum ./
RUN go mod download

COPY backend-go/ .
RUN CGO_ENABLED=0 GOOS=linux go build -o /main .


FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY cv-service-python/ /app/
COPY entrypoint.sh /app/entrypoint.sh

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir --retries 10 --timeout 120 -r requirements.txt && \
    chmod +x /app/entrypoint.sh

ENV CV_SERVICE_URL=http://127.0.0.1:8000 \
    GIN_MODE=release \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

COPY --from=go-builder /main /app/main

EXPOSE 8080
EXPOSE 8000

CMD ["/app/entrypoint.sh"]
