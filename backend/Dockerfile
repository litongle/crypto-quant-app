# === Stage 1: Build dependencies ===
FROM python:3.12-slim AS builder

WORKDIR /build

ARG INSTALL_DEV=false

# Use Aliyun mirror for faster apt downloads (China-optimized)
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# Install build-time dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency configuration (separate from source for better caching)
COPY pyproject.toml README.md ./

# Install dependencies with pip mirror (Aliyun) + timeout/retry for flaky networks
RUN pip install --no-cache-dir --timeout=120 --retries=5 \
        --upgrade pip setuptools wheel hatchling && \
    if [ "$INSTALL_DEV" = "true" ]; then \
        pip install --no-cache-dir --timeout=120 --retries=5 \
            -i https://mirrors.aliyun.com/pypi/simple/ \
            --trusted-host mirrors.aliyun.com ".[dev]"; \
    else \
        pip install --no-cache-dir --timeout=120 --retries=5 \
            -i https://mirrors.aliyun.com/pypi/simple/ \
            --trusted-host mirrors.aliyun.com .; \
    fi

# === Stage 2: Runtime image ===
FROM python:3.12-slim

WORKDIR /app

# Use Aliyun mirror for faster apt downloads
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# Install only runtime dependencies (no compilation tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built dependencies from builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data && chown -R appuser:appuser /app

# Copy application source code
COPY . ./

# Switch to non-root user
USER appuser

# Python runtime settings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: production mode (no reload)
# Override in docker-compose for dev: add --reload flag
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
