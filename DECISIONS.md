# 币钱袋 - 架构决策记录 (ADR)

> v1.2 | 2026-04-26 | 状态：✅ 已建立

---

## ADR 索引

| ID | 标题 | 状态 |
|----|------|------|
| ADR-001 | 技术栈选型 | ✅ |
| ADR-002 | 状态管理方案 | ✅ |
| ADR-003 | 量化引擎部署位置 | ✅ |
| ADR-004 | 数据库选型 | ✅ |
| ADR-005 | 消息队列选型 | ✅ |
| ADR-006 | 安全审计修复（P0/P1问题清零） | ✅ |
| ADR-007 | 移动端可选登录 + 占位数据兜底 | ✅ |
| ADR-008 | 网页控制台 + 安装向导 + 接口契约修复 | ✅ |
| ADR-009 | Sprint 3 完成：策略引擎 + 回测 + 交易所优化 + 响应式适配 | ✅ |
| ADR-010 | 现实检验修复：生产安全 + 止损止盈 + 测试框架 | ✅ |
| ADR-011 | 自定义规则策略 + 规则引擎 | ✅ |
| ADR-012 | 前端 P0 断裂点修复 + 设计系统 v3.1 | ✅ |

---

## ADR-001：技术栈选型

**决策**：Flutter + Python FastAPI + PostgreSQL/TimescaleDB + Redis + Docker

| 层级 | 选型 | 备选 |
|------|------|------|
| 移动端 | Flutter (Dart) | React Native |
| 后端 | Python FastAPI | Go Gin |
| 主数据库 | PostgreSQL | MySQL |
| 时序数据 | TimescaleDB | InfluxDB |
| 缓存/队列 | Redis + Redis Streams | RabbitMQ |
| 行情数据源 | Binance WebSocket API | CoinGecko |

**正面**：Flutter 跨平台；FastAPI 高性能自带 OpenAPI；TimescaleDB 基于 PG 运维统一。  
**负面**：Flutter 需学 Dart；Python 量化计算不如 C++/Go（但足够）。

---

## ADR-002：状态管理方案

**决策**：Flutter 使用 **Riverpod**（类型安全、编译时检查、易测试）

**备选否决**：BLoC（代码量大）、Provider（大型应用难维护）

---

## ADR-003：量化引擎部署位置

**决策**：**云端部署**（不受移动设备性能限制，便于更新和风控统一管理）

**负面**：策略逻辑上传存在泄露风险；依赖网络连接。

---

## ADR-004：数据库选型

**决策**：PostgreSQL（业务数据）+ TimescaleDB Hypertable（K线历史）+ Redis（缓存）

**一体化优势**：TimescaleDB 基于 PG，运维统一，支持关系查询与时序查询 JOIN。

---

## ADR-005：消息队列选型

**决策**：**Redis Streams**（已有 Redis 依赖，零额外引入；支持消费者组；延迟极低）

**备选否决**：Kafka（过重）、RabbitMQ（运维复杂）

---

## ADR-006：安全审计修复（P0/P1 问题清零）

**背景**：2026-04-21 全量代码审计，共发现 27 项问题。

| 等级 | 数量 | 关键变更 |
|------|------|---------|
| P0（阻塞） | 6 | 移除硬编码默认密钥；API Key 加 AES-256 加密；端点加认证；Token 类型校验；数值范围校验 |
| P1（严重） | 18 | 修复模型字段不一致；去重代码；httpx 单例复用；Redis Lock；结构化日志；CORS 加固 |
| P2（改进） | 5 | Redis 行情缓存；提取常量；依赖注入规范化 |
| P3（建议） | 1 | 更新 DECISIONS.md |

**后续要求**：数据库迁移（新增 balance/frozen_balance/pnl 字段）；安装 `cryptography` 依赖；现有 API Key 重新加密存储。

---

## ADR-007：移动端可选登录 + 占位数据兜底

**背景**：原设计强制登录，后端不可用时 App 完全无法使用。

**决策**：
1. 路由不强制跳转登录页，未登录可自由浏览
2. API 失败时各 Provider 返回 `DashboardData.placeholder()` 占位数据
3. 登录入口放在设置页用户卡片
4. 已登录访问 /login 自动重定向 /dashboard
5. 所有 `demo`/`演示` 命名改为 `placeholder`/`占位`

**正面**：无后端可浏览；降低新用户门槛；API 失败自动降级。  
**负面**：占位数据可能被误认为真实（已加"示例数据"提示）。

---

## ADR-008：网页控制台 + 安装向导 + 接口契约修复

**背景**：
1. 项目只有 Flutter 移动端，缺少桌面端可视化入口；`prototype.html` 已有交互逻辑但未接真实 API
2. 首次启动需要手动配置 `.env`（SECRET_KEY/DATABASE_URL/JWT_SECRET_KEY 无默认值），不是产品级体验
3. 前后端接口契约存在 3 处不一致：Token 刷新返回格式、资产字段名、策略 templateId 类型

**决策**：
1. 在 FastAPI 中挂载 `/web` 轻量网页控制台，从 `prototype.html` 拆分为模块化前端（登录/Dashboard/策略/回测）
2. 实现安装向导：config.py 开发默认值 + database.py 懒初始化 + setup API + setup.html 3步向导
3. 修复接口契约：`/auth/refresh` 改 APIResponse 包裹；资产字段名对齐前端；templateId 反向映射为字符串 code
4. 清除所有模块级 `settings = get_settings()` 缓存，支持运行时热重载配置
5. 默认数据库改为 SQLite（零配置启动），安装向导可选切换 PostgreSQL

**正面**：
- 首次启动体验从"改配置文件"变为"网页填表单"
- 网页控制台提供桌面端可视化入口
- 接口契约统一，移动端和网页端数据一致
- SQLite 默认数据库降低开发门槛

**负面**：
- 网页 v1 不含实盘下单（安全考量）
- setup 完成后需重启部分连接（引擎/Redis），有短暂不可用
- SQLite 不适合生产高并发

**日期/决策者**：2026-04-24 | @backend

---

## ADR-009：Sprint 3 完成 — 策略引擎 + 回测 + 交易所优化 + 响应式适配

**背景**：
1. Sprint 3 目标为策略引擎与回测框架完成，8个任务全部完成
2. 交易所适配器存在重试/限流/异常细分等工程缺陷
3. 网页控制台只适配桌面端，768px 以下侧栏直接隐藏无替代导航
4. 缺少交易所账户管理前端界面

**决策**：

### 策略引擎（5 种策略 + 实时运行器 + 绩效计算）
1. 实现 MAStrategy / RSIStrategy / BollingerStrategy / GridStrategy / MartingaleStrategy
2. StrategyRunner 单例管理运行中策略，每个实例一个 asyncio.Task
3. PerformanceCalculator 计算完整绩效指标（收益/夏普/回撤/胜率/盈亏比）
4. 60s 防抖避免重复信号

### 回测框架
1. BacktestService 使用 Binance 公开 API 获取真实历史 K 线（自动分页）
2. 逐根 K 线驱动策略 analyze()，模拟订单执行
3. 结果持久化到 BacktestResult 模型，支持历史查询

### 交易所适配器优化
1. 异常体系增强：`RateLimitError` / `NetworkError` / `OrderRejectedError`
2. 重试+限流：指数退避（1→2→4s），下单不重试，查询3次
3. 安全 Decimal：`_safe_decimal()` / `_safe_divide()` 防数值异常
4. Huobi accountId 缓存：TTL 5分钟 + 失败清理

### 响应式适配（4 断点）
1. 768px 以下：侧栏改为抽屉式 + 汉堡菜单 + 遮罩层
2. 策略/回测页两列→单列；grid-2/3/4 逐级降列数
3. 表格加 `.table-wrap` 横向滚动
4. 480px 以下：按钮全宽，账户卡片纵向堆叠

### 交易所账户管理
1. 后端 CRUD API：POST/GET/DELETE `/trading/accounts`
2. 前端 accounts.js：添加/删除/列表展示
3. API Key AES-256 加密存储

**正面**：
- Sprint 3 目标 100% 完成
- 网页端从纯桌面变为全设备可用
- 交易所交互更健壮（重试/限流/异常细分）
- 交易所账户可在网页端管理

**负面**：
- 自动下单（StrategyRunner→OrderService）未实现，需 exchange_account 关联
- 零测试覆盖率仍然是最紧迫的基础设施问题
- 回测降级策略（模拟数据）可能导致误导性结果

**日期/决策者**：2026-04-24 | @backend

---

## ADR-010：现实检验修复 — 生产安全 + 止损止盈 + 测试框架

**背景**：
1. 生产环境仍用开发默认密钥，无运行时校验
2. debug 模式默认 True，日志泄露敏感信息
3. 止损止盈前端只存数据库，未实际提交交易所条件单
4. 零测试覆盖率是最紧迫的基础设施问题

**决策**：

### P0 修复（4项）
1. **生产密钥校验**：`validate_production_secrets()` 拒绝默认密钥启动
2. **debug 默认 False**：docker-compose 通过环境变量控制
3. **止损止盈实际提交**：适配器新增 `create_stop_order()` 三家实现 + Position 新增 order_id + 降级机制
4. **测试框架**：`tests/` 目录，SQLite 内存 DB，40+ 用例

### P1 修复（7项）
- 事务安全 / WS user_id / 限流中间件 / Redis 复用 / OKX 时间同步 / get_db 不自动 commit / 下单默认 30% 仓位

**正面**：生产不再有默认密钥漏洞；止损止盈真正生效；测试从零到 40+
**负面**：6 个 P2/P3 仍未修；部分修复为最小实现

**日期/决策者**：2026-04-26 | @backend

---

## ADR-011：自定义规则策略 + 规则引擎

**背景**：5种内置策略无法自定义买卖条件，新增策略需写代码+改模型+迁移

**决策**：
1. 新增 `strategy_type="rule"` — JSON DSL 定义买卖条件，无需写代码
2. 新增 `indicators.py`（14种技术指标）+ `rule_engine.py`（引擎核心+校验+描述）
3. AND/OR 逻辑组合 + 事件型交叉检测
4. `strategy_type` 从 Enum 改为 String(50)，新增类型零迁移
5. API：`POST /strategies/validate-rules` 校验规则

**正面**：用户不写代码即可构建自定义策略；新增类型零迁移
**负面**：JSON DSL 有学习曲线；指标计算依赖历史K线数据量

**日期/决策者**：2026-04-26 | @quant

---

## ADR-012：前端 P0 断裂点修复 + 设计系统 v3.1

**背景**：交易按钮文案不跟随方向、平仓未传 account_id、回测不支持规则策略、设计系统需升级

**决策**：
1. **交易按钮文案**：联动买卖方向（"买入"/"卖出"）
2. **平仓传 accountId**：后端新增 `ClosePositionRequest` body
3. **回测规则构建器**：完整的条件组 UI + DSL 构建
4. **设计系统 v3.1**：Geist Sans 字体 + 流体缩放 + 规则构建器样式

**正面**：交易流程无断裂；流体缩放更自然；回测支持所有策略
**负面**：策略信号 WS 前端未订阅；规则构建器 UI 复杂度高

**日期/决策者**：2026-04-26 | @frontend

---

## ADR 模板

```markdown
## ADR-XXX：标题

**背景**：[问题上下文]
**决策**：[方案]
**备选**：[未选原因]
**正面**：- ...
**负面**：- ...
**日期/决策者**：YYYY-MM-DD | @角色
```

---
*最后更新：2026-04-26（ADR-010 现实检验修复 + ADR-011 规则引擎 + ADR-012 前端P0修复）*
