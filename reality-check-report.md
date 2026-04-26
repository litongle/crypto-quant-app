# 🧐 币钱袋 (CryptoQuant) 上线前现实检验报告

**评估日期**: 2026-04-26  
**评估人**: 现实检查员 (Integration Agent)  
**证据来源**: 全量代码审计 — 后端 45 个 .py + 8 个 .js + 2 个 .html + Flutter 35 个 .dart  
**代码版本**: main 分支 (10 个未提交修改)

---

## 🔍 现实检查验证

**执行的审查范围**:
1. ✅ 后端 API 层: auth/users/orders/market/strategies/backtest/ws_market (10 个路由模块)
2. ✅ 后端服务层: market_service/order_service/strategy_service/backtest_service/auth_service (6 个服务)
3. ✅ 后端核心层: security/database/config/strategy_runner/schemas (5 个核心模块)
4. ✅ 前端 Web: api.js/dashboard.js + HTML/CSS 全部页面
5. ✅ Docker 部署: Dockerfile + docker-compose.yml
6. ✅ Flutter 移动端: 35 个 .dart 文件概览
7. ✅ 数据模型: exchange/order/strategy/user/signal/backtest (6 个模型)

---

## 🚨 关键发现汇总

| 级别 | 数量 | 说明 |
|------|------|------|
| 🔴 P0 — 阻断上线 | **5** | 必须修复，否则不能发布 |
| 🟠 P1 — 严重问题 | **7** | 上线后很快会暴露，应尽快修复 |
| 🟡 P2 — 中等问题 | **9** | 影响用户体验和系统稳定性 |
| 🔵 P3 — 建议优化 | **6** | 提升质量，可排期处理 |

---

## 🔴 P0 — 阻断上线的问题

### P0-1: 生产环境使用硬编码开发密钥

**位置**: `config.py:34-35`

```python
secret_key: str = "dev-secret-key-change-me"
jwt_secret_key: str = "dev-jwt-secret-key-change-me"
```

**现实**: 虽然文档说"安装向导生成真实密钥"，但：
- 如果用户跳过安装向导或 .env 未正确配置，系统会用这些占位值启动
- 没有启动时校验：**生产环境完全可以带默认密钥运行**
- Fernet 加密的 API Key 也是基于这个 `secret_key` 派生的——如果密钥是默认值，所有加密形同虚设
- JWT 用默认密钥签名 = 任何人都能伪造 token

**修复建议**: 启动时检测 `environment=production` 且密钥为默认值 → **拒绝启动**

---

### P0-2: 调试模式在生产环境可能开启

**位置**: `config.py:28`

```python
debug: bool = True
```

**现实**: 默认值为 `True`。docker-compose.yml 也显式设置了 `DEBUG=true`。这意味着：
- SQLAlchemy echo=all → 所有 SQL 语句打印到日志
- uvicorn reload=True → 热重载（仅开发用）
- 可能泄露敏感信息到错误响应

**修复建议**: `debug` 默认值改为 `False`，生产环境必须显式设置

---

### P0-3: 止损止盈只在数据库层面设置，未实际提交到交易所

**位置**: `order_service.py:507-587`

```python
position.stop_loss_price = stop_price
await self.session.commit()
```

**现实**: 止损止盈只在本地数据库记录了一个价格，**没有调用交易所 API 设置条件单**。用户以为止损已生效，但价格跌破止损线时不会有任何自动平仓动作。

**这是量化交易系统的核心风控缺陷。** 用户看到"已设置止损"→ 信心满满 → 实际没有保护 → 爆仓。

**修复建议**: 调用交易所条件单 API（Binance: `POST /api/v3/order` with `stopPrice` + `type=STOP_LOSS`）

---

### P0-4: 零测试覆盖率

**现实**: 整个项目没有 `tests/` 目录，没有 pytest 配置，没有任何自动化测试。

- 后端 35+ 个 API 端点 = 0 个测试
- 5 种策略引擎 = 0 个测试
- 3 家交易所适配器 = 0 个测试
- 订单/持仓/账户核心业务 = 0 个测试

量化交易系统涉及真实资金。没有测试 = 每次改动都是赌命。

**修复建议**: 至少覆盖：
1. 认证流程（注册/登录/token刷新）
2. 订单生命周期（创建→提交→成交/取消）
3. 策略引擎信号生成
4. 金额计算（Decimal 精度、手续费、盈亏）

---

### P0-5: 未提交的代码变更 (10 个文件)

**现实**: git status 显示 10 个文件有修改但未提交，包括：
- auth.py, backtest.py, market.py, orders.py, strategies.py, users.py, ws_market.py（API 层全改了）
- market_service.py, order_service.py（服务层改了）
- api.js（前端改了）

这些是安全审计修复（P0-P3），代码已经修改但**没有提交也没有验证**。意味着：
- 当前运行的可能不是这些修改后的代码
- 修改是否经过验证？未知
- 一键回滚能力 = 零

---

## 🟠 P1 — 严重问题

### P1-1: 平仓操作先标记 closed 再执行，顺序反转

**位置**: `order_service.py:486-490`

```python
await self.submit_order(order.id, user_id)   # 提交到交易所
position.status = "closed"                    # 标记已平仓
```

**问题**: `submit_order` 可能失败（网络错误、交易所拒绝），但 position 已经不会回滚为 "open"。`submit_order` 抛异常时 position 状态不变（没 commit），但如果 `submit_order` 成功提交了订单但后续 commit 失败 → 数据不一致。

**修复**: 使用数据库事务，确保订单提交成功后再更新 position 状态。

---

### P1-2: WS 连接数限制依赖 `_user_id` 私有属性 hack

**位置**: `ws_market.py:644`

```python
sub._user_id = user_id  # 记录用户ID用于连接数限制
```

**问题**: Subscription 是 dataclass，`_user_id` 不是其定义的字段。这种 monkey-patch 方式脆弱且不可靠。如果后续有人用 `dataclasses.replace()` 或序列化操作，这个属性会丢失。

**修复**: 在 Subscription dataclass 中正式添加 `user_id` 字段。

---

### P1-3: 市场数据 API 无认证保护

**位置**: `market.py:19-85`, `ws_market.py:604`

**现实**: 行情 API（ticker/kline/orderbook/symbols/tickers）不需要认证。虽然行情是公开数据，但：
- 无限流保护 → 任何人可以无限刷接口 → 对 Binance/OKX 的请求可能被限流
- 没有调用频率限制 → 可被用于 DDoS 放大攻击
- WS 连接有认证，但 REST 没有

**修复**: 至少加 IP 限流中间件

---

### P1-4: Redis 连接每次获取行情都创建新客户端

**位置**: `market_service.py:66-73`

```python
pool = await get_redis_pool()
client = aioredis.Redis(connection_pool=pool)
cached = await client.get(cache_key)
await client.aclose()
```

**问题**: 每次请求都 `Redis(connection_pool=pool)` + `aclose()`。虽然用了连接池，但 Redis 客户端对象重复创建/销毁有开销。高频行情请求下效率低。

**修复**: 复用 Redis 客户端实例，只在应用关闭时释放。

---

### P1-5: `_fetch_initial_ticker` OKX 分支有丑陋的 hack

**位置**: `ws_market.py:771`

```python
inst_id = BinanceWSProxy.__bases__[0]._to_inst_id(None, symbol) if hasattr(BinanceWSProxy, '__bases__') else symbol
```

**问题**: 试图从 BinanceWSProxy 的基类调用 OKX 的方法，逻辑完全错误。虽然后面有简单转换覆盖了，但这段代码说明有问题未清理。

**修复**: 删除这行，只保留下面的简单转换。

---

### P1-6: 数据库连接在 get_db() 中自动 commit

**位置**: `database.py:97-108`

```python
async def get_db():
    async with session_maker() as session:
        try:
            yield session
            await session.commit()  # 自动 commit
        except Exception:
            await session.rollback()
            raise
```

**问题**: 每次请求结束自动 commit。如果路由中有多个数据库操作，中间发生异常时部分数据可能已经 commit 了（因为前面的 commit 已经执行）。对于订单/持仓这种金融操作，应该使用显式事务控制。

---

### P1-7: 策略运行器自动下单使用 95% 余额

**位置**: `strategy_runner.py:419-420`

```python
invest_amount = balance * Decimal("0.95")
```

**问题**: 策略自动下单使用 95% 可用余额，且不可配置。如果用户有多个策略同时运行，每个都会试图用 95% 余额 → 余额不足被交易所拒绝。没有考虑多策略之间的余额分配。

**修复**: 策略参数中添加 `max_invest_percent`，默认降低到 30%。

---

## 🟡 P2 — 中等问题

### P2-1: 批量行情使用随机种子生成趋势线

**位置**: `market.py:112-116`

```python
import random
random.seed(int(price * 1000) % 10000)
sparkline = [price * (1 + (random.random() - 0.5) * 0.02) for _ in range(8)]
```

**问题**: 迷你趋势线是用随机数"伪造"的，不是真实历史数据。用户以为看到的是真实走势，实际是随机生成的装饰。在量化交易 App 里，这种做法会严重误导决策。

---

### P2-2: docker-compose 密码硬编码

**位置**: `docker-compose.yml:14,31`

```yaml
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/crypto_quant
POSTGRES_PASSWORD=postgres
```

**问题**: 生产部署时如果直接用这个 compose 文件，数据库密码就是 `postgres`。没有注释说明或环境变量替换机制。

---

### P2-3: 回测降级到模拟数据时标记不够明显

**位置**: `backtest_service.py:128`

```python
data_source = "mock" if getattr(self, "_using_mock_data", True) else "binance"
```

**问题**: 默认值是 `True`（模拟数据），只有真实获取到 K 线后才设为 `False`。前端只在一个 `warning` 字段提示，不够醒目。

---

### P2-4: 缺少 CORS 生产域名配置

**位置**: `config.py:49`

```python
cors_origins: str = "http://localhost:3000,http://127.0.0.1:8000,http://localhost:8000"
```

**问题**: 只有本地开发域名。部署到线上后需要手动添加生产域名，否则前端无法请求 API。

---

### P2-5: Flutter API 客户端硬编码地址

**位置**: `mobile/lib/core/network/api_client.dart`

**问题**: 移动端 API 地址需要动态配置（开发/测试/生产环境不同），但目前可能是硬编码的。

---

### P2-6: 订单模型中 `exchange_order_id` 有 unique 约束

**位置**: `order.py:40`

```python
exchange_order_id: Mapped[str | None] = mapped_column(
    String(100), nullable=True, unique=True, index=True
)
```

**问题**: 同一交易所订单 ID 不会重复，但不同交易所可能重复。如果用户同时在 Binance 和 OKX 下单，交易所返回的订单 ID 可能冲突。

**修复**: `unique` 应改为联合唯一约束 `(exchange_order_id, account_id)`。

---

### P2-7: 策略实例创建时直接设为 running

**位置**: `strategy_service.py:157`

```python
status="running",  # 移动端创建即运行
```

**问题**: 创建即运行意味着用户还没确认参数就开始执行策略。如果参数有误，可能立即产生错误信号甚至自动下单。

---

### P2-8: 缺少数据库迁移工具

**现实**: 没有使用 Alembic（虽然 Dockerfile 里装了）。数据库 schema 变更时只能删除重建，线上数据无法平滑迁移。

---

### P2-9: 全局异常处理器吞掉所有错误信息

**位置**: `main.py:107-118`

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"message": "服务器内部错误"})
```

**问题**: 所有未捕获异常统一返回"服务器内部错误"，不区分 500/502/503。在交易系统中，502（网关错误，可重试）和 500（服务端错误，不要重试）的区别非常重要。

---

## 🔵 P3 — 建议优化

### P3-1: 日志格式不统一
- 有些用 `logger.info()`，有些用 `logger.warning()`
- 没有结构化日志（JSON format），生产环境难以做日志分析

### P3-2: 缺少速率限制中间件
- 所有 API 端点无调用频率限制
- 推荐: `slowapi` 或自定义中间件

### P3-3: 缺少健康检查详细信息
- `/health` 只返回 `{"status": "healthy"}`，应包含数据库/Redis/交易所连接状态

### P3-4: 前端 token 存储在 localStorage
- XSS 攻击可窃取 token
- 建议使用 httpOnly cookie（至少 refresh token）

### P3-5: 密码处理中 UTF-8 截断可能产生无效字符
- `security.py:20` `decode("utf-8", errors="ignore")` 可能静默丢弃密码字符

### P3-6: 缺少请求 ID / 链路追踪
- 多个服务调用时难以追踪问题

---

## 📊 现实质量评估

| 维度 | 评级 | 说明 |
|------|------|------|
| **安全** | C | 密钥管理有致命缺陷，加密存储设计OK但实现依赖默认值 |
| **功能完整性** | B- | 功能覆盖全面（35+端点），但止损止盈核心缺陷 |
| **代码质量** | B | 架构清晰，命名规范，但缺少测试和事务安全 |
| **部署就绪度** | D+ | Docker配置有，但密钥/环境变量/数据库迁移全没准备好 |
| **可观测性** | C- | 基本日志有，但缺监控/告警/链路追踪 |
| **风控** | D | 止损止盈未实现、95%余额自动下单、缺少限流保护 |

---

## 🎯 现实质量认证

**整体质量评级**: **C+**

**设计实施级别**: 良好（架构清晰，功能全面）

**系统完整性**: ~75%（框架搭好了，核心风控功能未真正落地）

**生产就绪度**: ❌ **需要工作** — 默认"需要工作"状态，证据不足以认证"就绪"

---

## 🔄 部署就绪评估

**状态**: ❌ **需要工作**

### 生产前必须修复（P0 + 关键 P1）:

| # | 问题 | 预估工时 | 优先级 |
|---|------|----------|--------|
| 1 | 生产环境密钥校验（拒绝默认密钥启动） | 2h | 🔴 |
| 2 | debug 默认值改 False | 0.5h | 🔴 |
| 3 | 止损止盈实际提交到交易所 | 8h | 🔴 |
| 4 | 提交未暂存的代码变更并验证 | 4h | 🔴 |
| 5 | 最小测试覆盖（认证+订单+金额计算） | 16h | 🔴 |
| 6 | 平仓操作事务安全 | 4h | 🟠 |
| 7 | WS Subscription 添加 user_id 字段 | 1h | 🟠 |
| 8 | 行情 API 限流 | 4h | 🟠 |
| 9 | 自动下单余额比例可配置 | 2h | 🟠 |
| 10 | docker-compose 密码环境变量化 | 1h | 🟡 |

**最小上线工期估计**: 2-3 周修复周期

**需要修订周期**: 是（1-2 轮修复+验证）

---

## 📈 下次迭代成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| 测试覆盖率 | 0% | ≥60%（核心模块≥80%） |
| P0 问题数 | 5 | 0 |
| P1 问题数 | 7 | ≤2 |
| 止损止盈实际生效 | ❌ | ✅（调用交易所条件单API） |
| 生产环境安全启动 | ❌ | ✅（默认密钥拒绝启动） |
| 数据库迁移方案 | ❌ | ✅（Alembic） |

---

**集成代理**: 现实检查员 🧐  
**评估日期**: 2026-04-26  
**下次评估**: 修复实施后
