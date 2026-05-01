# Plan: 生产就绪功能开发计划

> Source PRD: 2026-05-01 生产前必须补的功能清单

## Architectural decisions

- **通知渠道**: Telegram Bot + 企微 Webhook 双通道，统一由 `notification_service.py` 管理
- **定时任务**: FastAPI lifespan 启动 `asyncio.Task`，不使用外部 cron/scheduler 库
- **订单对账**: 每 30-60s 轮询交易所未完成订单，更新本地状态
- **持仓价格刷新**: StrategyRunner 轮询行情时顺带更新绑定策略的持仓价格
- **审计日志**: 中间件拦截所有写操作（POST/PUT/PATCH/DELETE），记录到 audit_logs 表
- **2FA**: TOTP (pyotp)，用户模型增加 `totp_secret` 字段
- **风控仪表盘**: 新 API `/api/v1/risk/dashboard` 返回实时计算指标
- **回测手续费/滑点**: BacktestService 增加 commission_rate 和 slippage 参数

## Database Schema Additions

- `audit_logs` - 审计日志表
- `notifications` - 通知记录表（可选，用于通知历史）
- `users.totp_secret`, `users.totp_enabled` - 2FA 字段
- `orders` 已有 status 枚举包含 filled/cancelled/rejected
- `positions.current_price` 已有，需自动更新逻辑

---

## Phase 1: 通知系统 (P0-1)

**User stories**: 策略信号通知、止损止盈触发通知、大额成交通知

### What to build

统一通知服务 `notification_service.py`，支持 Telegram Bot 和企微 Webhook 双通道。
- 策略产生信号 → 推送消息
- 止损/止盈触发 → 推送消息
- 大额成交（订单价值 > 阈值）→ 推送消息
- 用户可配置通知渠道和阈值

### Acceptance criteria

- [ ] `notification_service.py` 支持 Telegram 和企微 Webhook
- [ ] 策略信号产生时自动推送通知
- [ ] 止损/止盈触发时推送通知
- [ ] 大额成交（> 1000 USDT）推送通知
- [ ] 用户可在设置中配置通知渠道
- [ ] 通知失败不影响主业务流程

---

## Phase 2: 持仓价格自动刷新 (P0-2)

**User stories**: 持仓未实现盈亏实时更新

### What to build

StrategyRunner 在轮询行情时，顺带更新绑定策略的持仓 current_price。
前端通过现有 WS `/ws/market` 接收持仓价格变动推送。

### Acceptance criteria

- [ ] StrategyRunner 每轮询周期更新持仓 current_price
- [ ] 持仓 unrealized_pnl 自动重新计算
- [ ] 前端 WS 推送持仓价格变动
- [ ] 价格更新频率与 K 线轮询周期对齐

---

## Phase 3: 订单状态对账 (P0-3)

**User stories**: 订单状态与交易所保持一致

### What to build

定时任务每 30-60s 查询交易所未完成订单状态：
- 成交 → 更新 status=filled + avg_fill_price + commission + pnl
- 取消/拒绝 → 更新对应状态
- 部分成交 → 更新 partial 状态

### Acceptance criteria

- [ ] 定时任务查询交易所未完成订单
- [ ] 成交订单更新 filled 状态及成交详情
- [ ] 取消/拒绝订单更新对应状态
- [ ] 部分成交更新 partial 状态
- [ ] 对账失败记录日志，不影响其他订单

---

## Phase 4: 定时同步任务 (P1-1)

**User stories**: 余额/持仓/订单自动同步

### What to build

FastAPI lifespan 启动 asyncio.Task，每 5 分钟自动同步：
- 账户余额
- 持仓信息
- 订单历史

### Acceptance criteria

- [ ] lifespan 启动定时同步任务
- [ ] 每 5 分钟同步余额
- [ ] 每 5 分钟同步持仓
- [ ] 每 5 分钟同步订单
- [ ] 同步失败记录日志，下次继续

---

## Phase 5: 2FA 双因素认证 (P1-2)

**User stories**: 登录安全增强

### What to build

- 用户模型增加 totp_secret 和 totp_enabled
- 登录流程增加 TOTP 验证步骤
- 提供 QR Code 绑定接口
- 提供 2FA 启用/禁用接口

### Acceptance criteria

- [ ] 用户可启用 2FA，扫描 QR Code 绑定
- [ ] 启用 2FA 后登录需输入 TOTP 码
- [ ] 支持 2FA 禁用（需验证密码）
- [ ] 备用恢复码生成

---

## Phase 6: 操作审计日志 (P1-3)

**User stories**: 操作可追溯

### What to build

- AuditLog 模型 + 表
- 中间件拦截所有写操作（POST/PUT/PATCH/DELETE）
- 记录：用户ID、操作类型、资源、变更内容、IP、时间

### Acceptance criteria

- [ ] 所有写操作自动记录审计日志
- [ ] 审计日志包含用户、操作、资源、时间、IP
- [ ] 提供审计日志查询 API
- [ ] 敏感字段脱敏处理

---

## Phase 7: 风控仪表盘 (P1-4)

**User stories**: 全局风险视图

### What to build

新 API `/api/v1/risk/dashboard` 返回：
- 总敞口占比（持仓价值 / 总资产）
- 单币种集中度
- 最大回撤监控 + 告警阈值
- 杠杆使用情况

### Acceptance criteria

- [ ] 风控仪表盘 API 返回实时指标
- [ ] 总敞口占比计算准确
- [ ] 单币种集中度排名
- [ ] 最大回撤超过阈值时推送告警

---

## Phase 8: 回测手续费/滑点模拟 (P1-5)

**User stories**: 回测结果更接近真实

### What to build

BacktestService 增加：
- 手续费率参数（默认 0.1% maker/taker）
- 滑点模拟（根据成交量和波动率）
- 更精确的 PnL 计算

### Acceptance criteria

- [ ] 回测支持手续费率配置
- [ ] 回测支持滑点模拟
- [ ] 默认手续费率与 Binance 一致（0.1%）
- [ ] 回测结果展示手续费和滑点影响

---

## Phase 9: GitHub 提交

**User stories**: 代码版本管理

### What to build

- 所有变更提交到 GitHub
- 清晰的 commit message
- 更新 README 和版本号

### Acceptance criteria

- [ ] 所有代码变更已 commit
- [ ] Commit message 清晰描述变更
- [ ] 推送到 GitHub
- [ ] README 更新版本号和功能列表
