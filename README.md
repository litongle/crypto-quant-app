# 📱 币钱袋 - 数字货币量化交易 App

> 面向普通加密货币投资者的量化交易 App

---

## 🎯 产品定位

**币钱袋** — 让不懂代码的普通投资者，也能通过简单配置使用量化交易策略。

**目标用户**：不想自己盯盘、希望用量化工具辅助决策的币圈散户。

---

## 🏗️ 项目状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 产品原型 | ✅ 完成 | 单 HTML 可交互原型，5 个完整页面 |
| 后端 API | ✅ 完成 | FastAPI 全量接口已实现（37 个 Python 文件） |
| 移动端框架 | ✅ 完成 | Flutter + Riverpod，核心页面已实现 |
| Dashboard 对接 | ✅ 完成 | 资产/行情/持仓/权益曲线已对接真实 API |
| 认证流程 | ✅ 完成 | 可选登录 + JWT + Token 刷新（未登录可浏览占位数据） |
| 安全审计 | ✅ 完成 | P0/P1/P2/P3 全部修复，27 项问题清零 |
| 策略引擎 | 🚧 进行中 | MA/RSI/Bollinger 框架已有，Martingale 待完成 |
| 交易所 WebSocket | 🚧 进行中 | Binance/OKX 框架已有，实时推送待完善 |
| 回测引擎 | 📋 待开发 | 框架搭建中 |
| 实盘下单 | 📋 待开发 | 涉及真实资金，需完整风控 |

---

## 📂 项目结构

```
crypto-quant-app/
├── prototype.html              ← 完整可交互原型（浏览器打开）
├── README.md                   ← 本文档
├── DECISIONS.md                ← 架构决策记录 (ADR)
├── 系统架构设计文档.md           ← 完整技术架构设计
├── 后端补充接口文档.md           ← 移动端配套 API 接口定义
├── Release前审查报告.md         ← 发布前审查报告
├── 项目进展报告.md              ← 产品/业务进展
├── agent-collaboration-plan.md ← 代理协同开发方案（早期规划）
│
├── backend/                    ← FastAPI 后端
│   ├── app/
│   │   ├── main.py            # 应用入口（结构化日志、CORS 加固）
│   │   ├── config.py          # 配置管理（无硬编码默认密钥）
│   │   ├── database.py        # PostgreSQL 异步连接
│   │   ├── redis.py           # Redis 连接池（asyncio.Lock 保护）
│   │   ├── api/v1/            # REST API 路由
│   │   ├── core/              # 安全模块（AES-256 加密、JWT）
│   │   ├── models/            # SQLAlchemy 模型
│   │   ├── schemas/           # Pydantic 模型
│   │   ├── services/          # 业务逻辑层
│   │   ├── repositories/      # 数据访问层
│   │   └── seed_data.py       # 初始数据
│   ├── .env.example           # 环境变量模板
│   └── pyproject.toml         # 项目依赖
│
├── mobile/                     ← Flutter 移动端
│   └── lib/
│       ├── core/              # 基础设施（API Client、常量、路由）
│       └── features/          # 功能模块
│           ├── auth/          # 登录注册
│           ├── dashboard/     # 首页 Dashboard
│           ├── strategy/      # 策略中心
│           ├── backtest/      # 回测页面
│           └── settings/      # 设置页面
│
└── docs/                       ← 项目文档
    ├── standards/             # 技术标准
    │   ├── CODE_REVIEW_PROCESS.md   # 代码审查标准与流程
    │   ├── CODE_STANDARDS.md        # 编码规范
    │   └── ARCHITECTURE_REVIEW.md   # 架构 Review 报告
    └── PM/                    # 项目管理
        ├── 项目计划.md         # Sprint 计划
        ├── PM规范手册.md       # PM 规范
        └── 风险登记册.md       # 风险跟踪
```

---

## 🛠️ 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 移动端 | Flutter (Dart) + Riverpod | 跨平台 iOS/Android |
| 后端 | Python FastAPI | 异步高性能，自动 OpenAPI 文档 |
| 数据库 | PostgreSQL + TimescaleDB | 业务数据 + 时序行情 |
| 缓存 | Redis | 会话/行情缓存/消息队列 |
| 安全 | AES-256 (Fernet) + JWT | API Key 加密存储、Token 认证 |
| 交易所 | Binance / OKX API | 行情 + 下单对接 |

---

## 🔑 核心用户流程

```
选择策略模板 → 调节参数（滑块） → 一键回测 → 查看绩效 → 激活策略
     ↓
收到信号 → 跟单确认 → 自动下单（止盈止损）
     ↓
持仓管理 → 调节止盈止损 → 卖出平仓
```

---

## 🚀 快速启动

### 后端

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate  # Windows
pip install -e ".[dev]"
cp .env.example .env  # 编辑 .env 填入实际配置
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 移动端

```bash
cd mobile
flutter pub get
flutter run
```

---

## 📊 安全审计（2026-04-21 完成）

全量代码审计发现 27 项问题，按四级优先级全部修复：

| 等级 | 修复项 | 关键变更 |
|------|--------|---------|
| P0 | 6 | 移除硬编码密钥、AES-256 加密、端点加认证、Token 类型校验、数值校验 |
| P1 | 18 | 修复模型字段不一致、去重代码、httpx 单例复用、Redis 锁、结构化日志 |
| P2 | 5 | Redis 行情缓存、提取常量、依赖注入规范化 |
| P3 | 1 | 更新 DECISIONS.md |

详见 `DECISIONS.md` → ADR-006

---

## 📋 当前 Sprint

**Sprint 3: 策略引擎完成 & 回测框架** (目标: 2026-05-04)

- ✅ T-3.1 数据模型完善
- ✅ T-3.2 Repository 层
- ✅ T-3.3 Service 层
- 🔄 T-3.4 交易所适配器 WebSocket
- 🔄 T-3.5 策略引擎核心
- 📋 T-3.6 马丁格尔策略
- 📋 T-3.7 回测框架
- 📋 T-3.8 绩效计算

---

## ⚠️ 关键风险

| 风险 | 等级 | 说明 |
|------|------|------|
| 实盘下单涉及真金白银 | 🔴 高 | 必须沙盒验证，完整风控 |
| 用户信任 App 代为下单 | 🔴 高 | 需透明化策略逻辑、风险提示 |
| 回测 vs 实盘差距 | 🟡 中 | 行业经典难题，需滑点/手续费模拟 |
| 零测试覆盖率 | 🟡 中 | 急需建立 pytest 测试框架 |

---

*最后更新：2026-04-21*
