# 币钱袋 — 开发参考手册

> 面向开发者的速查手册：代码规范、Docker 部署、架构参考、环境配置。

---

## 1. 代码规范

### 问题严重等级

| 等级 | 定义 | 处理方式 |
|------|------|---------|
| **P0** 🔴 | 安全漏洞、资金风险、数据损坏 | 必须立即修复 |
| **P1** 🟠 | 功能错误、接口不一致 | 必须修复 |
| **P2** 🟡 | 架构不合理、性能隐患 | 创建 Issue 跟进 |
| **P3** 🔵 | 风格优化、命名改善 | 建议改进 |

### Python 后端

**命名**：模块 `snake_case` | 类 `PascalCase` | 函数/变量 `snake_case` | 常量 `UPPER_SNAKE`

**金融计算（强制）**：

```python
from decimal import Decimal

# ❌ 禁止
price = 0.1 * 100  # 精度丢失

# ✅ 必须
def calculate_pnl(price: Decimal, quantity: Decimal) -> Decimal:
    return price * quantity
```

**日志**：使用 `logging`，禁止 `print()`

```python
import logging
logger = logging.getLogger(__name__)
logger.info("user_created", extra={"user_id": user_id, "action": "register"})
```

**FastAPI 端点模板**：

```python
@router.get("/endpoint", response_model=ResponseModel)
async def endpoint_name(
    current_user: CurrentUser,          # 认证依赖
    session: DbSession,                  # 数据库依赖
    param: str = Query(...),
) -> ResponseModel:
    """端点说明"""
    service = SomeService(session)
    return await service.do_something(current_user.id, param)
```

**关键检查项**：

| 检查项 | 等级 |
|--------|------|
| 无硬编码密钥/凭证 | P0 |
| 金融计算使用 Decimal，禁止 float | P0 |
| API Key 加密存储（AES-256 Fernet） | P0 |
| 所有业务端点有认证 | P0 |
| 安全 Decimal：`_safe_decimal()` / `_safe_divide()` | P0 |
| 模型字段与 Service 层访问一致 | P1 |
| httpx.AsyncClient 单例复用 | P1 |
| Redis 连接池全局初始化需加锁 | P1 |
| 回测禁止用随机数伪造指标 | P1 |
| 禁止模块级缓存 settings | P1 |
| 使用 logging，禁止 print() | P1 |
| 分层正确：API → Service → Repository → Model | P1 |

### Dart/Flutter

**命名**：文件 `snake_case` | 类 `PascalCase` | 私有 `_camelCase` | 常量 `kCamelCase`

**Provider 模板**：

```dart
final strategyProvider = FutureProvider<List<StrategyTemplate>>((ref) async {
  final service = ref.watch(strategyServiceProvider);
  return service.getTemplates();
});
```

### Git 提交规范

```
<type>(<scope>): <subject>

feat     新功能 | fix      Bug 修复 | docs     文档更新
refactor 重构   | test     测试相关 | chore    构建/工具

# 示例
feat(auth): 添加 refresh token 刷新机制
fix(strategy): 修复 MA 策略计算错误
```

---

## 2. Docker 部署

### 构建优化（已实施）

当前 Dockerfile 使用**多阶段构建 + 国内镜像加速**：

```dockerfile
# Stage 1: Builder — 编译依赖
FROM python:3.12-slim AS builder
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev
COPY pyproject.toml .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -e .

# Stage 2: Runtime — 最小化运行时
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl
COPY --from=builder /install /usr/local
```

**优化效果**：

| 指标 | 优化前 | 优化后 | 改进 |
|------|-------|--------|------|
| 最终镜像大小 | 718 MB | ~250 MB | 65% ↓ |
| 首次构建时间 | 7-10 min | 2-3 min | 70% ↓ |
| 代码变更重建 | 5-7 min | 10-30 sec | 90% ↓ |

### 基础镜像选择

| 镜像 | 大小 | 推荐度 | 说明 |
|------|------|--------|------|
| `python:3.12-slim` | 126 MB | ✅ 推荐 | 当前使用，编译稳定，apt 镜像多 |
| `python:3.12-alpine` | 50 MB | ❌ 不推荐 | numpy/asyncpg 编译困难，得不偿失 |
| `python:3.12-bookworm` | 311 MB | ❌ 过大 | 仅限开发调试 |

> **结论**：保持 `python:3.12-slim`，不要切换 Alpine。项目依赖 numpy/asyncpg/bcrypt 需要编译支持，Alpine 的 musl libc 不兼容。

### 国内镜像加速

**Dockerfile 已配置**（apt 阿里云 + pip 阿里云）。

**Docker Desktop 本地配置**（可选，双层加速）：

Settings → Docker Engine → `daemon.json`：

```json
{
  "registry-mirrors": [
    "https://docker.nju.edu.cn",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
```

**pip 本地加速**（`%APPDATA%\pip\pip.ini`）：

```ini
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
```

### 构建故障排除

| 问题 | 原因 | 解决 |
|------|------|------|
| pip install 超时 | 网络波动 | `--retries 5 --default-timeout 100` |
| 某些包找不到 | 镜像源同步延迟 | `--extra-index-url https://pypi.org/simple/` |
| apt 更新慢 | 未配置镜像源 | 确认 Dockerfile 中 sed 替换生效 |

---

## 3. 架构参考

### 系统架构概览

```
┌──────────────────────────────────────────────────────────┐
│                    客户端层                                │
│  Flutter App (Riverpod)  │  Web Console (JS + Chart.js) │
└──────────────┬───────────────────────┬───────────────────┘
               │  HTTPS / JSON / WS    │
               ▼                       ▼
┌──────────────────────────────────────────────────────────┐
│                  API 网关层 (FastAPI)                      │
│  /auth  /strategies  /backtest  /market  /asset  /trading │
└───────┬──────────┬───────────┬──────────┬────────────────┘
        │          │           │          │
┌───────┴──────────┴───────────┴──────────┴────────────────┐
│                  Service 服务层                            │
│  Auth │ Strategy │ Backtest │ Market │ Order │ Asset      │
└───────┬──────────┬───────────┬──────────┬────────────────┘
        │          │           │          │
┌───────┴──────────┴───────────┴──────────┴────────────────┐
│                  基础设施层                                │
│  PostgreSQL (SQLAlchemy) │ Redis (连接池) │ Exchange Adapter│
│                          │               │ (Binance/OKX/HTX)│
└──────────────────────────────────────────────────────────┘
```

### 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| 策略引擎 | `strategy_engine.py` | 6种策略实现（MA/RSI/Bollinger/Grid/Martingale/Rule） |
| 规则引擎 | `rule_engine.py` + `indicators.py` | 14种指标 + AND/OR 逻辑 + 交叉检测 |
| 策略运行器 | `strategy_runner.py` | asyncio.Task 管理 + 60s 防抖 + 自动交易 + WS 推送 |
| 交易所适配器 | `exchange_adapter.py` | Binance/OKX/HTX 三交易所，~1150行 |
| 绩效计算 | `performance.py` | 收益/夏普/回撤/胜率/盈亏比 |
| 安全模块 | `security.py` | JWT + AES-256 (Fernet) API Key 加密 |

### 数据模型关系

```
User 1:N → ExchangeAccount 1:N → Order
User 1:N → StrategyInstance N:1 → StrategyTemplate
StrategyInstance 1:N → Signal
ExchangeAccount 1:N → Position
```

### 交易所适配器特性

| 特性 | 说明 |
|------|------|
| 异常体系 | RateLimitError / NetworkError / OrderRejectedError |
| 重试+限流 | 指数退避 1→2→4s，下单不重试，查询3次 |
| 安全 Decimal | `_safe_decimal()` / `_safe_divide()` 防数值异常 |
| OKX 特殊处理 | Passphrase 空值警告 + 服务器时间同步 |
| Huobi 缓存 | accountId TTL 5分钟 + 失败清理 |
| 止损止盈 | `create_stop_order()` 三家实现 + 降级机制 |

### 策略执行流程

```
StrategyRunner.start() → asyncio.Task 循环:
  → MarketService.get_klines() 获取K线
  → Strategy.analyze(klines) 生成 Signal
  → _persist_signal() 信号入库
  → _auto_trade() 自动下单（查账户→create_order→submit_order）
  → _broadcast_signal() WS 推送信号
  → 60s 防抖等待
```

### WebSocket 行情

- 端点：`/ws/market`，支持 JWT 认证（query params `token=`）
- 单用户最多 5 连接
- 三交易所 WS 代理：BinanceWSProxy / OKXWSProxy / HuobiWSProxy
- 轮询降级：websockets 库未安装时自动降级
- 初始推送：连接后立即通过 REST 获取 ticker 并推送
- 消息格式：`{type, data: {price,...}, symbol}`，前端从 `msg.data` 读取

---

## 4. 需求优先级

| 等级 | 定义 | 处理时限 |
|------|------|---------|
| P0 🔴 | 阻塞核心流程 | 24小时内 |
| P1 🟠 | 本迭代必须完成 | 1个迭代周期 |
| P2 🟡 | 计划内完成 | 2个迭代周期 |
| P3 🟢 | 后续迭代 | 无时限 |

---

## 5. 技术债务

| 优先级 | 问题 | 状态 |
|--------|------|------|
| ~~🔴 P0~~ | ~~零测试覆盖率~~ | ✅ 40+ 用例 |
| ~~🔴 P0~~ | ~~生产环境默认密钥~~ | ✅ validate_production_secrets() |
| ~~🟠 P1~~ | ~~自动下单未实现~~ | ✅ StrategyRunner→OrderService |
| ~~🟠 P1~~ | ~~止损止盈只存数据库~~ | ✅ create_stop_order() + 降级 |
| 🟠 P1 | 数据库迁移（Alembic） | ❌ |
| 🟡 P2 | 移动端 API 全量对接 | ❌ |
| 🟡 P2 | 策略信号 WS 前端订阅 | ❌ |
| 🟡 P2 | Web 控制台测试覆盖 | ❌ |
| 🟢 P3 | token httpOnly cookie | ❌ |

---

## 6. 后端环境变量参考

安装向导自动生成 `.env`。完整变量列表：

```env
# 应用
APP_NAME=CryptoQuant
APP_VERSION=0.3.0
DEBUG=false                          # 生产必须 false
SECRET_KEY=                          # 安装向导自动生成（生产校验安全性）
JWT_SECRET_KEY=                      # 安装向导自动生成
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
PRODUCTION=true                      # 生产=true 触发密钥校验

# 数据库
DATABASE_URL=sqlite+aiosqlite:///./data/crypto_quant.db
# PostgreSQL: postgresql+asyncpg://user:password@localhost:5432/crypto_quant

# Redis
REDIS_URL=redis://localhost:6379/0   # 可选，缺失时部分功能降级

# CORS
CORS_ORIGINS=["http://localhost:8000"]
```

> ⚠️ `PRODUCTION=true` 时 `validate_production_secrets()` 拒绝默认密钥启动。开发环境不设此变量即可。

---

*v1.0 · 2026-04-27 · 整合自：STANDARDS.md + PM.md + DOCKER_OPTIMIZATION.md + MIRROR_ACCELERATION.md + SYSTEM_CHOICE_GUIDE.md + 系统架构设计文档_v2.md*
