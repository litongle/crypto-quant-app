# 币钱袋量化交易后端

## 环境要求

- Python 3.11+
- PostgreSQL 15+
- Redis 7+

## 快速开始

```bash
# 1. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux/Mac

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 配置环境变量（必须！无默认值）
cp .env.example .env
# 编辑 .env 填入实际配置，以下变量为必填：
#   SECRET_KEY, DATABASE_URL, JWT_SECRET_KEY

# 4. 数据库迁移
alembic upgrade head

# 5. 运行开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 6. 初始化种子数据（可选）
python -m app.seed_data

# 7. 运行测试
pytest

# 8. 代码检查
ruff check .
mypy app/
```

## 项目结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 应用入口（结构化日志、CORS 加固）
│   ├── config.py                # 配置管理（无硬编码默认密钥）
│   ├── database.py              # PostgreSQL 异步连接
│   ├── redis.py                 # Redis 连接池（asyncio.Lock 线程安全）
│   ├── seed_data.py             # 初始数据种子
│   ├── api/                     # API 路由
│   │   ├── deps.py              # 依赖注入（get_current_user, get_db 等）
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── auth.py          # 认证（登录/注册/刷新 Token）
│   │       ├── users.py         # 用户信息
│   │       ├── strategies.py    # 策略模板 & 实例
│   │       ├── market.py        # 行情数据
│   │       ├── orders.py        # 订单管理
│   │       ├── asset.py         # 资产汇总/持仓/权益曲线
│   │       └── backtest.py      # 回测执行
│   ├── core/                    # 核心模块
│   │   ├── security.py          # 安全：JWT + AES-256(Fernet) 加密
│   │   ├── exceptions.py        # 统一异常处理
│   │   ├── exchange_adapter.py  # 交易所适配器（Binance/OKX，httpx 单例）
│   │   ├── strategy_engine.py   # 策略引擎
│   │   └── schemas.py           # 通用 Schema
│   ├── models/                  # SQLAlchemy 模型
│   │   ├── __init__.py
│   │   ├── user.py              # 用户模型
│   │   ├── strategy.py          # 策略模板 & 实例
│   │   ├── exchange.py          # 交易所账户（API Key 加密存储）
│   │   └── order.py             # 订单 & 信号
│   ├── services/                # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── auth_service.py      # 认证服务
│   │   ├── asset_service.py     # 资产服务
│   │   ├── backtest_service.py  # 回测服务
│   │   ├── market_service.py    # 行情服务（Redis 缓存）
│   │   ├── order_service.py     # 订单服务
│   │   └── strategy_service.py  # 策略服务
│   └── repositories/            # 数据访问层
│       ├── __init__.py
│       ├── base.py              # 基础仓储
│       ├── user_repo.py         # 用户仓储
│       ├── strategy_repo.py     # 策略仓储
│       └── trading_repo.py      # 交易仓储
└── pyproject.toml               # 项目依赖 & 配置
```

## API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## 环境变量

所有环境变量定义在 `.env.example` 中，以下为必填项（无默认值）：

```env
# 应用
APP_NAME=CryptoQuant
APP_VERSION=1.0.0
DEBUG=true
SECRET_KEY=                    # 必填！无默认值
JWT_SECRET_KEY=                # 必填！无默认值
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# 数据库
DATABASE_URL=                  # 必填！无默认值
                                # 格式: postgresql+asyncpg://user:password@localhost:5432/crypto_quant

# Redis
REDIS_URL=redis://localhost:6379/0
```

> ⚠️ **安全提示**：`SECRET_KEY`、`DATABASE_URL`、`JWT_SECRET_KEY` 在 `config.py` 中无默认值，必须在 `.env` 文件中配置，否则服务无法启动。

## 安全特性

- **API Key 加密存储**：交易所 API Key/Secret/Passphrase 使用 AES-256 (Fernet) 加密
- **JWT Token 类型校验**：Refresh Token 验证时校验 token_type
- **数值范围校验**：金融数值字段使用 `Field(gt=0)` 防止非法值
- **CORS 加固**：明确限制 methods 和 headers
- **结构化日志**：使用 Python logging 替代 print

## 开发规范

详见 `../docs/standards/CODE_STANDARDS.md` 和 `../docs/standards/CODE_REVIEW_PROCESS.md`
