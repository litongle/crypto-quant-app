# 币钱袋 - 架构决策记录 (ADR)

> v1.0 | 2026-04-21 | 状态：✅ 已建立

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
*最后更新：2026-04-24（ADR-008 网页控制台 + 安装向导 + 接口契约修复）*
