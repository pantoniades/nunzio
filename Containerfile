# Multi-stage Containerfile for Nunzio - Local Workout Assistant
# Optimized for Podman deployment with external MySQL and OpenAI-compatible LLM server

# Build stage
FROM python:3.13-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_LINK_MODE=copy

# Use uv instead of pip to install dependencies. On this host's network a
# middlebox truncates HTTPS responses whose User-Agent identifies as "requests"
# (which pip's vendored HTTP stack uses), corrupting PyPI index pages and
# breaking `pip install`. uv ships its own HTTP client and is unaffected. It
# also installs from prebuilt wheels, so no compiler toolchain is needed.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/

RUN uv pip install --python /opt/venv/bin/python .

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
COPY --chown=nunzio:nunzio healthcheck.py /app/healthcheck.py

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python /app/healthcheck.py

CMD ["nunzio-bot"]

LABEL maintainer="philip" \
      version="0.1.0" \
      description="Nunzio - Local Workout Assistant" \
      org.opencontainers.image.title="nunzio" \
      org.opencontainers.image.version="0.1.0"