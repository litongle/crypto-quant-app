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
├── docker-compose.yml          ← 后端 + PG + Redis 一键启动
├── README.md                   ← 本文档
├── CLAUDE.md                   ← Claude Code 项目级指令
├── DECISIONS.md                ← 架构决策记录（ADR-001~013）
├── DESIGN_SYSTEM.md            ← 设计系统 v3.1
├── DEVELOPMENT.md              ← 开发参考手册
├── deploy/
│   └── Caddyfile.example       ← VPS 反向代理模板（自动 HTTPS）
├── docs/
│   ├── DEPLOY-VPS.md           ← VPS 部署指南
│   └── superpowers/            ← 实施记录（specs + plans）
├── backend/
│   ├── Dockerfile              ← Python 3.12-slim
│   ├── alembic/                ← 数据库迁移（0001~0011）
│   ├── scripts/
│   │   └── generate_admin_hash.py  ← 交互生成 admin bcrypt 哈希
│   ├── app/
│   │   ├── main.py             # 应用入口 + lifespan + seed_admin
│   │   ├── config.py           # Settings（admin/db/cors/告警）
│   │   ├── database.py         # SQLAlchemy 异步引擎
│   │   ├── redis.py            # Redis 连接池
│   │   ├── api/v1/             # API 端点
│   │   │   ├── auth.py         # 单用户登录（login/refresh/me）
│   │   │   ├── strategies.py   # 策略模板/实例/规则校验
│   │   │   ├── orders.py       # 交易（下单/撤单/持仓/平仓/紧急平仓）
│   │   │   ├── market.py       # 行情（REST + WebSocket）
│   │   │   ├── backtest.py     # 回测执行 & 历史
│   │   │   ├── asset.py        # 资产汇总/持仓/权益曲线
│   │   │   └── events.py       # 事件流（信号 + 策略自停）
│   │   ├── core/               # 策略引擎、规则引擎、指标、交易所适配器
│   │   ├── models/             # SQLAlchemy 模型
│   │   ├── services/           # 业务逻辑层
│   │   ├── repositories/       # 数据访问层
│   │   └── web/
│   │       ├── routes.py
│   │       └── static/         # index.html + css + js（控制台 + 设置抽屉）
│   └── tests/
└── .claude/                    ← Claude Code 配置 + 钩子（git-guardrails）
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

## 当前能力

- **单用户认证**：admin 用户名 + bcrypt 密码哈希存 `.env`，启动种子（详见 [ADR-013](DECISIONS.md)）
- **策略引擎**：6 种内置策略（含 RSI 分层极值追踪）+ 规则引擎 + 自动交易
- **回测框架**：真实 K 线 + 滑点/手续费模拟 + 绩效报告 + 历史回看
- **交易所适配**：Binance / OKX / HTX（火币）三家 + 重试 + 限流
- **WebSocket 实时行情**：多交易所代理 + 重连
- **交易所账户管理**：AES-256 (Fernet) 加密存 API key
- **风控与自停**：连续失败/心跳超时自动暂停策略（详见 [ADR-013](DECISIONS.md)）
- **数据库迁移**：Alembic 0001~0011
- **网页控制台**：4 项侧栏（控制台 / 策略 / 回测 / 事件流）+ 设置抽屉 + PWA
- **测试**：pytest 600+ 用例，Docker 容器内 SQLite 内存数据库

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
| [docs/DEPLOY-VPS.md](docs/DEPLOY-VPS.md) | VPS 生产部署 —— Caddy + HTTPS + 防火墙 + 备份 |
| [DECISIONS.md](DECISIONS.md) | 架构决策记录（ADR-001~013）—— "为什么这样选" |
| [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) | 设计系统 v3.1 —— 色彩/字体/组件/动效规范 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发参考手册 —— 代码规范/Docker/架构/环境变量 |
| [CLAUDE.md](CLAUDE.md) | Claude Code 项目级指令（开发协作约定） |
| [docs/superpowers/](docs/superpowers/) | 设计 spec 与实施 plan 历史档案 |

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

| 服务 | 镜像 | 容器内端口 | 宿主映射 |
|------|------|------|------|
| 后端 | Python 3.12-slim（多阶段构建） | 8000 | 8001 |
| PostgreSQL | postgres:16-alpine | 5432 | 127.0.0.1:5432 |
| Redis | redis:7-alpine | 6379 | 127.0.0.1:6379 |

启动：`docker compose up -d --build`（项目根目录）

> 多阶段构建 + 国内镜像加速（阿里云 apt/pip 源）+ .dockerignore。详见 [DEVELOPMENT.md](DEVELOPMENT.md)。

---

## 安全特性

- **生产密钥校验**：`ENVIRONMENT=production` 时拒绝默认/空 `SECRET_KEY`/`JWT_SECRET_KEY`/`ADMIN_PASSWORD_HASH`
- **API Key 加密存储**：交易所 API Key/Secret/Passphrase 使用 AES-256 (Fernet)
- **bcrypt 密码哈希**：admin 密码以 bcrypt 哈希形式存 `.env`，明文从不入库
- **JWT 双 Token + 类型校验**：Access/Refresh 分离，Refresh 验证时校验 token_type
- **HTTPS 强制（生产）**：登录端点要求 `X-Forwarded-Proto: https`（反向代理传递）
- **WS 认证**：WebSocket 端点需 JWT + 单用户最多 5 连接
- **金融字段校验**：金额数值统一用 `Decimal` + Pydantic `Field(gt=0)`
- **策略自停**：连续失败/心跳超时触发自动暂停，避免「失控的策略」
