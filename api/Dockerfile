FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY config.yaml ./
COPY seed ./seed

ENV DB_PATH=/data/app.db \
    SEED_DIR=/app/seed \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
EXPOSE 8000

# Hosts like Render inject PORT; docker-compose relies on the 8000 default.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
