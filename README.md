# 💎 币钱袋 - 数字货币量化交易 App

> 面向普通加密货币投资者的量化交易 App — 让不懂代码的散户也能使用量化策略。

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Flutter](https://img.shields.io/badge/Flutter-3.16+-25B8F8.svg)](https://flutter.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)

---

## 🏗️ 技术栈

| 层级 | 技术 |
|------|------|
| 移动端 | Flutter + Riverpod + GoRouter |
| 网页控制台 | 原生 JS + Tailwind CSS + Chart.js（响应式4断点） |
| 后端 | Python FastAPI（异步） |
| 数据库 | PostgreSQL + TimescaleDB（默认 SQLite 零配置启动） |
| 缓存/队列 | Redis + Redis Streams |
| 安全 | AES-256 (Fernet) + JWT |
| 交易所 | Binance / OKX / HTX（火币） |
| 量化引擎 | 5种策略（MA/RSI/Bollinger/Grid/Martingale）+ 实时运行器 + 回测 + 绩效 |
| 构建 | Docker Compose + Gradle + 阿里云镜像 |

---

## 📂 项目结构

```
crypto-quant-app/
├── docker-compose.yml      ← 一键部署（后端+PG+Redis）
├── prototype.html          ← 可交互原型（浏览器打开）
├── README.md               ← 本文档
├── DECISIONS.md            ← 架构决策记录 (ADR)
├── PROGRESS.md             ← 项目进展 & 发布审查
├── docs/
│   ├── PM.md               ← 项目管理规范（合并版）
│   ├── STANDARDS.md        ← 代码规范 & 审查标准（合并版）
│   ├── 系统架构设计文档_v2.md  ← 长期演进目标
│   └── 系统架构图.html      ← 可视化架构图
├── backend/                ← FastAPI 后端
│   ├── Dockerfile          ← Python 3.12-slim
│   ├── app/
│   │   ├── main.py / config.py / database.py / redis.py
│   │   ├── api/v1/         # auth, users, strategies, market, asset, orders, backtest, setup, ws_market
│   │   ├── core/           # security, exchange_adapter, strategy_engine, strategy_runner, performance, exceptions
│   │   ├── models/         # user, strategy, exchange, order, backtest
│   │   ├── repositories/   # base, user_repo, strategy_repo, trading_repo
│   │   ├── services/       # auth, strategy, market, order, asset, backtest
│   │   └── web/            # 网页控制台（/web 入口）
│   │       ├── routes.py
│   │       └── static/     # index.html, setup.html, css/, js/
│   ├── .env.example
│   └── pyproject.toml
└── mobile/                 ← Flutter 移动端
    └── lib/
        ├── core/           # constants, network, providers, router, services, theme
        └── features/       # auth, dashboard, strategies, backtest, settings
```

---

## 🚀 项目状态

| 模块 | 状态 |
|------|------|
| 产品原型（5页） | ✅ 完成 |
| 后端 API（35端点） | ✅ 完成 |
| 安全审计（P0~P3，27项） | ✅ 全部修复 |
| Flutter 框架（5模块） | ✅ 完成 |
| Dashboard API 对接 | ✅ 完成 |
| 可选登录 + 占位数据 | ✅ 完成 |
| Gradle 构建优化 | ✅ 完成 |
| 网页控制台 + 安装向导 | ✅ 完成 |
| 接口契约对齐（3项修复） | ✅ 完成 |
| 策略引擎（MA/RSI/Bollinger/Grid/Martingale） | ✅ 完成 |
| 实时策略运行器 | ✅ 完成 |
| 绩效计算模块 | ✅ 完成 |
| 回测框架（真实K线+绩效+历史存储） | ✅ 完成 |
| 交易所适配器（3交易所+重试+限流+安全Decimal） | ✅ 完成 |
| WebSocket 实时行情 | ✅ 完成 |
| 交易所账户管理（CRUD + AES-256加密） | ✅ 完成 |
| 响应式网页适配（4断点：桌面/平板/手机） | ✅ 完成 |
| Docker 一键部署 | ✅ 完成 |
| 实盘下单 | 📋 待开发 |
| 测试覆盖 | 📋 待建立 |

**当前 Sprint 3**：✅ **100% 完成**（8/8）

---

## 🚀 快速启动

### Docker 一键部署（推荐）

```bash
# 克隆仓库
git clone https://github.com/litongle/crypto-quant-app.git
cd crypto-quant-app

# 启动所有服务（后端 + PostgreSQL + Redis）
docker compose up --build

# 访问 http://localhost:8000 首次进入安装向导
```

### 后端（零配置启动）

```bash
cd backend
pip install -e .                                         # 安装依赖
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000  # 启动
```

首次启动无需 `.env` 文件，访问 `http://localhost:8000/` 自动进入安装向导：

1. 创建管理员账号
2. 选择数据库（默认 SQLite 开箱即用，可选 PostgreSQL）
3. 确认安装 → 自动生成安全密钥、建表、跳转登录

> 安装完成后配置保存在 `.env`，后续启动直接进入控制台。

### 移动端

```bash
cd mobile
flutter pub get
flutter run                 # 无需后端，未登录时展示占位数据
```

### 访问地址

| 入口 | 地址 |
|------|------|
| 安装向导 | `http://localhost:8000/web/setup`（首次自动跳转） |
| 网页控制台 | `http://localhost:8000/web/` |
| API 文档 | `http://localhost:8000/docs` |
| 健康检查 | `http://localhost:8000/health` |

---

## 🔑 核心用户流程

```
选择策略模板 → 调节参数（滑块）→ 一键回测 → 查看绩效 → 激活策略
     ↓
收到信号 → 跟单确认 → 自动下单（止盈止损）
     ↓
持仓管理 → 调节止盈止损 → 卖出平仓
```

---

## ⚠️ 关键风险

| 风险 | 等级 |
|------|------|
| 实盘下单涉及真金白银 | 🔴 高 |
| 用户信任 App 代为下单 | 🔴 高 |
| 回测 vs 实盘差距 | 🟡 中 |
| 零测试覆盖率 | 🟡 中 |

---

## 📚 文档索引

| 文档 | 说明 |
|------|------|
| [DECISIONS.md](DECISIONS.md) | 架构决策记录（ADR，9条） |
| [PROGRESS.md](PROGRESS.md) | 项目进展 & 发布审查 |
| [docs/PM.md](docs/PM.md) | 项目管理规范 |
| [docs/STANDARDS.md](docs/STANDARDS.md) | 代码规范 & 审查标准 |
| [prototype.html](prototype.html) | 可交互原型 |
