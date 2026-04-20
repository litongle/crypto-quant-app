# 📱 币钱袋 - 数字货币量化交易 App

> 面向普通加密货币投资者的量化交易 App

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Flutter](https://img.shields.io/badge/Flutter-3.16+-25B8F8.svg)](https://flutter.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 🎯 产品定位

**币钱袋** — 让不懂代码的普通投资者，也能通过简单配置使用量化交易策略。

**目标用户**：不想自己盯盘、希望用量化工具辅助决策的币圈散户。

---

## 🏗️ 项目状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 产品原型 | ✅ 完成 | 单 HTML 可交互原型，5 个完整页面 |
| 后端 API | ✅ 完成 | FastAPI 全量接口已实现（37 个 Python 文件，34 个端点） |
| 移动端框架 | ✅ 完成 | Flutter + Riverpod，35 个 Dart 文件，5 个功能模块 |
| Dashboard 对接 | ✅ 完成 | 资产/行情/持仓/权益曲线已对接真实 API |
| 认证流程 | ✅ 完成 | 可选登录 + JWT + Token 刷新（未登录可浏览占位数据） |
| 安全审计 | ✅ 完成 | P0/P1/P2/P3 全部修复，27 项问题清零 |
| Gradle 构建优化 | ✅ 完成 | 缓存+并行+Daemon+阿里云镜像，configuration-cache=false |
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
│       ├── core/              # 基础设施（API Client、常量、路由、主题）
│       └── features/          # 功能模块
│           ├── auth/          # 登录注册（可选登录）
│           ├── dashboard/     # 首页 Dashboard（资产/行情/持仓/权益曲线）
│           ├── strategies/    # 策略中心（模板/实例/参数配置）
│           ├── backtest/      # 回测页面（历史/绩效/收益曲线）
│           └── settings/      # 设置页面（用户/交易所/风控）
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
| 构建 | Gradle + Aliyun Maven | 缓存/并行/Daemon 加速 |

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

### 前置要求

| 组件 | 版本要求 | 说明 |
|------|----------|------|
| Python | 3.11+ | 后端运行环境 |
| Flutter | 3.16+ | 移动端开发框架 |
| PostgreSQL | 15+ | 主数据库 |
| Redis | 7+ | 缓存和消息队列 |

### 1. 克隆项目

```bash
git clone https://github.com/litongle/crypto-quant-app.git
cd crypto-quant-app
```

### 2. 后端安装

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -e ".[dev]"

# 配置环境变量（必填！无默认值）
cp .env.example .env
# 编辑 .env 填入以下必填项：
#   - SECRET_KEY
#   - DATABASE_URL
#   - JWT_SECRET_KEY

# 数据库迁移
alembic upgrade head

# 初始化种子数据（可选）
python -m app.seed_data

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> ⚠️ **重要**：`SECRET_KEY`、`DATABASE_URL`、`JWT_SECRET_KEY` 必须配置，否则服务无法启动。

### 3. 移动端安装

```bash
cd mobile

# 安装依赖
flutter pub get

# 启动开发服务器
flutter run

# 构建 Debug APK
flutter build apk --debug

# 构建 Release APK
flutter build apk --release
```

> 💡 **提示**：App 采用可选登录设计，无需后端即可浏览占位数据。首次启动会展示示例资产和行情。

---

## 📖 使用示例

### API 认证

```bash
# 注册用户
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"securepassword","username":"trader"}'

# 登录获取 Token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"securepassword"}'

# 响应示例
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### 获取行情数据

```bash
# 获取 K 线数据
curl -X GET "http://localhost:8000/api/v1/market/kline?symbol=BTCUSDT&interval=1h&limit=100" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 获取账户资产
curl -X GET "http://localhost:8000/api/v1/asset/balance" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 策略管理

```bash
# 获取策略模板列表
curl -X GET "http://localhost:8000/api/v1/strategies/templates" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 创建策略实例
curl -X POST "http://localhost:8000/api/v1/strategies/instances" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": 1,
    "name": "我的 BTC 策略",
    "symbol": "BTCUSDT",
    "params": {
      "ma_period": 20,
      "rsi_period": 14,
      "rsi_overbought": 70,
      "rsi_oversold": 30
    }
  }'

# 运行回测
curl -X POST "http://localhost:8000/api/v1/backtest/run" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_instance_id": 1,
    "symbol": "BTCUSDT",
    "start_date": "2024-01-01",
    "end_date": "2024-03-01",
    "initial_capital": 100000
  }'
```

### API 文档

启动服务后访问：
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

---

## 🧪 测试

### 后端测试

```bash
cd backend

# 运行所有测试
pytest

# 运行测试并查看覆盖率
pytest --cov=app --cov-report=html

# 运行特定测试文件
pytest tests/test_auth.py -v

# 运行带标记的测试
pytest -m "not slow"
```

### 移动端测试

```bash
cd mobile

# 运行所有测试
flutter test

# 运行特定测试文件
flutter test test/dashboard_test.dart

# 生成覆盖率报告
flutter test --coverage
```

---

## 🔧 开发指南

### 代码规范

#### Python (后端)

```bash
cd backend

# 代码检查
ruff check .

# 自动修复
ruff check --fix .

# 类型检查
mypy app/

# 格式化
ruff format .
```

#### Dart (移动端)

```bash
cd mobile

# 代码检查
flutter analyze

# 格式化
dart format lib/

# 生成代码（freezed/json_serializable）
dart run build_runner build
```

### Git 提交规范

项目采用**约定式提交**（Conventional Commits）：

```
<type>(<scope>): <subject>

# 示例
feat(auth): 添加 refresh token 刷新机制
fix(strategy): 修复 MA 策略计算错误
docs(readme): 完善安装步骤
refactor(core): 重构交易所适配器
test(backtest): 添加回测服务单元测试
```

**Type 类型**：
- `feat`: 新功能
- `fix`: 错误修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具相关

---

## 🤝 贡献指南

### 如何贡献

1. **Fork 本仓库**
2. **创建特性分支**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **提交更改**
   ```bash
   git commit -m "feat(scope): 添加新功能"
   ```
4. **推送分支**
   ```bash
   git push origin feature/your-feature-name
   ```
5. **创建 Pull Request**

### Pull Request 规范

- PR 标题使用约定式提交格式
- 描述清楚解决的问题或添加的功能
- 关联相关 Issue（使用 `Fixes #123`）
- 确保所有 CI 检查通过
- 添加必要的测试和文档

### 代码审查标准

详见 [docs/standards/CODE_REVIEW_PROCESS.md](docs/standards/CODE_REVIEW_PROCESS.md)

### 开发环境要求

- IDE: VS Code / PyCharm / Android Studio
- Python: 3.11+
- Flutter: 3.16+
- Node.js: 18+ (用于前端工具链)

### 本地环境设置

```bash
# 克隆后安装 pre-commit hooks
cd backend
pre-commit install

cd ../mobile
# Flutter 相关 hooks 已在 pubspec.yaml 中配置
```

---

## 📊 安全特性（2026-04-21 完成）

全量代码审计发现 27 项问题，按四级优先级全部修复：

| 等级 | 修复项 | 关键变更 |
|------|--------|---------|
| P0 | 6 | 移除硬编码密钥、AES-256 加密、端点加认证、Token 类型校验、数值校验 |
| P1 | 18 | 修复模型字段不一致、去重代码、httpx 单例复用、Redis 锁、结构化日志 |
| P2 | 5 | Redis 行情缓存、提取常量、依赖注入规范化 |
| P3 | 1 | 更新 DECISIONS.md |

详见 `DECISIONS.md` → ADR-006

---

## ⚠️ 关键风险

| 风险 | 等级 | 说明 |
|------|------|------|
| 实盘下单涉及真金白银 | 🔴 高 | 必须沙盒验证，完整风控 |
| 用户信任 App 代为下单 | 🔴 高 | 需透明化策略逻辑、风险提示 |
| 回测 vs 实盘差距 | 🟡 中 | 行业经典难题，需滑点/手续费模拟 |
| 零测试覆盖率 | 🟡 中 | 急需建立 pytest 测试框架 |
| App 调试包体积大 | 🟢 低 | Debug APK ~1.35GB 正常，Release 约 30-80MB |

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

## 📚 相关文档

| 文档 | 说明 |
|------|------|
| [系统架构设计文档.md](系统架构设计文档.md) | 完整技术架构设计 |
| [后端补充接口文档.md](后端补充接口文档.md) | 移动端配套 API 定义 |
| [DECISIONS.md](DECISIONS.md) | 架构决策记录 |
| [Release前审查报告.md](Release前审查报告.md) | 发布前审查报告 |
| [docs/standards/](docs/standards/) | 技术标准和代码规范 |
| [docs/PM/](docs/PM/) | 项目管理文档 |

---

## 🆘 获取帮助

- **问题反馈**: [GitHub Issues](https://github.com/litongle/crypto-quant-app/issues)
- **功能请求**: [GitHub Discussions](https://github.com/litongle/crypto-quant-app/discussions)
- **API 文档**: 启动后端后访问 `/docs`

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

感谢所有为币钱袋项目做出贡献的开发者！

---

*最后更新：2026-04-21（可选登录改造 + Gradle优化 + 文档全面同步）*
