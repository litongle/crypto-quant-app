# Alpha-7 — 数字货币量化交易平台

面向加密货币投资者的自托管量化交易平台。不写代码即可配置策略、跑回测、自动下单与风控管理。

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.12 + FastAPI（异步） |
| 数据库 | PostgreSQL 16 |
| 缓存 / 流 | Redis 7（含 Streams） |
| 前端 | PWA 控制台 — 原生 JS + CSS 变量设计系统 + LightweightCharts |
| 交易所 | Binance / OKX / HTX 三家适配（REST + WebSocket） |
| 量化引擎 | 8 种内置策略（含 RSI 分层极值追踪 / DCA / 自定义规则） + 回测 + 实盘运行器 |
| 安全 | bcrypt 单用户登录 + JWT 双 Token + Fernet (AES-256) 加密交易所密钥 |

## 快速启动

```bash
git clone https://github.com/litongle/crypto-quant-app.git
cd crypto-quant-app

# 一键装机（交互问 3 个问题：管理员邮箱 / 密码 / 域名）
./setup.sh

# 启动
docker compose up -d --build
```

打开 `http://localhost:8000/web/`，用刚才设的邮箱 + 密码登录。

交易所 API key、Telegram、SMTP、风控阈值等**运行时配置**登录后在「设置」抽屉里填，保存即时生效，无需重启。

VPS 生产部署见 [docs/DEPLOY-VPS.md](docs/DEPLOY-VPS.md)（含 Caddy 自动 HTTPS、防火墙、备份、升级流程）。

### 访问地址

| 入口 | 地址 |
|------|------|
| 网页控制台 | `http://localhost:8000/web/` |
| API 文档（Swagger UI） | `http://localhost:8000/docs` |
| 健康检查 | `http://localhost:8000/health` |

## 项目结构

```
crypto-quant-app/
├── docker-compose.yml          后端 + PostgreSQL + Redis 一键启动
├── setup.sh                    首次装机脚本
├── deploy/
│   └── Caddyfile.example       VPS 反向代理模板（自动 HTTPS）
├── docs/
│   └── DEPLOY-VPS.md           VPS 部署指南
└── backend/
    ├── Dockerfile              Python 3.12-slim
    ├── alembic/                数据库迁移
    └── app/
        ├── main.py             应用入口 + lifespan + seed_admin
        ├── config.py           Settings（admin / db / cors）
        ├── api/v1/             REST API
        │   ├── auth.py         单用户登录（login / refresh / me）
        │   ├── strategies.py   策略模板 / 实例 / 规则校验
        │   ├── trading.py      下单 / 撤单 / 持仓 / 平仓
        │   ├── market.py       行情（REST + WebSocket 代理）
        │   ├── backtest.py     回测执行与历史
        │   ├── asset.py        资产汇总 / 权益曲线
        │   └── events.py       事件流（信号 / 自停 / 风险）
        ├── core/               策略引擎、规则引擎、指标、交易所适配器
        ├── models/             SQLAlchemy 模型
        ├── services/           业务逻辑层
        ├── repositories/       数据访问层
        ├── web/                网页控制台（routes.py + static/）
        └── tests/              pytest 测试套件
```

## 核心能力

- **单用户认证** — admin 用户名 + bcrypt 密码哈希存 `.env`，启动种子，避免数据库泄漏明文。
- **策略引擎** — 8 个内置模板（双均线 / RSI / 布林带 / 网格 / 马丁格尔 / 自定义规则 / RSI 分层极值追踪 / DCA），含规则构建器，所有策略实盘运行。
- **回测框架** — 真实 K 线 + 滑点 / 手续费模拟 + 绩效报告 + 历史回看。
- **交易所适配** — Binance / OKX / HTX 三家 REST + WebSocket，含重连、限流、指数退避。
- **加密存储** — 交易所 API key / secret / passphrase 全部 Fernet (AES-256) 加密入库，密钥派生自 `JWT_SECRET_KEY`。
- **风控与自停** — 连续失败 / 心跳超时自动暂停策略；自停事件入 audit_events，保留可追溯历史。
- **网页控制台** — 控制台 / 策略 / 回测 / 日志 4 个 SPA 页 + 设置抽屉，PWA 离线兜底。
- **可观测性** — 信号 / 订单 / 自停 / 风险告警 / 用户操作 / 系统事件统一入 events 流，支持搜索 / 筛选 / 分页。

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/DEPLOY-VPS.md](docs/DEPLOY-VPS.md) | VPS 生产部署（Caddy + HTTPS + 防火墙 + 备份） |
| [DECISIONS.md](DECISIONS.md) | 架构决策记录（ADR）— 解释关键设计的"为什么" |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发参考（代码规范、Docker、架构、环境变量） |
| [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) | 前端设计系统（色彩 / 字体 / 组件 / 动效规范） |

## 环境变量

推荐用 `./setup.sh` 自动生成 `.env`。手工模式下只有 6 个引导级配置必须写在 `.env`（应用启动前就要用，无法挪到前端）：

```env
ADMIN_USERNAME=admin@example.com    # 登录邮箱
ADMIN_PASSWORD_HASH=                # bcrypt 哈希（setup.sh 自动生成）
SECRET_KEY=                         # openssl rand -hex 32
JWT_SECRET_KEY=                     # openssl rand -hex 32
DATABASE_URL=postgresql+asyncpg://postgres:dev-postgres-password@postgres:5432/crypto_quant
REDIS_URL=redis://:dev-redis-password@redis:6379/0
```

其他运行时配置（Telegram / SMTP / 风控阈值 / 交易所账户）登录后在前端「设置」抽屉里填，存数据库，敏感字段以 Fernet 密文加密。

生产环境（`ENVIRONMENT=production`）启动时会校验密钥强度，拒绝默认 / 空密钥。**改 `JWT_SECRET_KEY` 会让已加密的 Telegram token / SMTP 密码失效**，需在前端重新填。

## Docker 环境

| 服务 | 镜像 | 容器内端口 | 宿主映射 |
|------|------|------|------|
| 后端 | Python 3.12-slim（多阶段构建） | 8000 | 0.0.0.0:8000 |
| PostgreSQL | postgres:16-alpine | 5432 | 127.0.0.1:5432 |
| Redis | redis:7-alpine | 6379 | 127.0.0.1:6379 |

数据库和 Redis 默认只绑 `127.0.0.1`，不对外暴露；只有后端 8000 端口对外。VPS 部署时由 Caddy 反代到 HTTPS。

## 安全特性

- bcrypt 密码哈希，明文不入库；JWT 双 Token（Access / Refresh）+ 类型校验。
- 交易所 API Key / Secret / Passphrase 全部 Fernet (AES-256) 加密入库。
- 金额字段统一 `Decimal`，禁止 float；Pydantic `Field(gt=0)` 在 API 边界拦截非法值。
- 生产环境拒绝默认密钥启动；登录端点要求 `X-Forwarded-Proto: https`。
- WebSocket 端点需 JWT，单用户最多 5 连接，避免被异常客户端打爆。
- 策略自停 + 审计事件，避免"失控的策略"持续亏损。

## 许可证

MIT
