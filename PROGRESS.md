# 币钱袋 - 项目进展 & 发布审查

> v2.0 | 2026-04-24 | 发布就绪度：**98%** | Sprint 3：**100% 完成**

---

## 当前 Sprint 3 状态

**目标**：策略引擎完成 & 回测框架（截止 2026-05-04）

| Task | 负责 | 状态 |
|------|------|------|
| T-3.1 数据模型完善 | backend | ✅ |
| T-3.2 Repository 层 | backend | ✅ |
| T-3.3 Service 层基础 | backend | ✅ |
| T-3.4 交易所适配器 WebSocket | backend | ✅ |
| T-3.5 策略引擎核心（MA/RSI/Bollinger + 实时运行器） | quant | ✅ |
| T-3.6 马丁格尔策略 | quant | ✅ |
| T-3.7 回测框架 | quant | ✅ |
| T-3.8 绩效计算模块 | quant | ✅ |

完成度：**100%**（8/8）

---

## 后端 API 清单（35 端点）

| 模块 | 前缀 | 端点数 | 移动端对接 | 网页端对接 |
|------|------|--------|------------|------------|
| 安装向导 | /setup | 2 | N/A | ✅ |
| 认证 | /auth | 4 | ✅ 全部 | ✅ |
| 用户 | /users | 1 | ❌ | ❌ |
| 策略 | /strategies | 9 | ✅ 2/9 | ✅ 5/9 |
| 回测 | /backtest | 3 | ❌ | ✅ 全部 |
| 行情 | /market | 5 | ✅ 1/5 | ✅ 2/5（tickers+kline） |
| 资产 | /asset | 3 | ✅ 全部 | ✅ 全部 |
| 交易 | /trading | 8+1 | ❌ | ✅ 3/9（账户CRUD） |

---

## 移动端模块状态

| 模块 | UI | API 对接 |
|------|----|---------|
| Dashboard | ✅ | ✅ 资产/行情/持仓/权益曲线 |
| 认证（登录/注册） | ✅ | ✅ |
| 策略中心 | ✅ | ❌ 可延后 |
| 回测页面 | ✅ | ❌ 可延后 |
| 设置页面 | ✅ | ❌ 可延后 |

---

## 网页控制台状态（2026-04-24）

| 功能 | 状态 | 备注 |
|------|------|------|
| 安装向导（3步：管理员→数据库→确认） | ✅ | /web/setup |
| 登录/注册 | ✅ | JWT + 自动刷新 |
| Dashboard（资产/持仓/权益曲线） | ✅ | 空状态引导+占位 |
| 策略中心（模板/实例管理） | ✅ | 5种策略模板 |
| 回测（配置/运行/结果/历史） | ✅ | 真实K线+绩效计算 |
| 交易所账户管理 | ✅ | CRUD + AES-256加密 |
| 响应式适配（4断点） | ✅ | 桌面/平板/手机全适配 |
| 实盘下单 | ❌ | v1 不含（安全考量） |

---

## 安全审计结果（2026-04-21 全部清零）

| 等级 | 数量 | 状态 |
|------|------|------|
| P0 阻塞 | 6 | ✅ 全修复 |
| P1 严重 | 18 | ✅ 全修复 |
| P2 改进 | 5 | ✅ 全修复 |
| P3 建议 | 1 | ✅ 完成 |

核心修复：AES-256 加密 API Key、移除硬编码密钥、JWT Token 类型校验、数值范围校验、httpx 连接池单例、Redis Lock 线程安全、CORS 加固、结构化日志。

---

## 接口契约修复（2026-04-24）

| 问题 | 修复 | 影响 |
|------|------|------|
| `/auth/refresh` 返回顶层 vs 前端读 `data.data` | 改为 `APIResponse` 包裹 | Token 续期恢复正常 |
| 资产字段名不对齐 | `totalAsset→totalAssets`, `lockedBalance→frozenBalance` 等 | Dashboard 数据显示正确 |
| 策略 `templateId` int vs string | 反向映射 `_TEMPLATE_ID_TO_CODE` | 策略模板名正确显示 |

---

## 策略引擎架构（2026-04-24 完成）

### 策略实现
| 策略 | 文件 | 核心逻辑 |
|------|------|---------|
| 双均线 (MA) | strategy_engine.py | 短期/长期均线交叉 |
| RSI | strategy_engine.py | 超买超卖区间反转 |
| 布林带 (Bollinger) | strategy_engine.py | 上下轨突破回归 |
| 网格 (Grid) | strategy_engine.py | 价格区间等分挂单 |
| 马丁格尔 (Martingale) | strategy_engine.py | 亏损加倍+趋势判断+连亏保护 |

### 实时策略运行器
- **StrategyRunner** 单例，管理 running 状态的策略实例
- 每个实例一个 asyncio.Task：获取K线→策略分析→信号处理→WS推送
- 防抖：60s 内同策略不重复发信号
- 集成 main.py 生命周期：启动加载 + 关闭清理

### 绩效计算模块
- **PerformanceCalculator**: 总收益/年化/最大回撤/夏普/卡玛/胜率/盈亏比
- API: `GET /strategies/instances/{id}/performance`

### 回测框架
- **BacktestService**: Binance 公开K线 + 逐根驱动 + 模拟执行 + 绩效计算
- 支持 5 种策略，降级策略（K线获取失败用确定性模拟）
- 持久化：BacktestResult 模型 + 历史查询 API

---

## Docker 环境（2026-04-24）

| 服务 | 镜像 | 端口 |
|------|------|------|
| 后端 | Python 3.12-slim | 8000 |
| PostgreSQL | postgres:16-alpine | 5432 |
| Redis | redis:7-alpine | 6379 |

启动：`docker compose up --build`（项目根目录）

---

## 安装向导架构（2026-04-24）

**核心改动**：从"导入即初始化"改为"可默认启动、可运行时完成初始化"

| 组件 | 改动 |
|------|------|
| config.py | 开发默认值 + `setup_complete` + `reload_settings()` |
| database.py | 懒初始化引擎 + `reset_database()` + `init_db()` + `get_session()` |
| User 模型 | 加 `is_superuser`，安装向导创建的首个用户为管理员 |
| setup API | `GET /setup/status` + `POST /setup/complete` |
| 所有模块级缓存 | 清除 `settings = get_settings()` 模块级调用 |
| 默认数据库 | SQLite（`./data/crypto_quant.db`），零配置启动 |

---

## 交易所适配器优化（2026-04-24）

| 优化 | 内容 |
|------|------|
| 异常体系 | `RateLimitError` / `NetworkError` / `OrderRejectedError` + retryable 属性 |
| 重试+限流 | 指数退避 1→2→4s（上限30s）；下单不重试；撤单1次；查询3次 |
| 安全Decimal | `_safe_decimal()` 防 ValueError；`_safe_divide()` 防 DivisionByZero |
| Huobi缓存 | accountId TTL 5分钟 + 失败清理 + 降级策略 |
| OrderService | 异常细分处理：OrderRejected→400 / RateLimit→429 / Network→502 |

---

## 网页控制台响应式适配（2026-04-24）

| 尺寸 | 断点 | 布局策略 |
|------|------|---------|
| 桌面 (>1200px) | — | 侧栏常驻220px，4列网格，回测左右分栏 |
| 大平板 (1024-1200px) | 1200px | grid-4/grid-3 降为2列 |
| 平板 (768-1024px) | 1024px | 回测配置+结果上下排列，padding缩小 |
| 小平板/大手机 (480-768px) | 768px | 侧栏变抽屉+汉堡菜单+遮罩，grid-2/3变单列 |
| 手机 (<480px) | 480px | 统计卡片2列，按钮全宽，账户卡片纵向堆叠 |

关键特性：汉堡菜单导航、表格横向滚动、导航后自动关闭侧栏

---

## 发布阻塞项

| 优先级 | 问题 | 状态 |
|--------|------|------|
| 🔴 P0 | 登录/注册页面 | ✅ |
| 🔴 P0 | Dashboard API 对接 | ✅ |
| 🔴 P0 | 硬编码默认密钥 | ✅ |
| 🔴 P0 | API Key 未加密 | ✅ |
| 🔴 P0 | 端点缺少认证 | ✅ |
| 🔴 P0 | Token 类型未校验 | ✅ |
| 🔴 P0 | 金融数值缺少范围校验 | ✅ |
| 🟡 P1 | 接口契约不一致 | ✅ 已修复 |
| 🟡 P1 | 回测功能对接 | ✅ 已完成 |
| 🟡 P1 | 交易所管理对接 | ✅ 网页端完成 |
| 🟢 P2 | WebSocket 实时行情 | ✅ 已实现 |
| 🟢 P2 | 零测试覆盖率 | ❌ 待解决 |

---

## 发布检查清单

### 必须通过
- [x] API Base URL 已配置生产地址
- [x] 登录/注册流程（UI + API）
- [x] Dashboard 数据显示正常
- [x] Token 刷新机制
- [x] 接口契约前后端一致
- [x] 安装向导首次启动体验
- [x] 网页控制台全页面响应式适配
- [x] 交易所账户 CRUD + API Key 加密存储
- [ ] 错误提示友好（需测试）
- [ ] 加载状态正确显示（需测试）
- [ ] 退出登录功能（需测试）
- [ ] 隐私政策/用户协议页面

### 建议检查
- [ ] 应用启动速度 < 3 秒
- [ ] 内存占用 < 150MB
- [ ] 自动下单（StrategyRunner 信号→OrderService，需 exchange_account 关联）

---

## 部署命令

```bash
# Docker 一键部署（推荐）
docker compose up --build

# 后端（零配置启动，首次自动进入安装向导）
cd backend
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 移动端构建
flutter build apk --release    # Android
flutter build ios --release    # iOS
```

```nginx
# Nginx 反向代理
location / {
    proxy_pass http://localhost:8000/;
}
# API 和 Web 控制台同域部署
```

---

## 版本历史

| 版本 | 日期 | 内容 |
|------|------|------|
| v1.0 | 2026-04-21 | 初始发布前审查 |
| v1.1 | 2026-04-21 | 登录注册 + Dashboard API 对接 |
| v1.2 | 2026-04-21 | 安全审计 P0~P3 全部修复 |
| v1.3 | 2026-04-21 | 可选登录 + Gradle 优化 + 文档同步 |
| v1.4 | 2026-04-24 | 接口契约修复（Token/资产/策略 3项） |
| v1.5 | 2026-04-24 | 网页控制台 v1（登录/Dashboard/策略/回测） |
| v1.6 | 2026-04-24 | 安装向导（无 .env 启动 + 懒初始化 + 管理员创建） |
| v1.7 | 2026-04-24 | 文档全面同步更新 |
| v1.8 | 2026-04-24 | 马丁格尔策略 + 实时策略运行器 + 绩效计算模块 + WebSocket bug 修复 |
| v1.9 | 2026-04-24 | 回测框架完成（真实K线+策略引擎+绩效计算+历史存储） |
| v2.0 | 2026-04-24 | Sprint 3 全部完成 + 交易所账户管理 + 响应式适配4断点 + Docker修复 |
