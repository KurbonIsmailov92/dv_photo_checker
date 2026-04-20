# =============================================
#  DV Photo Checker — Render / Local FINAL
# =============================================

FROM python:3.11-slim

# Системные библиотеки для OpenCV + MediaPipe
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

# Копируем Python сервис
COPY cv-service-python/ /app/cv-service-python/

# Устанавливаем зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/cv-service-python/requirements.txt

# Копируем Go бинарник (собираем автоматически)
COPY --from=go-builder /main /app/main

EXPOSE 8080

# Запуск: Python + Go
CMD ["sh", "-c", "uvicorn cv-service-python.main:app --host 0.0.0.0 --port 8000 & sleep 8 && exec /app/main"]