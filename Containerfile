# Multi-stage Containerfile for Nunzio - Local Workout Assistant
# Optimized for Podman deployment with external MySQL and Ollama services

# Build stage
FROM python:3.13-slim AS builder

# Set build environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy project files
WORKDIR /app
COPY pyproject.toml ./

# Install dependencies
RUN pip install --upgrade pip && \
    pip install -e .[dev]

# Production stage
FROM python:3.13-slim AS production

# Set production environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create non-root user for security
RUN groupadd -r nunzio && \
    useradd -r -g nunzio -d /app -s /bin/bash nunzio

# Set up application directory
WORKDIR /app

# Copy application code
COPY --chown=nunzio:nunzio src/ ./src/
COPY --chown=nunzio:nunzio .env.example .env

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data && \
    chown -R nunzio:nunzio /app

# Switch to non-root user
USER nunzio

# Health check script
COPY --chown=nunzio:nunzio <<'EOF' /app/healthcheck.py
#!/usr/bin/env python3
"""Health check script for Nunzio application."""
import asyncio
import sys
from src.nunzio.database.connection import db_manager

async def check_health():
    """Check database connection health."""
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

RUN chmod +x /app/healthcheck.py

# Expose port (not needed for Telegram bot, but good practice)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python /app/healthcheck.py

# Set default command
CMD ["python", "-m", "src.nunzio.main"]

# Labels for metadata
LABEL maintainer="philip" \
      version="0.1.0" \
      description="Nunzio - Local Workout Assistant" \
      org.opencontainers.image.title="nunzio" \
      org.opencontainers.image.description="Local workout tracking assistant with Telegram bot" \
      org.opencontainers.image.version="0.1.0"