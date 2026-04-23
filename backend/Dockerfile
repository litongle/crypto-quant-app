FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（psycopg2 需要编译）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 预装关键依赖（避免每次重复编译）
RUN pip install --no-cache-dir \
    fastapi==0.109.2 \
    uvicorn[standard]==0.27.1 \
    sqlalchemy==2.0.25 \
    asyncpg==0.29.0 \
    pydantic==2.5.3 \
    "pydantic[email]==2.5.3" \
    pydantic-settings==2.1.0 \
    redis==5.0.1 \
    python-jose[cryptography]==3.3.0 \
    passlib[bcrypt]==1.7.4 \
    bcrypt==4.0.1 \
    python-multipart==0.0.9 \
    httpx==0.26.0 \
    structlog==24.1.0 \
    python-dotenv==1.0.0 \
    orjson==3.9.15 \
    numpy==1.26.4 \
    aiosqlite==0.20.0 \
    alembic==1.13.1 \
    && pip cache purge

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . 2>&1 | tail -5

EXPOSE 8000

# 不使用 reload，生产模式直接运行
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
