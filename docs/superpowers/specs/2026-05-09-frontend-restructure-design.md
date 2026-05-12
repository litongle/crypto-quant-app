# 前端形态重组（自用版量化平台）实现规格

> 平台定位：**自用单人量化交易平台**。当前前端是"产品味交易终端 + 8 项侧栏 + 手动下单 UI"，与定位错位。本 spec 把它重构为"自动化策略平台"形态：4 项侧栏 + 控制台四块布局 + 抽屉式实例详情，并砍除手动下单 UI 与冗余独立页。
>
> **与并行 spec 的关系**：`2026-05-09-strategy-auto-pause-design.md`（自停告警）正在 codex 落地。本 spec **无前端冲突**——前者是后端 + settings + 测试，本 spec 仅前端 + 后端路由删除 + 2 个新查询端点。可并行进行；如自停 spec 引入的 5 个 settings 已落地，本 spec §3.3.4 的"风控参数 tab"会显示它们的当前值。

## 0. 一句话目标

把当前 8 项侧栏 + `#page-trading` + `#page-market` + 4 个独立账户/安全/模拟盘页 重构为：**4 项侧栏（控制台/策略/回测/事件流）+ 右上角设置抽屉 + 控制台四块布局 + 策略实例右侧抽屉**。同步删除所有手动下单端点和前端代码。

## 1. 现状快照（不要修改的事实）

### 1.1 当前侧栏结构（`backend/app/web/static/index.html:138-198`）

```
[控制台]   ▸ dashboard, strategy, backtest    (行 142,148,154)
[账户]     ▸ accounts, paper, security        (行 164,170,176)
[交易]     ▸ market, trading                  (行 186,192)
```

每项 nav 用 `<div class="sidebar-nav-item" onclick="navigate('xxx')" data-page="xxx">`。

### 1.2 8 个 page-view 块

| ID | `index.html` 行号 | 用途 | 决议 |
|---|---|---|---|
| `#page-dashboard` | 214–253 | 资产汇总 + 权益 + 持仓 + 风险驾驶舱 | **重写** |
| `#page-strategy` | 256–353 | 策略中心 | **保留**（不动） |
| `#page-backtest` | 354–411 | 回测 | **保留**（不动） |
| `#page-accounts` | 412–420 | 交易所账户列表 | **删除**，内容迁入设置抽屉 |
| `#page-paper` | 423–429 | 模拟盘账户 | **删除**，内容迁入设置抽屉 |
| `#page-security` | 432–438 | 2FA + 审计日志 | **删除**，内容迁入设置抽屉 |
| `#page-market` | 441–489 | K 线 + orderbook | **删除**，K 线挪到实例抽屉 |
| `#page-trading` | 492–624 | 手动下单（pair browser + 下单 form + 持仓 tabs + orderbook） | **删除** |

附属弹窗：
- `#sltp-dialog`（行 627–650）：手动止盈止损弹窗，**删除**
- `#strategy-perf-modal`（行 653–663）：策略绩效，**保留**
- `#danger-confirm-dialog`（行 669+）：通用危险操作确认，**保留**

### 1.3 路由调度核心

`navigate(page, pushHash=true)` 函数定义在 `index.html:806-846`：
- 行 815–816：通过 `.page-view.active` / `.sidebar-nav-item.active` 切页
- 行 833–834：离开页面时清理 `stopMarketWs()` / `stopTradingOrderbookPolling()`
- 行 836–843：switch-like 调度 `loadXxxPage()`

### 1.4 JS 文件资产（`backend/app/web/static/js/`）

| 文件 | 行数 | 入口函数 | 决议 |
|---|---|---|---|
| `dashboard.js` | 479 | `loadDashboard()` | **重写** |
| `strategy.js` | 1664 | `loadStrategyPage()` | **保留** |
| `backtest.js` | 901 | `loadBacktestPage()` | **保留** |
| `api.js` | 492 | `Api` 类 | **改造**（删 trading 订单方法） |
| `accounts.js` | 427 | `loadAccountsPage()`（行 21）+ `renderAccounts()`（行 34） | **改造**入口 |
| `security.js` | 332 | `loadSecurityPage()`（行 69）+ `renderSecurityPage()`（行 111） | **改造**入口 |
| `paper.js` | 107 | `loadPaperPage()`（行 5）+ `renderPaperPage()`（行 20） | **改造**入口 |
| `market.js` | 948 | `loadMarketPage()`（行 125） + K 线渲染等 | **删除**（K 线渲染抽到 `kline.js`） |
| `trading.js` | 1171 | `loadTradingPage()`（行 21） | **删除** |
| `symbol-selector.js` | 449 | `SymbolSelector` 类 | **保留**（策略中心也用） |

### 1.5 后端路由（`backend/app/api/v1/__init__.py`）

```python
api_router.include_router(setup.router,    prefix="/setup",      tags=["安装向导"])
api_router.include_router(auth.router,     prefix="/auth",       tags=["认证"])
api_router.include_router(users.router,    prefix="/users",      tags=["用户"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["策略"])
api_router.include_router(backtest.router, prefix="/backtest",   tags=["回测"])
api_router.include_router(market.router,   prefix="/market",     tags=["行情"])
api_router.include_router(asset.router,    prefix="/asset",      tags=["资产"])
api_router.include_router(orders.router,   prefix="/trading",    tags=["交易"])
api_router.include_router(ws.router,       prefix="/ws",         tags=["WebSocket"])
```

`orders.py` 含 17 个端点：
- **删除**（手动下单）：
  - `POST /trading` 创建订单（行 319–368）
  - `GET /trading` 订单列表（行 370–387）
  - `POST /trading/{order_id}/cancel`（行 389–400）
  - `POST /trading/{position_id}/stop-loss`（行 402–418）
  - `POST /trading/{position_id}/take-profit`（行 420–444）
  - `POST /trading/{position_id}/close`（行 446–end of handler）
  - `POST /trading/emergency-close-all`（行 222–244）
- **保留**（账户管理 + 持仓查询，策略需要）：
  - `GET /trading/accounts`（行 102）
  - `POST /trading/accounts`（行 116）
  - `GET /trading/accounts/{account_id}`（行 152）
  - `POST /trading/accounts/{account_id}/sync`（行 171）
  - `DELETE /trading/accounts/{account_id}`（行 195）
  - `GET /trading/positions`（行 246）
  - `GET /trading/symbol-rules`（行 260）
  - `GET /trading/accounts/{account_id}/contract-settings`（行 277）
  - `POST /trading/accounts/{account_id}/contract-settings`（行 294）

### 1.6 CSS 关键区段（`backend/app/web/static/css/app.css`）

| 行 | 类名 | 决议 |
|---|---|---|
| 2089–2238 | `cq-market-orderbook-*` | **删除**（市场页和 trading 页都用，两者都被砍） |
| 2300–2745 | `cq-trading-*` | **删除** |

`market.py` 后端路由 **保留**——策略 runner 需要拉行情。仅前端市场页废弃。

## 2. 目标形态

### 2.1 侧栏（4 项扁平结构）

砍掉"账户"和"交易"两个 sidebar group，全部扁平：

```
▸ 控制台  (dashboard, 默认页)
▸ 策略    (strategy)
▸ 回测    (backtest)
▸ 事件流  (events) ← 新增
```

### 2.2 顶部 Header 改造

`index.html:104-132`：
- **删除** `:120-122` 的"交易所账户"快捷按钮（旧入口，迁入设置）
- **新增** 齿轮按钮触发设置抽屉（位置：原账户按钮位置）

### 2.3 控制台首页（重写 `#page-dashboard`）

四块布局：

```
┌────────────────────────────────────────────────────────────┐
│  [块A] 策略实例列表（全宽）                                  │
│  ●  BTC RSI分层    running   PnL +234U   80ms   [暂停]      │
│  ◐  ETH DCA        paused    auto: heartbeat_timeout       │
│  ●  SOL momentum   running   PnL  +12U   65ms   [暂停]      │
│  ○  ARB grid       stopped   累计 +1240U          [恢复]    │
│  → 点击行：打开实例抽屉                                      │
├──────────────────────────────┬─────────────────────────────┤
│  [块B] 实时活动流（最近 50）   │  [块C] 权益曲线（30 天）     │
│  13:42 BTC 开多 50U @ 64200  │  ▁▂▃▅▆▇▆▅▆▇▆▇                │
│  13:39 ETH 平仓 +12.4U       │  +1.42% (30d)               │
│  13:35 RSI 信号 BTCUSDT      │                             │
├──────────────────────────────┼─────────────────────────────┤
│  [块D] 风险事件 24h           │  [块E] 系统状态              │
│  ⚠ 14:01 ETH 连续 3 笔下单    │  Binance Fut  ●  12ms       │
│    失败 → auto:order_failures │  OKX          ●  25ms       │
│                              │  Runner       ● 4/4 ok      │
└──────────────────────────────┴─────────────────────────────┘
```

数据源（**全部走已有 + §2.6 §2.7 新增的 2 个端点**，本 spec 不引入新表）：
- 块A：`GET /strategies/instances`（已有）
- 块B：`GET /events?limit=50`（§2.6 新增）
- 块C：复用现有 `equityChart` 渲染逻辑
- 块D：`GET /events?event_type=risk&since=24h`（§2.6 新增）
- 块E：`GET /strategies/runner/status`（§2.7 新增）

### 2.4 设置抽屉（新增 `<aside id="settings-drawer">`）

挂载位置：`index.html` 中 `</main>` 之后（即 `:665` 之后），与 `#instance-drawer` 同级。

骨架（**不要改类名**，CSS 依赖）：

```html
<aside class="cq-drawer cq-drawer--right" id="settings-drawer" hidden>
  <div class="cq-drawer__overlay" onclick="closeSettingsDrawer()"></div>
  <div class="cq-drawer__panel">
    <div class="cq-drawer__header">
      <h2>设置</h2>
      <button class="cq-icon-btn" onclick="closeSettingsDrawer()" aria-label="关闭">✕</button>
    </div>
    <nav class="cq-drawer__tabs" role="tablist">
      <button class="cq-drawer__tab is-active" data-settings-tab="accounts" onclick="switchSettingsTab('accounts')">交易所账户</button>
      <button class="cq-drawer__tab" data-settings-tab="paper" onclick="switchSettingsTab('paper')">模拟盘</button>
      <button class="cq-drawer__tab" data-settings-tab="notifications" onclick="switchSettingsTab('notifications')">通知通道</button>
      <button class="cq-drawer__tab" data-settings-tab="risk" onclick="switchSettingsTab('risk')">风控参数</button>
      <button class="cq-drawer__tab" data-settings-tab="security" onclick="switchSettingsTab('security')">安全</button>
    </nav>
    <div class="cq-drawer__body">
      <div class="cq-settings-pane is-active" data-settings-pane="accounts" id="settings-pane-accounts"></div>
      <div class="cq-settings-pane" data-settings-pane="paper" id="settings-pane-paper" hidden></div>
      <div class="cq-settings-pane" data-settings-pane="notifications" id="settings-pane-notifications" hidden></div>
      <div class="cq-settings-pane" data-settings-pane="risk" id="settings-pane-risk" hidden></div>
      <div class="cq-settings-pane" data-settings-pane="security" id="settings-pane-security" hidden></div>
    </div>
  </div>
</aside>
```

5 个子 tab 内容来源：

| Tab | 内容 | 实现 |
|---|---|---|
| accounts | 交易所账户列表 + 增删 | `accounts.js: renderAccountsPane('#settings-pane-accounts')` |
| paper | 模拟盘重置/查看 | `paper.js: renderPaperPane('#settings-pane-paper')` |
| notifications | Telegram bot token / chat id 当前值（read-only） + 提示编辑 `.env` 后重启 | `settings-drawer.js` 内联 |
| risk | 显示自停 spec 引入的 5 个 `auto_pause_*` 配置（read-only） | `settings-drawer.js` 内联 |
| security | 2FA + 审计日志 | `security.js: renderSecurityPane('#settings-pane-security')` |

### 2.5 策略实例抽屉（新增 `<aside id="instance-drawer">`）

挂载位置：`index.html` 中 `</main>` 之前（即 `:665` 内、`#strategy-perf-modal` 之后）。

骨架：

```html
<aside class="cq-drawer cq-drawer--right" id="instance-drawer" hidden>
  <div class="cq-drawer__overlay" onclick="closeInstanceDrawer()"></div>
  <div class="cq-drawer__panel">
    <div class="cq-drawer__header">
      <span id="instance-drawer-title">--</span>
      <button class="cq-icon-btn" onclick="closeInstanceDrawer()" aria-label="关闭">✕</button>
    </div>
    <div class="cq-drawer__body">
      <section class="cq-instance-summary" id="instance-drawer-summary"></section>
      <details class="cq-instance-kline">
        <summary>K 线（点击展开）</summary>
        <div id="instance-drawer-kline-wrap" style="height:320px;"></div>
      </details>
      <section class="cq-instance-positions" id="instance-drawer-positions"></section>
      <section class="cq-instance-orders" id="instance-drawer-orders"></section>
      <div class="cq-instance-actions">
        <button class="cq-btn cq-btn--secondary" onclick="instanceDrawerPause()">暂停</button>
        <button class="cq-btn cq-btn--secondary" onclick="instanceDrawerStop()">停止</button>
        <button class="cq-btn cq-btn--primary" onclick="instanceDrawerViewLogs()">查看完整日志</button>
      </div>
    </div>
  </div>
</aside>
```

行为约束：
- 抽屉不做路由（不写入 URL hash）
- 关闭即销毁所有子组件 state（K 线 chart 实例必须 destroy）
- K 线默认折叠（`<details>` 不带 `open` 属性）

### 2.6 事件流页 + 后端 `/events` 路由

新增前端页 `#page-events`（结构骨架在 §3.1）+ 新增后端路由 `app/api/v1/events.py`：

```python
# backend/app/api/v1/events.py
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User

router = APIRouter()

@router.get("")
async def list_events(
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    event_type: str | None = Query(None, regex="^(signal|order|risk|auto_pause|error)$"),
    instance_id: int | None = Query(None),
    q: str | None = Query(None, max_length=200),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """聚合事件列表。

    数据源（v1）：
    - audit_log 表 → type=audit
    - strategy_signal 表 → type=signal
    - 持仓变动（从 audit_log 中过滤动作） → type=order
    - StrategyInstance.last_pause_reason 非空 + last_stopped_at within window → type=auto_pause
    - error 事件：从 audit_log 中过滤 status=error
    
    返回 { "total": int, "items": [...], "limit": int, "offset": int }
    每个 item 字段: id (str, 形如 "audit:123" 或 "signal:456"), at (ISO timestamp),
    type (str), instance_id (int|null), summary (str, ≤200 字), detail (dict, optional)
    """
    # codex 实现具体 SQL union 聚合 + 过滤 + 分页
    ...
```

注册到 `app/api/v1/__init__.py`：
```python
from app.api.v1 import events
api_router.include_router(events.router, prefix="/events", tags=["事件"])
```

### 2.7 Runner 状态端点

在 `app/api/v1/strategies.py` 末尾（行 597 之后）追加：

```python
@router.get("/runner/status")
async def get_runner_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """返回 strategy_runner 单例状态 + 各交易所 REST 健康。"""
    from app.core.strategy_runner import strategy_runner
    
    instance_tasks = {
        iid: not task.done()
        for iid, task in strategy_runner._tasks.items()  # 复用现有内部 dict
    }
    runner_block = {
        "running": strategy_runner._running,
        "task_count": len(instance_tasks),
        "alive_count": sum(1 for v in instance_tasks.values() if v),
        "last_heartbeat": getattr(strategy_runner, "_last_heartbeat", None),
    }
    
    # 各交易所健康：复用 app.core.exchanges.* 的 ping
    exchanges = []
    for ex_name in ("binance", "okx", "huobi"):
        try:
            from app.core.exchanges import get_exchange_client
            client = get_exchange_client(ex_name)
            t0 = time.monotonic()
            await client.ping()
            latency_ms = int((time.monotonic() - t0) * 1000)
            exchanges.append({"name": ex_name, "ws_connected": True, "rest_latency_ms": latency_ms})
        except Exception as e:
            exchanges.append({"name": ex_name, "ws_connected": False, "rest_latency_ms": None, "error": str(e)[:80]})
    
    return {"strategy_runner": runner_block, "exchanges": exchanges}
```

**注意**：`strategy_runner._tasks` / `_running` 等内部字段如果命名不一致，codex 应读 `backend/app/core/strategy_runner.py` 实际名字，不要瞎猜。

## 3. 变更点 by 文件

### 3.1 `backend/app/web/static/index.html`

| 行 | 操作 | 内容 |
|---|---|---|
| 120–122 | **删除** | 旧"交易所账户"快捷按钮 |
| 122 后 | **新增** | 齿轮按钮 `<button class="cq-icon-btn" onclick="openSettingsDrawer()" title="设置" aria-label="设置"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg></button>` |
| 162–198 | **删除** | "账户" + "交易"两个 `sidebar-section` 整块 |
| 159 后 | **新增** | 第 4 个 nav item（事件流，复用 svg 简洁图标）：`<div class="sidebar-nav-item" onclick="navigate('events')" data-page="events"><span class="sidebar-icon-container"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg></span><span class="sidebar-nav-text">事件流</span></div>` |
| 214–253 | **重写** | `#page-dashboard` 改为四块布局（DOM 骨架见 §3.1.1） |
| 412–420 | **删除** | `#page-accounts` 整块 |
| 423–429 | **删除** | `#page-paper` 整块 |
| 432–438 | **删除** | `#page-security` 整块 |
| 441–489 | **删除** | `#page-market` 整块 |
| 491–624 | **删除** | `#page-trading` 整块 |
| 624 后 | **新增** | `#page-events` 整块（DOM 骨架见 §3.1.2） |
| 626–650 | **删除** | `#sltp-dialog` 整块 |
| 663 后 | **新增** | `<aside id="instance-drawer">`（骨架见 §2.5） |
| 665 后 | **新增** | `<aside id="settings-drawer">`（骨架见 §2.4） |
| 806–846 | **改造** | `navigate()` 内部见 §3.1.3 |

#### 3.1.1 `#page-dashboard` 新 DOM 骨架

```html
<div class="page-view" id="page-dashboard">
  <div class="page-header">
    <h1>控制台</h1>
    <div class="sub">策略实例 / 实时活动 / 风险事件 / 系统状态</div>
  </div>

  <!-- 块 A: 策略实例 -->
  <div class="cq-card" style="margin-bottom:var(--cq-space-5);">
    <div class="cq-section-title"><h3>策略实例</h3></div>
    <div id="dashboard-instance-list"></div>
  </div>

  <!-- 块 B + 块 C: 活动流 + 权益曲线 -->
  <div class="cq-grid-2" style="margin-bottom:var(--cq-space-5);">
    <div class="cq-card">
      <div class="cq-section-title">
        <h3>实时活动</h3>
        <span class="cq-section-meta">最近 50 条</span>
      </div>
      <div id="dashboard-activity-stream"></div>
    </div>
    <div class="cq-card">
      <div class="cq-section-title">
        <h3>权益曲线</h3>
        <div class="cq-day-pills">
          <button class="cq-day-pill" data-days="7" onclick="changeEquityDays(7)">7天</button>
          <button class="cq-day-pill is-active" data-days="30" onclick="changeEquityDays(30)">30天</button>
          <button class="cq-day-pill" data-days="90" onclick="changeEquityDays(90)">90天</button>
        </div>
      </div>
      <div id="equityChart" style="position:relative;height:220px;width:100%;"></div>
    </div>
  </div>

  <!-- 块 D + 块 E: 风险事件 + 系统状态 -->
  <div class="cq-grid-2">
    <div class="cq-card">
      <div class="cq-section-title">
        <h3>风险事件</h3>
        <span class="cq-section-meta">最近 24 小时</span>
      </div>
      <div id="dashboard-risk-events"></div>
    </div>
    <div class="cq-card">
      <div class="cq-section-title">
        <h3>系统状态</h3>
      </div>
      <div id="dashboard-system-status"></div>
    </div>
  </div>
</div>
```

#### 3.1.2 `#page-events` DOM 骨架

```html
<div class="page-view cq-constrained" id="page-events">
  <div class="page-header">
    <h1>事件流</h1>
    <div class="sub">所有平台事件，可搜索可过滤</div>
  </div>
  <div class="cq-card" style="margin-bottom:var(--cq-space-4);">
    <div class="cq-event-filters">
      <select id="events-filter-type" onchange="reloadEvents()">
        <option value="">全部类型</option>
        <option value="signal">信号</option>
        <option value="order">订单</option>
        <option value="risk">风险</option>
        <option value="auto_pause">自停</option>
        <option value="error">错误</option>
      </select>
      <select id="events-filter-since" onchange="reloadEvents()">
        <option value="1h">最近 1 小时</option>
        <option value="24h" selected>最近 24 小时</option>
        <option value="7d">最近 7 天</option>
        <option value="30d">最近 30 天</option>
      </select>
      <input type="search" id="events-filter-q" placeholder="搜索关键字..." onkeyup="if(event.key==='Enter')reloadEvents()">
      <button class="cq-btn cq-btn--secondary" onclick="reloadEvents()">刷新</button>
    </div>
  </div>
  <div class="cq-card">
    <div id="events-list"></div>
    <div class="cq-event-pagination" id="events-pagination"></div>
  </div>
</div>
```

#### 3.1.3 `navigate()` 改造（行 806–846）

精确改动：
- 行 833 `if (page !== 'market') stopMarketWs();` → **删除**
- 行 834 `if (page !== 'trading' && typeof stopTradingOrderbookPolling === 'function') stopTradingOrderbookPolling();` → **删除**
- 行 836–843 switch 改为：

```js
if (page === 'dashboard') loadDashboard();
else if (page === 'strategy') loadStrategyPage();
else if (page === 'backtest') loadBacktestPage();
else if (page === 'events') loadEventsPage();
else { // 老 hash 兜底：market/trading/paper/security/accounts → dashboard
  await navigate('dashboard', false);
  return false;
}
```

### 3.2 `backend/app/web/static/js/dashboard.js`

整文件**重写**（保留权益曲线相关函数迁移）。新结构：

```js
// 全局状态
let _dashboardRefreshTimer = null;
const DASHBOARD_REFRESH_INTERVAL_MS = 5000;

async function loadDashboard() {
  await Promise.all([
    renderInstanceList(),
    renderActivityStream(),
    renderEquityChart(),     // 复用旧逻辑（搬过来）
    renderRiskEvents(),
    renderSystemStatus(),
  ]);
  startDashboardAutoRefresh();
}

function startDashboardAutoRefresh() { /* setInterval refresh blocks B/D/E */ }
function stopDashboardAutoRefresh() { /* clearInterval */ }

async function renderInstanceList() {
  const target = document.getElementById('dashboard-instance-list');
  const instances = await api.listInstances();  // 已有
  // 渲染表格行：● status / name / params summary / pnl / latency / [暂停/恢复] btn
  // 行点击 → openInstanceDrawer(instance.id)
}

async function renderActivityStream() {
  const target = document.getElementById('dashboard-activity-stream');
  const { items } = await api.getEvents({ limit: 50 });
  // 渲染时间倒序列表
}

async function renderEquityChart(days = 30) { /* 复用旧 dashboard.js 的逻辑 */ }
function changeEquityDays(days) { /* 复用旧 */ }

async function renderRiskEvents() {
  const target = document.getElementById('dashboard-risk-events');
  const { items } = await api.getEvents({ event_type: 'risk', since: '24h', limit: 20 });
  // 渲染高亮卡片
}

async function renderSystemStatus() {
  const target = document.getElementById('dashboard-system-status');
  const status = await api.getRunnerStatus();
  // 渲染：runner block + 各 exchange 行
}
```

**删除**：旧 `loadDashboard()` 中的资产汇总卡 / 持仓 section / 风险驾驶舱渲染相关函数（如 `renderAssetSummary`、`renderPositionSection`、`renderRiskDashboard` 等）。这些功能在新结构中由 `renderInstanceList` + `renderRiskEvents` 替代。

### 3.3 `backend/app/web/static/js/api.js`

| 行 | 操作 |
|---|---|
| 322–342 | **保留**（`getAccounts/createAccount/getAccount/syncAccount/deleteAccount`） |
| 351–353 (`createOrder` 起) – 431 (`emergencyCloseAll` 末) | **删除整段**：包括 `createOrder` / `getOrders` / `cancelOrder` / `getPositions` / `getSymbolRules` / `getContractSettings` / `updateContractSettings` / `setStopLoss` / `setTakeProfit` / `closePosition` / `emergencyCloseAll` 共 11 个方法 |
| 文末 | **新增** 2 个方法： |

```js
async getEvents({ event_type, since, until, instance_id, q, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (event_type) params.set('event_type', event_type);
  if (since) params.set('since', resolveSinceParam(since)); // '24h' → ISO timestamp
  if (until) params.set('until', until);
  if (instance_id) params.set('instance_id', instance_id);
  if (q) params.set('q', q);
  params.set('limit', limit);
  params.set('offset', offset);
  return await this.get(`/events?${params}`);
}

async getRunnerStatus() {
  return await this.get('/strategies/runner/status');
}
```

辅助函数 `resolveSinceParam` 在 `api.js` 内 helper 区实现：'1h' → ISO timestamp of now-1h，'24h' → now-24h，'7d' → now-7d 等。

### 3.4 删除的文件

```
backend/app/web/static/js/trading.js   (1171 行)
backend/app/web/static/js/market.js    (948 行)
```

### 3.5 新增的文件

#### `backend/app/web/static/js/events.js`

入口与函数：
```js
let _eventsState = { type: '', since: '24h', q: '', offset: 0, limit: 50, total: 0 };

async function loadEventsPage() {
  // 初始化 + 渲染
  await reloadEvents();
}

async function reloadEvents() {
  // 读取 filters → 调 api.getEvents → 渲染表格 + 分页
}

function renderEventsTable(items) { /* 时间 / 类型 badge / 实例 / 摘要，行点击展开详情 JSON */ }
function renderEventsPagination(total, offset, limit) { /* 上一页/下一页/页码 */ }
function navigateToEventsForInstance(instanceId) { /* 跳到事件流页 + 预填 instance_id 过滤 */ }
```

#### `backend/app/web/static/js/settings-drawer.js`

```js
let _settingsCurrentTab = 'accounts';

function openSettingsDrawer(initialTab = 'accounts') {
  document.getElementById('settings-drawer').hidden = false;
  switchSettingsTab(initialTab);
}

function closeSettingsDrawer() {
  document.getElementById('settings-drawer').hidden = true;
}

async function switchSettingsTab(tab) {
  _settingsCurrentTab = tab;
  // 更新 .cq-drawer__tab.is-active class
  // 更新 .cq-settings-pane.is-active + hidden 切换
  // 调用对应渲染函数：
  if (tab === 'accounts') await renderAccountsPane('#settings-pane-accounts');
  else if (tab === 'paper') await renderPaperPane('#settings-pane-paper');
  else if (tab === 'security') await renderSecurityPane('#settings-pane-security');
  else if (tab === 'notifications') renderNotificationsPane('#settings-pane-notifications');
  else if (tab === 'risk') await renderRiskPane('#settings-pane-risk');
}

function renderNotificationsPane(selector) {
  // 内联实现：
  // 调 api.get('/setup/status') 或类似获取当前 telegram_bot_token / telegram_chat_id 是否已配置（不返回明文 token）
  // 渲染：状态标识 + "如需修改，编辑 backend/.env 后 docker compose restart backend" 提示
}

async function renderRiskPane(selector) {
  // 调 api.get('/setup/status') 或 settings 暴露端点（如无则 fetch 常量数组从后端 /strategies/runner/status 的 metadata）
  // 渲染 5 个 read-only 字段：
  //   auto_pause_consecutive_errors (默认 5)
  //   auto_pause_consecutive_order_failures (默认 3)
  //   auto_pause_heartbeat_multiplier (默认 5)
  //   auto_pause_heartbeat_min_seconds (默认 300)
  //   auto_pause_watchdog_interval_seconds (默认 30)
  // + 提示 "修改 .env 后重启容器生效"
}
```

#### `backend/app/web/static/js/instance-drawer.js`

```js
let _currentInstanceId = null;
let _instanceKlineChart = null;  // 复用 kline.js 返回的 chart 实例

async function openInstanceDrawer(instanceId) {
  _currentInstanceId = instanceId;
  document.getElementById('instance-drawer').hidden = false;
  await Promise.all([
    renderInstanceSummary(instanceId),
    renderInstancePositions(instanceId),
    renderInstanceOrders(instanceId),
  ]);
  // K 线 details 默认折叠，绑定 toggle 事件懒加载
  bindInstanceKlineLazyLoad();
}

function closeInstanceDrawer() {
  document.getElementById('instance-drawer').hidden = true;
  if (_instanceKlineChart) {
    _instanceKlineChart.destroy?.();
    _instanceKlineChart = null;
  }
  _currentInstanceId = null;
}

function bindInstanceKlineLazyLoad() {
  const det = document.querySelector('#instance-drawer .cq-instance-kline');
  det.addEventListener('toggle', async () => {
    if (det.open && !_instanceKlineChart) {
      const symbol = inferInstanceSymbol(_currentInstanceId);
      _instanceKlineChart = await renderKline('#instance-drawer-kline-wrap', { symbol, interval: '1h', exchange: 'binance' });
    }
  }, { once: false });
}

async function instanceDrawerPause() { await api.pauseInstance(_currentInstanceId); /* refresh */ }
async function instanceDrawerStop() { await api.stopInstance(_currentInstanceId); /* refresh */ }
function instanceDrawerViewLogs() { closeInstanceDrawer(); navigate('events'); navigateToEventsForInstance(_currentInstanceId); }
```

#### `backend/app/web/static/js/kline.js`

从原 `market.js` 抽出来的 K 线渲染。**核心要求**：参数化目标元素 + symbol + interval + exchange，**不依赖任何 `#market-*` ID**。

```js
async function renderKline(targetSelector, { symbol, interval = '1h', limit = 200, exchange = 'binance', market = 'spot' } = {}) {
  const data = await api.getKline(symbol, interval, limit, exchange, market);
  const target = typeof targetSelector === 'string' ? document.querySelector(targetSelector) : targetSelector;
  // 用 lightweight-charts (现有依赖) 渲染
  // 返回 chart 实例（含 destroy 方法）
  return chart;
}
```

#### `backend/app/api/v1/events.py`

骨架见 §2.6。完整实现量级参考 `backend/app/api/v1/market.py` 中的列表端点（约 100 行可完成）。

### 3.6 改造文件（保持职责）

#### `backend/app/web/static/js/accounts.js`

- 新增导出函数 `renderAccountsPane(targetSelector)`：把原 `loadAccountsPage()` 的逻辑提炼为接受 target selector 的版本（原来挂在 `#accounts-content`，新版挂在传入的 target）
- **保留** 原 `loadAccountsPage` 函数体，但内部改为 `return renderAccountsPane('#accounts-content')` 兼容包装层（虽然 `#accounts-content` 这次会被删除——但保留这个名字给其他可能的调用者无害）
- 实际上：`loadAccountsPage` 全局名引用已在 `navigate()` 中删除（§3.1.3），可以安全删除该函数

#### `backend/app/web/static/js/paper.js`

同上：`loadPaperPage` → `renderPaperPane(targetSelector)`，目标元素从 `#paper-content` 改为传入的 selector。

#### `backend/app/web/static/js/security.js`

同上：`loadSecurityPage` → `renderSecurityPane(targetSelector)`，目标元素从 `#security-content` 改为传入的 selector。

**注意**：security.js 内部还有 `load2faStatus` / `loadAuditLogs` / `loadMoreAuditLogs` 等函数，签名不变，只是 `renderSecurityPane` 在新 mount 点重新挂载 DOM。

### 3.7 后端

| 文件 | 操作 |
|---|---|
| `backend/app/api/v1/__init__.py` | 在 `orders` 后追加 `from app.api.v1 import events` 和 `api_router.include_router(events.router, prefix="/events", tags=["事件"])` |
| `backend/app/api/v1/orders.py` | 删除 §1.5 列出的 7 个手动下单端点 + 各自 import 中变成孤儿的 schema |
| `backend/app/api/v1/strategies.py` | 末尾追加 `GET /runner/status` endpoint（实现见 §2.7） |
| `backend/app/api/v1/events.py` | 新建（骨架见 §2.6） |
| `backend/tests/test_*orders*.py` | 删除所有针对手动下单端点的测试文件/用例（保留账户管理测试） |

### 3.8 CSS 改造（`backend/app/web/static/css/app.css`）

| 行 | 操作 |
|---|---|
| 2089–2238 | **删除** `cq-market-orderbook-*` 全部规则块 |
| 2300–2745 | **删除** `cq-trading-*` 全部规则块（验证最后一个块到 `.cq-trading-tabs__panel.is-active` 在行 2741–2743） |
| 文末 | **新增** `cq-drawer*`、`cq-drawer__overlay`、`cq-drawer__panel`、`cq-drawer__header`、`cq-drawer__tabs`、`cq-drawer__tab`、`cq-drawer__body`、`cq-settings-pane`、`cq-instance-summary`、`cq-instance-kline`、`cq-instance-positions`、`cq-instance-orders`、`cq-instance-actions`、`cq-event-filters`、`cq-event-pagination` 等样式 |

CSS 设计原则：
- 抽屉宽度桌面 480px、移动端全宽
- `cq-drawer[hidden]` 走 `display:none`，open 时 panel 用 `transform: translateX(0)` 配合 transition
- `cq-drawer--right` 表示从右侧滑入
- overlay 半透明 + 点击关闭

具体 CSS 量约 200 行，codex 自行实现。

## 4. 测试用例

### 4.1 后端单测

新建 `backend/tests/test_events_api.py`：

```python
import pytest
from datetime import datetime, timezone, timedelta

@pytest.mark.asyncio
async def test_list_events_empty(async_client):
    """空库返回 200 + total=0 + items=[]"""
    resp = await async_client.get("/api/v1/events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["limit"] == 50
    assert body["offset"] == 0

@pytest.mark.asyncio
async def test_list_events_with_audit_signal_pause(async_client, db_session, fixture_user):
    """插入 3 条 audit_log + 2 条 strategy_signal + 1 条 auto_pause 事件，应返回 6 条"""
    # fixture: 在 db_session 中插入测试数据
    # 调用 /api/v1/events
    # 断言 total=6, len(items)=6, items 按时间倒序
    ...

@pytest.mark.asyncio
async def test_list_events_filter_by_type(async_client, db_session, fixture_events_mixed):
    resp = await async_client.get("/api/v1/events?event_type=risk")
    body = resp.json()
    assert all(e["type"] == "risk" for e in body["items"])

@pytest.mark.asyncio
async def test_list_events_filter_by_instance(async_client, db_session, fixture_events_mixed):
    resp = await async_client.get("/api/v1/events?instance_id=1")
    body = resp.json()
    assert all(e["instance_id"] == 1 for e in body["items"])

@pytest.mark.asyncio
async def test_list_events_search(async_client, db_session, fixture_events_mixed):
    resp = await async_client.get("/api/v1/events?q=BTCUSDT")
    body = resp.json()
    assert all("BTCUSDT" in e["summary"] for e in body["items"])

@pytest.mark.asyncio
async def test_list_events_pagination(async_client, db_session, fixture_100_events):
    resp1 = await async_client.get("/api/v1/events?limit=10&offset=0")
    resp2 = await async_client.get("/api/v1/events?limit=10&offset=10")
    assert resp1.json()["items"][0]["id"] != resp2.json()["items"][0]["id"]
    assert len(resp1.json()["items"]) == 10
    assert resp1.json()["total"] == 100

@pytest.mark.asyncio
async def test_list_events_invalid_type(async_client):
    """非法 event_type 应返回 422"""
    resp = await async_client.get("/api/v1/events?event_type=invalid_xxx")
    assert resp.status_code == 422
```

新建 `backend/tests/test_runner_status_api.py`：

```python
@pytest.mark.asyncio
async def test_runner_status_no_instances(async_client, mock_strategy_runner_empty):
    resp = await async_client.get("/api/v1/strategies/runner/status")
    body = resp.json()
    assert body["strategy_runner"]["task_count"] == 0
    assert body["strategy_runner"]["alive_count"] == 0
    assert isinstance(body["exchanges"], list)

@pytest.mark.asyncio
async def test_runner_status_with_running_instance(async_client, mock_strategy_runner_with_task):
    resp = await async_client.get("/api/v1/strategies/runner/status")
    body = resp.json()
    assert body["strategy_runner"]["task_count"] == 1
    assert body["strategy_runner"]["alive_count"] == 1

@pytest.mark.asyncio
async def test_runner_status_exchange_failure(async_client, mock_exchange_ping_fail):
    """ping 失败时应返回 ws_connected=False, 不抛 500"""
    resp = await async_client.get("/api/v1/strategies/runner/status")
    assert resp.status_code == 200
    body = resp.json()
    failed = [e for e in body["exchanges"] if not e["ws_connected"]]
    assert len(failed) >= 1
    assert "error" in failed[0]
```

### 4.2 后端回归（手动下单端点已删）

```bash
docker compose run --rm backend pytest -q
# 应全绿；test_*orders*.py 应已被删除（不存在）
```

确认这些 endpoint 不再可达：

```bash
docker compose run --rm backend pytest -q -k "test_create_order or test_cancel_order or test_emergency_close or test_set_stop_loss"
# 应输出 "no tests ran"（无匹配）
```

### 4.3 前端手测脚本（浏览器 DevTools 控制台 + 肉眼检查）

```
1. docker compose up --build
2. 打开 http://localhost:8001/web/，登录 ltlghs@gmail.com
3. 验证侧栏只有 4 项：控制台 / 策略 / 回测 / 事件流
   ✓ 无"账户"分组、无"交易"分组
4. 点击右上角齿轮 → 设置抽屉从右侧滑出
   ✓ 5 个 tab 全部可切换：交易所账户 / 模拟盘 / 通知通道 / 风控参数 / 安全
   ✓ 交易所账户 tab：可看到现有账户列表，可新增/删除（功能等同旧 page-accounts）
   ✓ 模拟盘 tab：等同旧 page-paper
   ✓ 安全 tab：2FA + 审计日志等同旧 page-security
   ✓ 通知通道 tab：显示 telegram_bot_token / telegram_chat_id 是否已配置（不显示明文）+ 提示编辑 .env
   ✓ 风控参数 tab：显示 5 个 auto_pause_* 配置当前值（read-only）
   ✓ 点 overlay 或 ✕ 关闭抽屉
5. 控制台首页：四块布局可见
   ✓ 块 A 策略实例列表（无策略时显示 empty state）
   ✓ 块 B 实时活动流（最近 50 条，时间倒序）
   ✓ 块 C 权益曲线（30 天，含 7/30/90 天切换）
   ✓ 块 D 风险事件 24h（无事件时显示 empty）
   ✓ 块 E 系统状态（runner + 各交易所）
6. 在策略中心创建并启动一个 RSI 分层实例
   返回控制台 → 块 A 应显示该实例
   点击该行 → 实例抽屉从右侧滑出
   ✓ 摘要卡片显示状态/PnL/启动时间
   ✓ K 线 details 默认折叠
   ✓ 展开 K 线 → 加载该实例对应 symbol 的 1h K 线（无报错）
   ✓ 持仓表 / 订单表 加载
   ✓ [暂停] 按钮可用，点击后实例状态变 paused
   ✓ [查看完整日志] → 跳转到事件流页且过滤 instance_id
7. 点击侧栏"事件流" → events 页加载
   ✓ 默认显示最近 24 小时所有类型
   ✓ 类型筛选可切换（5 种类型 + 全部）
   ✓ 时间范围可切换（1h/24h/7d/30d）
   ✓ 搜索框输入回车后过滤
   ✓ 分页可上一页/下一页
8. 浏览器地址栏输入老 hash:
   #market → 自动跳到 dashboard
   #trading → 自动跳到 dashboard
   #paper → 自动跳到 dashboard
   #security → 自动跳到 dashboard
   #accounts → 自动跳到 dashboard
   ✓ 不出现白屏 / 不出现 console error
```

### 4.4 grep 验收

```bash
# A. 旧入口完全清除
grep -rnE "page-trading|page-market|page-paper|sltp-dialog" backend/app/web/static && echo "FAIL: A1"
grep -rnE "trading\.js|market\.js" backend/app/web/static/index.html && echo "FAIL: A2"
grep -rnE "createOrder|cancelOrder|setStopLoss|setTakeProfit|emergencyClose|closePosition|getSymbolRules|getContractSettings" backend/app/web/static/js && echo "FAIL: A3"
grep -nE "POST.*orders|/{order_id}/cancel|emergency-close|stop-loss|take-profit|close_position|create_order" backend/app/api/v1/orders.py && echo "FAIL: A4"

# B. 新增功能存在
grep -rn "openInstanceDrawer" backend/app/web/static/js | head -3   # 必须有
grep -rn "openSettingsDrawer" backend/app/web/static/js | head -3   # 必须有
grep -rn "switchSettingsTab" backend/app/web/static/js | head -3    # 必须有
grep -rn "renderInstanceList\|renderActivityStream\|renderRiskEvents\|renderSystemStatus" backend/app/web/static/js/dashboard.js
grep -rn "from app.api.v1 import events" backend/app/api/v1/__init__.py
grep -rn "@router.get.*runner/status" backend/app/api/v1/strategies.py

# C. 老 page 视图已删
grep -nE "id=\"page-(trading|market|paper|security|accounts)\"" backend/app/web/static/index.html && echo "FAIL: C1"

# D. 老 sidebar 项已删
grep -nE "data-page=\"(trading|market|paper|security|accounts)\"" backend/app/web/static/index.html && echo "FAIL: D1"

# E. CSS 残留扫除
grep -nE "^\.cq-trading|^\.cq-market-orderbook" backend/app/web/static/css/app.css && echo "FAIL: E1"
```

A/C/D/E 段全部应**无 FAIL**输出，B 段每条应**至少有 1 行匹配**。

## 5. 验收标准

1. `docker compose up --build` 成功启动
2. 浏览器 `http://localhost:8001/web/` 可登录 `ltlghs@gmail.com`
3. §4.3 全部 8 步手测通过
4. `docker compose run --rm backend pytest -q` 全绿
5. `docker compose run --rm backend ruff check .` 无报错
6. `docker compose run --rm backend python -m black --check .` 无报错
7. §4.4 grep A/C/D/E 段无 FAIL，B 段全部有匹配
8. 浏览器 DevTools Console 在所有页面均无 `Uncaught` 错误
9. 浏览器 Network 面板：
   - 无对 `/api/v1/trading` (POST) 的请求
   - 无对 `/api/v1/trading/{id}/cancel` 等手动操作端点的请求
   - 控制台首页加载触发 `/api/v1/strategies/instances`、`/api/v1/events`、`/api/v1/strategies/runner/status` 各 1 次

## 6. 反范式（**不要做**）

1. **不要保留任何手动下单 UI 的"假装关闭"模式**——不要藏起来留着以后开。直接删文件、删路由、删 CSS。如果以后需要，从 git 历史恢复。
2. **不要把 K 线做成全屏页面或独立 tab**——K 线只在策略实例抽屉的 `<details>` 里出现，默认折叠。用户想看图就去交易所原生 app。
3. **不要新增数据库表**给事件流。聚合查询现有 `audit_log` + `strategy_signals` + `last_pause_reason`。即使聚合 SQL 复杂也接受，自用单人量级数据完全够。
4. **不要给"通知通道"和"风控参数"做新的 PUT/POST API**。这两个 tab v1 仅 read-only 显示当前 settings 值 + 提示"请编辑 backend/.env 后 docker compose restart"。引入可写 API 是另一个 spec 的事。
5. **不要把 `accounts.js` / `paper.js` / `security.js` 重写**。只把它们的入口函数改名（`loadXxxPage` → `renderXxxPane(targetSelector)`），渲染逻辑保持原样。
6. **不要在抽屉里嵌入完整的 strategy/backtest 子界面**——抽屉只是"实例详情"，编辑策略走主页 `#page-strategy`。
7. **不要把"控制台"做成可拖拽/可自定义"驾驶舱"**。四块布局是固定的，不做 widget 编辑器。
8. **不要把"事件流"做成 WebSocket 实时推流**。v1 用 polling（控制台首页 5 秒拉一次最新 50 条；事件流页只在用户操作时刷新）。WebSocket 是另一个 spec。
9. **不要在删除前端 `market.js` 时顺手删 `backend/app/api/v1/market.py`**——后端 `/market` 路由策略 runner 要用，仅前端市场页废弃。
10. **不要在重写 `dashboard.js` 时改其他页面的入口风格**。`strategy.js` / `backtest.js` 保持原样。
11. **不要给抽屉做"路由化"**（hash URL 跟踪抽屉打开状态）。抽屉是临时性的"瞄一眼"模式，关闭即销毁状态。
12. **不要在事件流里展示明文 API key / secret**。即使 `audit_log` 含敏感字段也要在 serialization 时 mask（参考现有 audit 列表的 mask 实现）。
13. **不要在本 spec 改 `setup.html` 或安装向导**。那是另一个层面的产品味讨论，不在本 spec 范围。
14. **不要把 `orders.py` 文件改名或拆分**。删完手动端点后文件名虽然名不副实，但保留它和 `/trading` 前缀以最小化对 `accounts.js` 等调用方的改动；改名是 nice-to-have，不在本 spec 范围。
15. **不要在抽屉打开/关闭时做花哨动画**（如弹簧、3D 翻转）。简单的 transform: translateX 配 transition 0.2s ease 即可。
16. **不要新增 `setup.html` 路由的修改**——本 spec 完全不动安装向导。
17. **不要把 K 线渲染从 `kline.js` 抄到 `instance-drawer.js` 内联**——`renderKline` 必须是独立可复用函数，否则后续如果策略页也要小 K 线就重复劳动。
18. **不要在 `navigate('events')` 时才动态创建 `#page-events` DOM**。所有 page-view 在 `index.html` 里静态存在，`navigate()` 只切 active class。

## 7. Commit 分片建议

按以下 7 片顺序提交，每片对应一组测试可独立验证。**严格按顺序，不要乱序或合并**。

### Commit 1: 砍除手动下单 UI（前端）
**文件**：`index.html`、`js/trading.js`、`js/api.js`、`css/app.css`

- 删除 `index.html:491-624`（`#page-trading` 整块）
- 删除 `index.html:626-650`（`#sltp-dialog` 整块）
- 删除 `index.html:184-198`（"交易"sidebar section 整块；market 项也在内但只删 trading 项；本片只删 trading）—— **修正**：本片仅删 trading 项（行 192-197 + 一个 div 闭合），market 项保留到 commit 3
- 删除 `js/trading.js`（整文件）
- 删除 `js/api.js:351-431` 中的 trading 订单方法（11 个）
- 删除 `css/app.css:2300-2745` 中的 `cq-trading-*` 块
- 修改 `index.html:806-846` 的 `navigate()`：删除 trading 分支 + 行 834 的 `stopTradingOrderbookPolling` 清理
- **验证**：§4.4 grep A1/A2/A3 通过；浏览器 sidebar 无"手动交易"项；首页 dashboard 仍正常

### Commit 2: 砍除手动下单端点（后端）
**文件**：`app/api/v1/orders.py`、`backend/tests/test_*orders*.py`

- 删除 `orders.py` 中 7 个手动端点（参见 §1.5 行号）
- 删除 `orders.py` 顶部因端点删除而成为孤儿的 import / schema
- 删除关联测试文件（`test_orders.py` 等含 `create_order` / `cancel_order` / `emergency_close` 的测试）
- **验证**：`pytest -q` 全绿；§4.4 grep A4 无 FAIL

### Commit 3: 砍除 market 前端页 + 4 个独立账户/安全/模拟盘页
**文件**：`index.html`、`js/market.js`、`css/app.css`

- 删除 `index.html:441-489`（`#page-market`）
- 删除 `index.html:412-420`（`#page-accounts`）
- 删除 `index.html:423-429`（`#page-paper`）
- 删除 `index.html:432-438`（`#page-security`）
- 删除 `index.html:162-198` 残余 sidebar："账户"section 整个 + "交易"section 残余 market 项 + 整个 section（commit 1 已删 trading）
- 删除 `js/market.js`（整文件）
- 删除 `css/app.css:2089-2238` 的 `cq-market-orderbook-*` 块
- 修改 `navigate()`：删除 paper/security/accounts/market 分支 + 行 833 的 `stopMarketWs` 清理
- **暂时**：accounts/paper/security 三个 `loadXxxPage` 全局函数体保留在原文件中（commit 4 会改造它们的 mount 点）
- **验证**：§4.4 grep C1/D1/E1 无 FAIL；浏览器 sidebar 仅剩 dashboard/strategy/backtest 三项；首页仍可加载

### Commit 4: 设置抽屉 + accounts/paper/security 入口改造
**文件**：`index.html`、`js/settings-drawer.js`（新建）、`js/accounts.js`、`js/paper.js`、`js/security.js`、`css/app.css`

- 改 `index.html:120-122` 删除旧账户快捷按钮，改为齿轮按钮
- 在 `index.html:665` 后追加 `<aside id="settings-drawer">` 完整骨架（§2.4）
- 新建 `js/settings-drawer.js`（§3.5）
- 改 `accounts.js`：新增 `renderAccountsPane(targetSelector)`，原 `loadAccountsPage` 函数体迁入，目标 element 接受 selector 参数
- 改 `paper.js`：同上 → `renderPaperPane(targetSelector)`
- 改 `security.js`：同上 → `renderSecurityPane(targetSelector)`
- `index.html` `<script>` 区追加 `<script src="js/settings-drawer.js"></script>`
- `css/app.css` 末尾追加 `cq-drawer*` / `cq-settings-pane` 等样式
- **验证**：齿轮按钮可点击 → 抽屉打开 → 5 个 tab 切换正常；交易所账户 tab 内容功能等同旧 page-accounts

### Commit 5: 后端 `/events` + `/runner/status` 端点
**文件**：`app/api/v1/events.py`（新建）、`app/api/v1/__init__.py`、`app/api/v1/strategies.py`、`backend/tests/test_events_api.py`（新建）、`backend/tests/test_runner_status_api.py`（新建）

- 新建 `events.py`（§2.6）
- 在 `__init__.py` 注册 events router
- 在 `strategies.py:597` 后追加 `GET /runner/status`（§2.7）
- 新建测试文件（§4.1）
- **验证**：`pytest backend/tests/test_events_api.py backend/tests/test_runner_status_api.py -v` 全绿；`pytest -q` 全绿

### Commit 6: 实例抽屉 + 事件流页 + K 线复用
**文件**：`index.html`、`js/kline.js`（新建）、`js/instance-drawer.js`（新建）、`js/events.js`（新建）、`js/api.js`、`css/app.css`

- 在 `index.html:624` 后追加 `#page-events` 整块（§3.1.2）
- 在 `index.html:159` 后追加 sidebar "事件流" nav 项
- 在 `index.html:663` 后追加 `<aside id="instance-drawer">`（§2.5）
- 新建 `js/kline.js`（§3.5）—— 从原 `market.js` 的 K 线渲染逻辑抽取参数化版本
- 新建 `js/instance-drawer.js`（§3.5）
- 新建 `js/events.js`（§3.5）
- `js/api.js` 文末追加 `getEvents` + `getRunnerStatus` + `resolveSinceParam` helper
- `index.html` `<script>` 区追加 `<script src="js/kline.js"></script>` `<script src="js/instance-drawer.js"></script>` `<script src="js/events.js"></script>`
- `index.html` `navigate()` 增加 `events` 分支
- `css/app.css` 末尾追加 `cq-instance-*` / `cq-event-*` 样式
- **验证**：sidebar 出现"事件流"；点击进入 → 页加载；模拟点击控制台某条策略行（commit 7 之前控制台还是旧版，这里手动 `openInstanceDrawer(1)` 控制台调用即可验证）→ 抽屉滑出 + K 线展开正常

### Commit 7: 控制台首页重写 + 老 hash 兜底 + 收尾
**文件**：`js/dashboard.js`、`index.html`

- 重写 `js/dashboard.js`（§3.2）
- 改 `index.html:214-253` 的 `#page-dashboard` 为新四块布局（§3.1.1）
- 改 `navigate()` 末尾增加老 hash 兜底（§3.1.3）
- **全量回归**：§4.3 全部 8 步、§4.4 grep 全部、`pytest -q` 全绿、`ruff check .` + `black --check .` 全绿、Console 无 error
