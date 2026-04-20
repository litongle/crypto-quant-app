# 币钱袋（CryptoQuant）代码审查标准与流程

> 版本：1.0 | 生效日期：2026-04-21 | 维护者：技术团队

---

## 目录

1. [审查目标与原则](#1-审查目标与原则)
2. [问题严重等级定义](#2-问题严重等级定义)
3. [审查标准：六大维度](#3-审查标准六大维度)
   - 3.1 [安全性（Security）](#31-安全性security)
   - 3.2 [正确性（Correctness）](#32-正确性correctness)
   - 3.3 [架构与设计（Architecture）](#33-架构与设计architecture)
   - 3.4 [可维护性（Maintainability）](#34-可维护性maintainability)
   - 3.5 [性能（Performance）](#35-性能performance)
   - 3.6 [测试覆盖（Testing）](#36-测试覆盖testing)
4. [审查流程](#4-审查流程)
5. [质量门禁（Quality Gates）](#5-质量门禁quality-gates)
6. [PR 模板](#6-pr-模板)
7. [自动化检查配置](#7-自动化检查配置)
8. [审查角色与职责](#8-审查角色与职责)
9. [当前项目已知问题清单](#9-当前项目已知问题清单)
10. [附录：审查 Checklist 速查表](#10-附录审查-checklist-速查表)

---

## 1. 审查目标与原则

### 目标

- **守住底线**：安全漏洞和正确性缺陷不上线
- **持续改善**：每次 PR 让代码比之前好一点
- **知识共享**：审查是团队学习的渠道，不是惩罚工具
- **量化可追溯**：问题有等级、有记录、有闭环

### 原则

| 原则 | 说明 |
|------|------|
| **自动化优先** | 能由工具检查的，不依赖人工 |
| **分层审查** | P0/P1 阻塞合并，P2/P3 可后续跟进 |
| **领域敏感** | 金融计算、交易所对接、用户资产相关代码需额外严格审查 |
| **最小审查范围** | 单次 PR 不超过 400 行变更（自动生成除外），超出则拆分 |
| **审查时效** | PR 提交后 24 小时内完成首轮审查 |

---

## 2. 问题严重等级定义

| 等级 | 名称 | 定义 | 处理方式 |
|------|------|------|----------|
| **P0** | 🔴 阻塞 | 安全漏洞、资金风险、数据损坏 | **必须立即修复，阻塞合并** |
| **P1** | 🟠 严重 | 功能错误、接口不一致、核心逻辑缺陷 | **必须修复后合并** |
| **P2** | 🟡 改进 | 架构不合理、性能隐患、代码重复 | **应修复，可创建 Issue 跟进** |
| **P3** | 🔵 建议 | 风格优化、命名改善、注释补充 | **建议改进，不阻塞合并** |

### 等级判定决策树

```
是否涉及资金/资产/密钥？
  ├─ 是 → P0
  └─ 否 → 是否导致功能不可用或数据错误？
              ├─ 是 → P1
              └─ 否 → 是否影响扩展性/性能/可维护性？
                          ├─ 是 → P2
                          └─ 否 → P3
```

---

## 3. 审查标准：六大维度

### 3.1 安全性（Security）

> 金融应用安全是底线。以下任何一项不通过，直接 P0。

#### 3.1.1 密钥与凭证管理

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| SEC-01 | 禁止硬编码密钥/凭证 | P0 | `secret_key`、`jwt_secret_key`、数据库URL等不得写在源码中，必须从环境变量读取且无默认值 |
| SEC-02 | `.env.example` 提供模板 | P2 | 提供不含真实值的 `.env.example`，方便新成员配置 |
| SEC-03 | 敏感字段加密存储 | P0 | 交易所 API Key/Secret 必须加密存储（AES-256），字段名不得误导（如标记 `encrypted` 必须真加密） |
| SEC-04 | 禁止日志输出敏感信息 | P1 | 不得在日志中输出 token、密码、API Key、完整请求体 |

**本项目已知问题**：
- ❌ `config.py` 中 `secret_key`、`jwt_secret_key`、数据库URL均有硬编码默认值
- ❌ `ExchangeAccount.api_secret` 字段名含 `encrypted` 但实际未加密
- ❌ `main.py` 使用 `print()` 输出启动信息，可能泄露配置

#### 3.1.2 认证与授权

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| SEC-05 | 所有业务端点必须认证 | P0 | 除 `/docs`、`/health`、`/auth/login`、`/auth/register` 外，所有端点需认证 |
| SEC-06 | Refresh Token 类型校验 | P0 | 刷新令牌时必须验证 token 类型为 `refresh`，防止 access token 被复用 |
| SEC-07 | JWT payload 类型安全 | P1 | `payload.get("sub")` 返回值为 str，转 int 需显式转换并处理异常 |
| SEC-08 | CORS 配置最小化 | P1 | 生产环境禁用 `allow_origins=["*"]`，禁止 `allow_credentials=True` + 通配符组合 |

**本项目已知问题**：
- ❌ `/users/me` 端点无认证，返回硬编码用户数据
- ❌ 回测 API 缺失认证
- ❌ `auth_service.py` 的 `refresh_tokens()` 未验证 token 类型
- ❌ `deps.py` 中 `user_id: int = payload.get("sub")` 类型不安全
- ❌ CORS 配置 `allow_methods=["*"]` + `allow_headers=["*"]` + `allow_credentials=True` 过于宽松

#### 3.1.3 输入验证

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| SEC-09 | Pydantic 模型校验所有外部输入 | P1 | 请求体、路径参数、查询参数均需 Pydantic 校验 |
| SEC-10 | 金融数值范围校验 | P0 | 金额、数量、价格必须校验 > 0，百分比 0-100，避免负数或溢出 |
| SEC-11 | SQL 注入防护 | P0 | 禁止字符串拼接 SQL，使用 SQLAlchemy ORM/参数化查询 |

---

### 3.2 正确性（Correctness）

> 金融计算的正确性直接关系到用户资产安全。

#### 3.2.1 数据模型一致性

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| COR-01 | 模型字段与服务层使用一致 | P1 | Service 层访问的 Model 字段必须在 Model 中定义，类型匹配 |
| COR-02 | ForeignKey 语义正确 | P1 | 外键不得自引用除非语义合理（如树形结构） |
| COR-03 | 模型字段类型与业务语义匹配 | P1 | JSON/dict 字段不得与 ForeignKey 混用 |

**本项目已知问题**：
- ❌ `Signal.market_data` 类型为 `dict` 但定义了 `ForeignKey("signals.id")`，自引用且语义错误
- ❌ `asset_service.py` 使用 `account.balance`/`account.frozen_balance`，但 `ExchangeAccount` 模型无此字段
- ❌ `asset_service.py` 使用 `o.pnl`，但 `Order` 模型无此字段

#### 3.2.2 业务逻辑正确性

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| COR-04 | 金融计算使用 Decimal | P0 | 金额、价格、比率计算必须使用 `Decimal`，禁止 `float` |
| COR-05 | 市价单价值计算 | P1 | 市价单的订单价值必须有合理的价格来源，不得默认为 0 |
| COR-06 | 交易所适配器字段映射 | P1 | 第三方 API 返回字段必须正确映射，验证字段含义 |
| COR-07 | 止损/止盈方法存在性 | P1 | API 调用的方法必须在对应 Service 中实现 |

**本项目已知问题**：
- ❌ `order_service.py` 市价单 `order_value = quantity * (price or Decimal("0"))` 结果为 0
- ❌ OKX 适配器 `price_change_percent` 使用 `sodUtc8`（开盘价）而非百分比字段
- ❌ `orders.py` API 调用 `set_stop_loss`/`set_take_profit`，但 OrderService 无此方法

#### 3.2.3 回测数据真实性

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| COR-08 | 禁止用随机数伪造指标 | P1 | Sharpe Ratio、波动率等指标必须基于真实数据计算，禁止 `random.uniform()` |
| COR-09 | 回测需使用真实市场数据 | P1 | 不得使用 `_generate_mock_prices()` 生成假数据 |
| COR-10 | 回测结果标注数据来源 | P2 | 回测结果需标注数据来源和时间范围 |

---

### 3.3 架构与设计（Architecture）

#### 3.3.1 代码去重

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| ARC-01 | 禁止跨文件重复核心逻辑 | P1 | 认证、密码处理、策略模板等核心逻辑只允许一份实现 |
| ARC-02 | Provider 文件唯一性 | P1 | 同一功能的 Provider 只允许一个文件定义 |
| ARC-03 | 模型类定义唯一性 | P1 | 数据模型类只在一处定义，UI 层可引用但不可重定义 |

**本项目已知问题**：
- ❌ `get_current_user` 在 `auth_service.py` 和 `deps.py` 两处定义
- ❌ `pwd_context` 在 `security.py` 和 `auth_service.py` 两处定义
- ❌ 策略模板定义在 `strategies.py` 和 `seed_data.py` 两处硬编码
- ❌ `dashboard_provider.dart` 和 `dashboard_providers.dart` 两个竞争性 Provider 文件
- ❌ `strategy_center_page.dart` 重新定义了 `StrategyTemplate`/`StrategyInstance` 类

#### 3.3.2 分层架构合规

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| ARC-04 | 严格分层依赖方向 | P1 | API → Service → Repository → Model，禁止跨层或反向依赖 |
| ARC-05 | 依赖注入规范 | P2 | 数据库 session 通过 FastAPI Depends 注入，禁止裸 `Annotated` 声明 |
| ARC-06 | Service 层无 HTTP 依赖 | P1 | Service 层不得直接依赖 `Request`/`Response` 对象 |

#### 3.3.3 配置管理

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| ARC-07 | 配置集中管理 | P2 | 所有配置项通过 `config.py` + `.env` 管理，禁止分散硬编码 |
| ARC-08 | 环境区分 | P2 | 开发/测试/生产环境配置分离，通过 `ENV` 变量切换 |

---

### 3.4 可维护性（Maintainability）

#### 3.4.1 日志规范

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| MNT-01 | 使用结构化日志 | P1 | 使用 `logging` 模块，禁止 `print()` 输出运行时信息 |
| MNT-02 | 日志级别正确 | P2 | ERROR：需立即处理；WARNING：异常但可恢复；INFO：关键业务事件；DEBUG：开发调试 |
| MNT-03 | 日志包含上下文 | P2 | 关键操作日志需包含 user_id、request_id 等上下文 |

**本项目已知问题**：
- ❌ `main.py`、`seed_data.py` 使用 `print()` 而非结构化日志

#### 3.4.2 代码清晰度

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| MNT-04 | 禁止魔法数字 | P2 | 硬编码的数值常量（如 `Decimal("100000")`）需提取为命名常量 |
| MNT-05 | 函数单一职责 | P2 | 单个函数不超过 50 行，职责单一 |
| MNT-06 | 类型注解完整 | P2 | Python 函数签名必须包含参数和返回值类型注解 |
| MNT-07 | Dart 空安全 | P2 | Flutter 代码严格遵循空安全，避免 `!` 强制解包 |

#### 3.4.3 文档与注释

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| MNT-08 | 公共 API 必须有 docstring | P2 | Service 层公共方法、API 端点必须有 docstring |
| MNT-09 | 复杂算法需注释 | P2 | 量化策略核心算法、交易所签名逻辑等需有注释说明 |
| MNT-10 | 变更记录 | P3 | 重要架构变更需更新 `DECISIONS.md` |

---

### 3.5 性能（Performance）

#### 3.5.1 异步与连接管理

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| PRF-01 | HTTP 客户端复用 | P1 | `httpx.AsyncClient` 必须单例复用，禁止每次请求新建 |
| PRF-02 | Redis 连接池线程安全 | P1 | 全局连接池初始化需加锁或使用 `asyncio.Lock` |
| PRF-03 | 数据库连接池配置 | P2 | 配置合理的 `pool_size` 和 `max_overflow` |

**本项目已知问题**：
- ❌ `exchange_adapter.py` 每次请求新建 `httpx.AsyncClient()`
- ❌ `redis.py` 的 `get_redis_pool()` 全局 `_pool` 无锁保护

#### 3.5.2 查询优化

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| PRF-04 | 避免 N+1 查询 | P1 | 关联查询使用 `joinedload`/`selectinload`，禁止循环内查库 |
| PRF-05 | 高频数据 Redis 缓存 | P2 | 行情数据、策略配置等高频读取数据需 Redis 缓存 |
| PRF-06 | 分页查询 | P2 | 列表接口必须支持分页，禁止无限制 `query.all()` |

**本项目已知问题**：
- ❌ `asset_service.py` 存在 N+1 查询模式
- ❌ 行情数据未使用 Redis 缓存

---

### 3.6 测试覆盖（Testing）

> 当前项目测试覆盖率为 **0%**，这是最紧迫的质量问题。

#### 3.6.1 测试要求

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| TST-01 | 核心逻辑必须有单元测试 | P1 | 认证、金融计算、订单处理、策略信号等核心逻辑测试覆盖率 ≥ 80% |
| TST-02 | API 端点集成测试 | P1 | 每个业务 API 端点至少 1 个正向测试 + 1 个异常测试 |
| TST-03 | 安全测试 | P0 | 认证绕过、越权访问、SQL 注入等需有测试用例 |
| TST-04 | 交易所适配器 Mock 测试 | P1 | 交易所 API 返回解析逻辑需用 Mock 数据测试 |
| TST-05 | 回归测试 | P1 | Bug 修复必须附带回归测试 |

#### 3.6.2 测试规范

| 编号 | 检查项 | 等级 | 说明 |
|------|--------|------|------|
| TST-06 | 测试目录结构 | P2 | `backend/tests/` 下按 `unit/`、`integration/`、`conftest.py` 组织 |
| TST-07 | 测试隔离 | P1 | 每个测试独立，使用 fixture 创建/清理数据，禁止测试间依赖 |
| TST-08 | Flutter Widget 测试 | P2 | 核心页面至少覆盖渲染测试和交互测试 |

---

## 4. 审查流程

### 4.1 PR 审查流程

```
┌──────────────┐
│  开发者提交 PR  │
└──────┬───────┘
       │
       ▼
┌──────────────┐     失败     ┌───────────────┐
│  自动化检查     │─────────────▶│  退回修改       │
│  (CI Pipeline) │              └───────────────┘
└──────┬───────┘
       │ 通过
       ▼
┌──────────────┐     发现P0/P1  ┌───────────────┐
│  人工代码审查   │──────────────▶│  要求修改       │
│  (至少1人)     │               └───────────────┘
└──────┬───────┘
       │ 通过
       ▼
┌──────────────┐     发现P0     ┌───────────────┐
│  金融域专项审查  │──────────────▶│  要求修改       │
│  (涉及资金代码)  │              └───────────────┘
└──────┬───────┘
       │ 通过
       ▼
┌──────────────┐
│  合并到主分支   │
└──────────────┘
```

### 4.2 审查触发条件

| 触发条件 | 审查级别 | 审查者 |
|----------|----------|--------|
| 常规 PR | 标准审查 | 1 位团队成员 |
| 涉及认证/授权代码 | 安全专项 | 至少 1 位安全审查者 |
| 涉及资金/交易/订单 | 金融域专项 | 至少 1 位金融域审查者 |
| 涉及交易所对接 | 适配器专项 | 至少 1 位交易所对接审查者 |
| 架构变更/新模块 | 架构审查 | 技术负责人 |
| 数据库迁移 | 数据专项 | 技术负责人 + DB审查者 |

### 4.3 审查时限

| 阶段 | 时限 | 超时处理 |
|------|------|----------|
| 自动化检查 | 10 分钟 | 检查 CI 状态 |
| 首轮人工审查 | 24 小时 | 提醒审查者 |
| 修改后复审 | 12 小时 | 提醒审查者 |
| P0 紧急修复 | 4 小时 | 优先处理 |

### 4.4 审查意见格式

审查者使用以下格式提交意见：

```markdown
**[P0/P1/P2/P3]** 检查项编号 — 简述问题

**位置**：`文件路径:行号`

**问题**：具体描述

**建议**：修复方案或推荐做法
```

示例：
```markdown
**[P0]** SEC-01 — 硬编码数据库凭证

**位置**：`backend/app/config.py:15`

**问题**：`SQLALCHEMY_DATABASE_URL` 包含硬编码的默认数据库凭证

**建议**：移除默认值，改为 `str = Field(..., description="数据库连接URL")` 强制从环境变量读取
```

---

## 5. 质量门禁（Quality Gates）

### 5.1 PR 合并必须满足

| 门禁 | 条件 | 阻塞等级 |
|------|------|----------|
| CI 通过 | 所有自动化测试和检查通过 | 硬阻塞 |
| 无 P0 问题 | 审查中无未解决的 P0 问题 | 硬阻塞 |
| 无 P1 问题 | 审查中无未解决的 P1 问题 | 硬阻塞 |
| 至少 1 位审查者通过 | 获得至少 1 位审查者 Approve | 硬阻塞 |
| 金融域审查 | 涉及资金代码需金融域审查者通过 | 条件阻塞 |
| 代码覆盖率 | 新增代码行覆盖率 ≥ 80% | 软阻塞（可创建 Issue 跟进） |

### 5.2 发布前必须满足

| 门禁 | 条件 |
|------|------|
| 全量测试通过 | `pytest` 全部通过 |
| 安全扫描 | 无高危漏洞 |
| 核心模块覆盖率 | 认证/交易/策略模块 ≥ 80% |
| P2 问题清零 | 发布版本无未解决的 P2 问题 |
| 数据库迁移验证 | 迁移脚本在测试环境验证通过 |

---

## 6. PR 模板

```markdown
## 变更描述
<!-- 简要描述本次变更的内容和目的 -->

## 变更类型
- [ ] 🐛 Bug 修复
- [ ] ✨ 新功能
- [ ] ♻️ 重构
- [ ] 🔒 安全修复
- [ ] 📝 文档更新
- [ ] 🧪 测试补充

## 影响范围
<!-- 列出影响的模块/功能 -->

## 涉及资金/交易？
- [ ] 是（需要金融域专项审查）
- [ ] 否

## 涉及认证/授权？
- [ ] 是（需要安全专项审查）
- [ ] 否

## 测试情况
- [ ] 已添加单元测试
- [ ] 已添加集成测试
- [ ] 已手动测试
- [ ] 无需测试（说明原因：____）

## 自检清单
- [ ] 无硬编码密钥/凭证
- [ ] 金融计算使用 Decimal
- [ ] 新增 API 端点已有认证
- [ ] 无 print() 语句
- [ ] 新增 Model 字段已有迁移脚本
- [ ] 日志级别正确

## 相关 Issue
<!-- 关联的 Issue 编号 -->
```

---

## 7. 自动化检查配置

### 7.1 Python 后端（推荐工具链）

```yaml
# .github/workflows/code-quality.yml 或等效 CI 配置

lint:
  - ruff check .                    # 代码风格 + 静态分析
  - mypy --strict backend/          # 类型检查
  - bandit -r backend/              # 安全扫描
  - detect-secrets scan             # 密钥泄露检测

test:
  - pytest --cov=backend --cov-report=xml
  - coverage fail-under=60          # 逐步提升到 80

format:
  - ruff format .                   # 自动格式化
```

### 7.2 Flutter 前端

```yaml
lint:
  - flutter analyze                 # Dart 静态分析
  - dart format --set-exit-if-changed .

test:
  - flutter test --coverage
```

### 7.3 Git Pre-commit Hooks（推荐）

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
```

### 7.4 硬性 CI 规则

| 规则 | 实现 |
|------|------|
| 禁止 `print()` | `ruff` 规则 T201 |
| 禁止硬编码密钥 | `detect-secrets` + `bandit` |
| 禁止 `float` 金额 | 自定义 `ruff` 规则或 `mypy` plugin |
| 类型检查必须通过 | `mypy --strict` |
| 安全扫描无高危 | `bandit -ll` |

---

## 8. 审查角色与职责

| 角色 | 职责 | 人员 |
|------|------|------|
| **提交者** | 提交高质量 PR，完成自检，及时响应审查意见 | 所有开发者 |
| **审查者** | 按审查标准逐项检查，给出明确意见 | 团队成员轮值 |
| **安全审查者** | 专项审查安全相关代码（SEC-* 检查项） | 指定 1-2 人 |
| **金融域审查者** | 专项审查资金/交易/策略代码（COR-* 检查项） | 指定 1-2 人 |
| **技术负责人** | 架构变更审批，P2 问题优先级决策 | 1 人 |

### 审查轮值建议

- 每位开发者每周至少审查 2 个 PR
- 安全审查者和金融域审查者不参与自己提交的 PR 审查
- 审查意见必须在 PR 中留痕，禁止口头传达

---

## 9. 当前项目已知问题清单

> 以下问题来自 2026-04-21 的全量代码审计，按优先级排列。

### P0 - 必须立即修复

| # | 问题 | 位置 | 检查项 | 状态 |
|---|------|------|--------|------|
| 1 | 硬编码默认密钥（secret_key, jwt_secret_key, DB URL） | `config.py` | SEC-01 | ✅ 已修复 |
| 2 | API Key 未加密存储 | `ExchangeAccount` 模型 | SEC-03 | ✅ 已修复 |
| 3 | `/users/me` 端点无认证 | `api/v1/users.py` | SEC-05 | ✅ 已修复 |
| 4 | 回测 API 缺失认证 | `api/v1/backtest.py` | SEC-05 | ✅ 已修复 |
| 5 | Refresh Token 未验证类型 | `auth_service.py` | SEC-06 | ✅ 已修复 |
| 6 | 金融数值缺少范围校验 | 多处 | SEC-10 | ✅ 已修复 |
| 7 | 零测试覆盖率 | 全项目 | TST-01 | ⏳ 后续跟进 |

### P1 - 必须修复后合并

| # | 问题 | 位置 | 检查项 |
|---|------|------|--------|
| 1 | Signal.market_data 自引用 ForeignKey | `models/order.py` | COR-02, COR-03 |
| 2 | OKX 涨跌幅字段映射错误 | `exchange_adapter.py` | COR-06 |
| 3 | ExchangeAccount 缺失 balance/frozen_balance 字段 | `models/` vs `asset_service.py` | COR-01 |
| 4 | Order 缺失 pnl 字段 | `models/` vs `asset_service.py` | COR-01 |
| 5 | 市价单价值计算为 0 | `order_service.py` | COR-05 |
| 6 | set_stop_loss/set_take_profit 方法不存在 | `orders.py` vs `order_service.py` | COR-07 |
| 7 | 回测使用随机数伪造指标 | `backtest.py` | COR-08 |
| 8 | get_current_user 重复定义 | `auth_service.py` + `deps.py` | ARC-01 |
| 9 | pwd_context 重复定义 | `security.py` + `auth_service.py` | ARC-01 |
| 10 | 策略模板硬编码重复 | `strategies.py` + `seed_data.py` | ARC-01 |
| 11 | Dashboard 两个竞争 Provider 文件 | Flutter | ARC-02 |
| 12 | StrategyTemplate 类重复定义 | Flutter | ARC-03 |
| 13 | httpx.AsyncClient 每次请求新建 | `exchange_adapter.py` | PRF-01 |
| 14 | Redis 连接池无锁保护 | `redis.py` | PRF-02 |
| 15 | N+1 查询模式 | `asset_service.py` | PRF-04 |
| 16 | 使用 print() 而非结构化日志 | `main.py`, `seed_data.py` | MNT-01 |
| 17 | JWT sub 字段类型不安全 | `deps.py` | SEC-07 |
| 18 | CORS 配置过于宽松 | `main.py` | SEC-08 |

### P2 - 建议改进

| # | 问题 | 位置 | 检查项 |
|---|------|------|--------|
| 1 | 行情数据未使用 Redis 缓存 | `exchange_adapter.py` | PRF-05 |
| 2 | 硬编码 initial_capital = 100000 | `asset_service.py` | MNT-04 |
| 3 | 回测 session 依赖注入不规范 | `backtest.py` | ARC-05 |
| 4 | Token refresh 创建新 Dio 实例 | `api_client.dart` | ARC-04 |
| 5 | 缺少 .env.example | 项目根目录 | SEC-02 |

---

## 10. 附录：审查 Checklist 速查表

### 快速审查表（每个 PR 必过）

- [ ] **安全**：无硬编码密钥，新增端点有认证，金融数值有校验
- [ ] **正确**：Model 字段与 Service 一致，金融计算用 Decimal，无逻辑错误
- [ ] **架构**：无重复代码，分层合规，依赖注入规范
- [ ] **可维护**：无 print()，类型注解完整，复杂逻辑有注释
- [ ] **性能**：无 N+1 查询，HTTP 客户端复用，高频数据有缓存
- [ ] **测试**：核心逻辑有单元测试，新增 API 有集成测试

### 金融域专项审查表

- [ ] 金额计算全部使用 `Decimal`
- [ ] 买卖方向无反转风险
- [ ] 止损/止盈逻辑正确
- [ ] 交易所 API 字段映射已验证
- [ ] 资产余额计算逻辑正确
- [ ] 订单状态机转换完整
- [ ] 回测结果基于真实数据

### 安全专项审查表

- [ ] 无硬编码密钥/凭证
- [ ] 所有业务端点有认证
- [ ] JWT Token 类型校验正确
- [ ] CORS 配置最小化
- [ ] API Key 加密存储
- [ ] 无 SQL 注入风险
- [ ] 敏感信息不出现在日志中

---

## 修订记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-04-21 | 1.0 | 初始版本，基于全量代码审计结果制定 |
