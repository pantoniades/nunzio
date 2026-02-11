# Multi-stage Containerfile for Nunzio - Local Workout Assistant
# Optimized for Podman deployment with external MySQL and Ollama services

# Build stage
FROM python:3.13-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --upgrade pip && \
    pip install .

# Production stage
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

COPY --from=builder /opt/venv /opt/venv

RUN groupadd -r nunzio && \
    useradd -r -g nunzio -d /app -s /bin/bash nunzio

WORKDIR /app

RUN mkdir -p /app/logs /app/data && \
    chown -R nunzio:nunzio /app

USER nunzio

# Health check script
COPY --chown=nunzio:nunzio <<'EOF' /app/healthcheck.py
#!/usr/bin/env python3
"""Health check script for Nunzio application."""
import asyncio
import sys
from nunzio.database.connection import db_manager

async def check_health():
    try:
        await db_manager.initialize()
        is_healthy = await db_manager.health_check()
        await db_manager.close()
        return 0 if is_healthy else 1
    except Exception:
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(check_health()))
EOF

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python /app/healthcheck.py

CMD ["nunzio-bot"]

LABEL maintainer="philip" \
      version="0.1.0" \
      description="Nunzio - Local Workout Assistant" \
      org.opencontainers.image.title="nunzio" \
      org.opencontainers.image.version="0.1.0"