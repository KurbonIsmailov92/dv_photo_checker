# =============================================
#  Astar Validator — Render-ready Dockerfile
# =============================================

# === 1. Собираем Python CV-сервис ===
FROM python:3.11-slim AS python-builder
WORKDIR /app/cv-service-python
COPY cv-service-python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cv-service-python/ .

# === 2. Собираем Go backend ===
FROM golang:1.22-alpine AS go-builder
WORKDIR /app/backend-go
COPY backend-go/go.mod backend-go/go.sum ./
RUN go mod download
COPY backend-go/ .
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/main .

# === 3. Финальный маленький образ ===
FROM python:3.11-slim

# Устанавливаем только самое нужное
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

# Копируем Python часть
COPY --from=python-builder /app/cv-service-python /app/cv-service-python
COPY --from=python-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Копируем собранный Go-бэкенд
COPY --from=go-builder /app/main /app/main

WORKDIR /app

# Если у тебя есть .env — копируем
COPY .env.example .env 2>/dev/null || true

# Открываем порт (Render будет смотреть на 8080 по умолчанию)
EXPOSE 8080

# Запускаем Go-приложение (оно должно запускать Python-сервис внутри или через HTTP)
CMD ["./main"]