# === Stage 1: Build dependencies ===
FROM python:3.12-slim AS builder

WORKDIR /build

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

# Install dependencies with pip mirror (Aliyun for faster downloads)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel hatchling && \
    pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ .

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

# Copy application source code
COPY . ./

EXPOSE 8000

# Production mode - no reload
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
