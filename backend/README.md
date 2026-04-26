# 币钱袋量化交易后端

## 环境要求

- Python 3.12+
- PostgreSQL 16+（可选，默认 SQLite 零配置启动）
- Redis 7+（可选，部分功能降级运行）

## 快速开始

```bash
# 1. 安装依赖
pip install -e .

# 2. 启动开发服务器（无需 .env，首次自动进入安装向导）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. 访问 http://localhost:8000 完成安装向导
#    - 创建管理员账号
#    - 选择数据库（默认 SQLite，可选 PostgreSQL）
#    - 确认安装 → 自动生成安全密钥、建表、跳转登录

# 4. 运行测试
pytest

# 5. 代码检查
ruff check .
```

> 首次启动无需 `.env` 文件，安装向导自动生成安全配置。完成后配置保存在 `.env`，后续启动直接进入控制台。

## 项目结构

```
backend/
├── app/
│   ├── main.py                  # FastAPI 应用入口 + 生命周期管理
│   ├── config.py                # 配置管理（开发默认值 + 生产校验）
│   ├── database.py              # 懒初始化 + SQLite 默认 + PostgreSQL 可选
│   ├── redis.py                 # Redis 连接池（asyncio.Lock 线程安全）
│   ├── seed_data.py             # 初始数据种子（6种策略模板含规则策略）
│   ├── api/                     # API 路由（40 端点）
│   │   ├── deps.py              # 依赖注入（get_current_user, get_db 等）
│   │   └── v1/
│   │       ├── auth.py          # 认证（登录/注册/刷新/me）
│   │       ├── strategies.py    # 策略模板/实例/规则校验
│   │       ├── orders.py        # 交易（下单/撤单/持仓/平仓/紧急平仓）
│   │       ├── market.py        # 行情（REST + WebSocket 3交易所）
│   │       ├── backtest.py      # 回测执行 & 历史
│   │       ├── asset.py         # 资产汇总/持仓/权益曲线
│   │       └── setup.py         # 安装向导
│   ├── core/                    # 核心模块（10个）
│   │   ├── strategy_engine.py   # 6种策略实现
│   │   ├── strategy_runner.py   # 实时运行器 + 自动交易
│   │   ├── rule_engine.py       # 自定义规则引擎
│   │   ├── indicators.py        # 14种技术指标计算
│   │   ├── exchange_adapter.py  # 三交易所适配器（~1150行）
│   │   ├── performance.py       # 绩效计算
│   │   ├── security.py          # JWT + AES-256(Fernet) 加密
│   │   ├── exceptions.py        # 统一异常
│   │   ├── schemas.py           # 通用 Schema
│   │   └── trade_schemas.py     # 交易 Schema
│   ├── models/                  # SQLAlchemy 模型（6个）
│   │   ├── user.py              # 用户（含 is_superuser）
│   │   ├── strategy.py          # 策略模板/实例/信号
│   │   ├── exchange.py          # 交易所账户（API Key AES-256 加密）
│   │   ├── order.py             # 订单 & 持仓
│   │   └── backtest.py          # 回测结果
│   ├── services/                # 业务逻辑层（6个）
│   │   ├── auth_service.py      # 认证
│   │   ├── strategy_service.py  # 策略
│   │   ├── order_service.py     # 交易 + 余额同步
│   │   ├── market_service.py    # 行情（httpx 单例复用）
│   │   ├── backtest_service.py  # 回测（真实K线 + 降级）
│   │   └── asset_service.py     # 资产
│   ├── repositories/            # 数据访问层
│   └── web/                     # 网页控制台
│       ├── routes.py            # 页面路由
│       └── static/              # index.html, setup.html, css/, js/（8个模块）
├── tests/                       # 测试（7个文件 / 40+ 用例）
└── pyproject.toml               # 项目依赖 & 配置
```

## API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- 健康检查: http://localhost:8000/health

## 环境变量

安装向导自动生成 `.env`，无需手动配置。如需自定义：

```env
# 应用
APP_NAME=CryptoQuant
DEBUG=false                          # 生产必须 false
SECRET_KEY=                          # 安装向导自动生成
JWT_SECRET_KEY=                      # 安装向导自动生成
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
PRODUCTION=true                      # 生产环境设为 true（校验密钥安全性）

# 数据库（默认 SQLite，无需配置）
DATABASE_URL=sqlite+aiosqlite:///./data/crypto_quant.db
# PostgreSQL: postgresql+asyncpg://user:password@localhost:5432/crypto_quant

# Redis（可选，缺失时部分功能降级）
REDIS_URL=redis://localhost:6379/0
```

> ⚠️ 生产环境设置 `PRODUCTION=true` 时，`validate_production_secrets()` 会拒绝默认密钥启动。

## 安全特性

- **生产密钥校验**：`PRODUCTION=true` 时拒绝默认/弱密钥
- **API Key 加密存储**：交易所 API Key/Secret/Passphrase 使用 AES-256 (Fernet)
- **JWT Token 类型校验**：Refresh Token 验证时校验 token_type
- **IDOR 防护**：所有资源操作校验 user_id 所有权
- **WS 连接认证**：WebSocket 端点需 JWT 认证 + 单用户最多 5 连接
- **数值范围校验**：金融数值字段使用 `Field(gt=0)`
- **CORS 加固**：明确限制 methods 和 headers
- **策略实例上限**：每用户最多 20 个
