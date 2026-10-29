# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Системные зависимости (psycopg требует libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.30" \
        "sqlalchemy>=2.0" \
        "psycopg[binary]>=3.1" \
        "redis>=5.0" \
        "rq>=1.16" \
        "pydantic>=2.7" \
        "httpx>=0.27" \
        "numpy>=1.26"

COPY src /app/src

ENV PYTHONPATH=/app/src