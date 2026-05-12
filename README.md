# 💎 币钱袋 (CryptoQuant) — 数字货币量化交易 App

> 面向加密货币投资者的量化交易平台 — 不写代码也能使用专业策略，支持实盘下单与风控管理。

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | PWA 网页控制台 — 原生 JS + CSS 变量设计系统 + Chart.js（响应式4断点） |
| 后端 | Python 3.12 + FastAPI（异步） |
| 数据库 | PostgreSQL（docker-compose 内置） |
| 缓存/队列 | Redis + Redis Streams |
| 安全 | AES-256 (Fernet) + JWT + 生产密钥校验 |
| 交易所 | Binance / OKX / HTX（火币）三交易所适配 |
| 量化引擎 | 6种策略（MA/RSI/Bollinger/Grid/Martingale/Rule）+ 实时运行器 + 自动交易 + 回测 + 绩效 |
| 设计系统 | v3.1 — Geist Sans 字体 + Indigo 主色 + 流体缩放 + 暗亮双主题 |
| 测试 | 7个测试文件 / 40+ 用例（auth/config/security/strategy/rule_engine） |

---

## 快速启动

### Docker 一键部署（本地开发）

```bash
git clone https://github.com/litongle/crypto-quant-app.git
cd crypto-quant-app

# 1. 准备 .env
cp backend/.env.example backend/.env
# 编辑 backend/.env，至少填好 ADMIN_USERNAME、SECRET_KEY、JWT_SECRET_KEY

# 2. 生成 ADMIN_PASSWORD_HASH（交互输入密码两次）
docker compose run --rm backend python -m scripts.generate_admin_hash
# 把输出的 ADMIN_PASSWORD_HASH=... 复制到 backend/.env

# 3. 启动
docker compose up -d --build
# 访问 http://localhost:8001/，用 .env 里的 ADMIN_USERNAME + 密码登录
```

### VPS 生产部署

详见 **[docs/DEPLOY-VPS.md](docs/DEPLOY-VPS.md)** — 含 Caddy 自动 HTTPS、防火墙、域名、备份、升级流程。

### 访问地址

| 入口 | 地址 |
|------|------|
| 网页控制台 | `http://localhost:8001/web/` |
| API 文档 | `http://localhost:8001/docs` |
| 健康检查 | `http://localhost:8001/health` |

---

## 项目结构

```
crypto-quant-app/
├── docker-compose.yml          ← 一键部署（后端+PG+Redis）
├── README.md                   ← 本文档
├── DECISIONS.md                ← 架构决策记录（ADR，12条）
├── DESIGN_SYSTEM.md            ← 统一设计系统 v3.1
├── DEVELOPMENT.md              ← 开发参考手册
├── docs/
│   └── 系统架构图.html         ← 可视化架构图
├── backend/                    ← FastAPI 后端
│   ├── Dockerfile              ← Python 3.12-slim（多阶段构建+镜像加速）
│   ├── app/
│   │   ├── main.py             # 应用入口 + 生命周期
│   │   ├── config.py           # 配置（开发默认值 + 生产校验）
│   │   ├── database.py         # 懒初始化 + SQLite 默认
│   │   ├── redis.py            # Redis 连接池（asyncio.Lock）
│   │   ├── api/v1/             # API 端点
│   │   │   ├── auth.py         # 单用户登录（login/refresh/me）
│   │   │   ├── strategies.py   # 策略模板/实例/规则校验
│   │   │   ├── orders.py       # 交易（下单/撤单/持仓/平仓/紧急平仓）
│   │   │   ├── market.py       # 行情（REST + WebSocket）
│   │   │   ├── backtest.py     # 回测执行 & 历史
│   │   │   ├── asset.py        # 资产汇总/持仓/权益曲线
│   │   │   └── events.py       # 事件流（信号 + 策略自停）
│   │   ├── core/               # 核心模块（10个）
│   │   │   ├── strategy_engine.py   # 6种策略实现
│   │   │   ├── strategy_runner.py   # 实时运行器 + 自动交易
│   │   │   ├── rule_engine.py       # 自定义规则引擎（14种指标+逻辑组合）
│   │   │   ├── indicators.py        # 技术指标计算
│   │   │   ├── exchange_adapter.py  # 三交易所适配器（~1150行）
│   │   │   ├── performance.py       # 绩效计算
│   │   │   ├── security.py          # JWT + AES-256 加密
│   │   │   ├── exceptions.py        # 统一异常
│   │   │   ├── schemas.py           # 通用 Schema
│   │   │   └── trade_schemas.py     # 交易 Schema
│   │   ├── models/             # SQLAlchemy 模型（6个）
│   │   ├── services/           # 业务逻辑层（6个）
│   │   ├── repositories/       # 数据访问层（4个）
│   │   └── web/                # 网页控制台（/web 入口）
│   │       ├── routes.py
│   │       └── static/         # index.html, css/, js/（控制台 + 设置抽屉）
│   └── tests/                  # 测试（7个文件 / 40+ 用例）
└── docs/
    └── 系统架构图.html         ← 可视化架构图
```

---

## 核心用户流程

```
选择策略模板 → 调节参数（滑块/规则构建器）→ 一键回测 → 查看绩效 → 激活策略
     ↓
收到信号 → 自动下单执行
     ↓
持仓管理 → 查看仓位与风险变化
```

---

## 项目状态

### 功能完成度

| 模块 | 状态 |
|------|------|
| 后端 API（40端点） | ✅ |
| 安全审计（P0~P3，27项 → 21已修复） | ✅ 核心清零 |
| 策略引擎（6种 + 规则引擎 + 自动交易） | ✅ |
| 回测框架（真实K线 + 绩效 + 历史） | ✅ |
| 交易所适配器（3交易所 + 重试 + 限流） | ✅ |
| WebSocket 实时行情 | ✅ |
| 交易所账户管理（CRUD + AES-256加密） | ✅ |
| 网页控制台（7页面 + 响应式4断点 + PWA） | ✅ |
| 设计系统 v3.1（流体缩放 + 双主题） | ✅ |
| 测试框架（40+ 用例） | ✅ |
| 数据库迁移（Alembic） | 📋 待完成 |

### API 对接矩阵

| 模块 | 前缀 | 端点数 | 网页端 |
|------|------|--------|--------|
| 认证 | /auth | 3 | ✅ |
| 策略 | /strategies | 10 | ✅ 7/10 |
| 回测 | /backtest | 3 | ✅ |
| 行情 | /market | 5 | ✅ 2/5 |
| 资产 | /asset | 3 | ✅ |
| 交易 | /trading | 10 | ✅ 9/10 |
| WebSocket | /ws | 3 | ✅ |

### 安全审计

| 审计轮次 | 发现 | 已修 | 关键未修项 |
|----------|------|------|-----------|
| 第一轮（2026-04-21） | 27项 | 27 | — |
| 现实检验（2026-04-26） | 27项 | 21 | Alembic迁移 / 订单模型优化 / 健康检查详情 / httpOnly cookie / 密码截断 |

### 发布阻塞项

| 优先级 | 问题 | 状态 |
|--------|------|------|
| 🔴 P0 | 策略信号 WS 前端订阅 | ❌ |
| 🟡 P1 | 数据库迁移（Alembic） | ❌ |
| 🟢 P2 | token httpOnly cookie | ❌ |

### 版本规划

| 版本 | 目标日期 | 主要内容 | 状态 |
|------|---------|---------|------|
| v0.3.0 | 2026-04-26 | 现实检验修复 + 规则引擎 + 前端P0修复 | ✅ |
| v0.4.0 | 2026-05-18 | 数据库迁移 + PWA 完善 | 📋 |
| v0.5.0 | 2026-06-01 | 风控完善 + 策略信号通知 | 📋 |
| v1.0.0 | 2026-06-30 | 生产发布 | 📋 |

---

## 关键风险

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| 实盘下单涉及真金白银 | 🔴 高 | 仓位上限控制 + 风险监控 + 审计记录 |
| 回测 vs 实盘差距 | 🟡 中 | 真实K线回测 + 滑点/手续费模拟 |
| 交易所 API 不稳定 | 🟡 中 | 重连机制 + 指数退避 + 多数据源冗余 |

---

## 文档索引

| 文档 | 说明 |
|------|------|
| [DECISIONS.md](DECISIONS.md) | 架构决策记录（ADR，12条）—— "为什么这样选" |
| [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) | 统一设计系统 v3.1 —— 色彩/字体/组件/动效规范 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发参考手册 —— 代码规范/Docker/架构/环境变量 |

---

## 环境变量

复制 `backend/.env.example` 为 `backend/.env`，按提示填写：

```env
# 应用
APP_NAME=CryptoQuant
DEBUG=false                          # 生产必须 false
ENVIRONMENT=production

# 安全密钥（用 `openssl rand -hex 32` 生成）
SECRET_KEY=
JWT_SECRET_KEY=

# 管理员账户（唯一登录账户）
ADMIN_USERNAME=admin@example.com
# 用 `docker compose run --rm backend python -m scripts.generate_admin_hash` 生成
ADMIN_PASSWORD_HASH=

# 数据库 / Redis（docker-compose 内置 PG + Redis，默认值通常无需改）
DATABASE_URL=postgresql+asyncpg://postgres:dev-postgres-password@postgres:5432/crypto_quant
REDIS_URL=redis://:dev-redis-password@redis:6379/0
```

> ⚠️ 生产环境（`ENVIRONMENT=production`）时，`validate_production_secrets()` 会拒绝默认/空密钥启动。

---

## Docker 环境

| 服务 | 镜像 | 端口 |
|------|------|------|
| 后端 | Python 3.12-slim（多阶段构建） | 8000 |
| PostgreSQL | postgres:16-alpine | 5432 |
| Redis | redis:7-alpine | 6379 |

启动：`docker compose up --build`（项目根目录）

> Docker 构建已优化：多阶段构建 + 国内镜像加速（阿里云 apt/pip 源）+ .dockerignore 排除，镜像从 718MB 降至 ~250MB。详见 [DEVELOPMENT.md](DEVELOPMENT.md)。

---

## 安全特性

- **生产密钥校验**：`PRODUCTION=true` 时拒绝默认/弱密钥
- **API Key 加密存储**：交易所 API Key/Secret/Passphrase 使用 AES-256 (Fernet)
- **JWT Token 类型校验**：Refresh Token 验证时校验 token_type
- **IDOR 防护**：所有资源操作校验 user_id 所有权
- **WS 连接认证**：WebSocket 端点需 JWT 认证 + 单用户最多 5 连接
- **数值范围校验**：金融数值字段使用 `Field(gt=0)`
- **策略实例上限**：每用户最多 20 个
