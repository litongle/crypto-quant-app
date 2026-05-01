# 📊 币钱袋 (CryptoQuant) 周报

## W18 · 2026年4月27日 — 5月1日

---

## 📌 概述

| 指标 | 数量 | 备注 |
|------|------|------|
| 总提交 | **27 次** | Apr 27 – May 1 |
| 合并 PR | **2 个** | PR #2, PR #3 |
| 关闭 PR | **1 个** | PR #1 (未合并) |
| Open Issue | **0 个** | 仓库无积压 Issue |

---

## 🚀 主要进展

### 1. 策略运行器（Strategy Runner）核心完善
- **Step 2a**: `_auto_trade` 支持读取 `signal.metadata.intent` 路由平仓意图
- **Step 2b**: `reverse` 反手操作原子化，先平后开，避免仓位冲突
- **Step 3**: 策略状态持久化，重启后不丢失仓位、极值和冷却状态

### 2. 前端控制台全面升级
- ✅ 行情页新增 **K线蜡烛图** + 币种列表迷你走势图（sparkline）
- ✅ 行情面板添加 **时间周期选择器**（1m/5m/1h/1d）
- ✅ 交易所设置页实现 **API Key 保存/断开/重连** 功能
- ✅ 移除永续合约（暂不支持）+ 切换币种立即拉 ticker 避免 `-- --` 卡顿

### 3. 测试覆盖率大幅提升
- 测试用例从 **196 → 373**（增长 90%）
- 后端覆盖率从 **~25% → ~57%**
- PR #2 专项补齐测试

### 4. gc 项目合并（RSI 分层极值追踪）
- 合并 RSI 分层极值追踪机器人代码
- 移植 `ba7af28` 策略实现
- 清理 `gc/frontend/node_modules` 污染
- 删除已决定不吸收的 60+ 文件

### 5. 重大 Bug 修复
| Bug | 严重度 | 修复内容 |
|-----|--------|----------|
| Redis asyncio.Lock 死锁 | P0 | `/api/v1/market/*` 全部 hang 问题 |
| WebSocket 缺 JWT token | P0 | 行情 WS 403 错误 |
| StrategyTemplateResponse 缺字段 | P0 | 字段补齐 + backtest 表单类型扩展 |
| asyncio.Lock 死锁 | P0 | 已彻底修复 |
| 永续合约显示卡顿 | P1 | 移除 perp + ticker 即时刷新 |

### 6. 行情服务升级
- **F1**: 合约市场支持（spot/perp 双市场，只读）
- OKX 认证、余额同步、路由404、时间同步四项修复
- error_handling 吸收：trace_id + retry 装饰器

### 7. 架构优化
- 策略模板 upsert 机制
- 回测引擎内存优化（自动时间级别+滑动窗口+采样+超时保护）
- pydantic-settings 替代 env_manager.py

---

## 🔑 关键变更文件

| 文件/目录 | 变更类型 | 说明 |
|-----------|----------|------|
| `backend/app/runner/` | feat | 策略运行器 3 步完善 |
| `backend/app/web/` | feat/fix | 前端控制台全面升级 |
| `backend/app/market/` | feat | 行情服务合约支持 |
| `backend/app/core/error_handling.py` | feat | trace_id + retry 装饰器 |
| `gc/` → 合并 | chore | 删除 gc 目录，代码已移植 |
| `tests/` | test | 覆盖率 25% → 57% |

---

## 📋 待关注事项

### 🔴 高优先级
1. **策略信号 WS 前端订阅** — 后端已推送但前端无通知（延续事项）
2. **6 个未修复项** — P2-3/P2-5/P2-8/P3-1/P3-4/P3-3/P3-6 待处理

### 🟡 中优先级
1. **token httpOnly cookie** — P3 安全优化
2. **OKX Passphrase 空值** — 需用户手动填写
3. **Alembic 迁移** — 初始迁移已初始化，待 git commit + push

---

## 📈 质量指标

| 指标 | 上周 | 本周 | 趋势 |
|------|------|------|------|
| 测试用例数 | 196 | 373 | 📈 +90% |
| 后端覆盖率 | ~25% | ~57% | 📈 +32pp |
| Open Issue | — | 0 | ✅ 清零 |

---

## 🔗 相关链接

- **仓库**: https://github.com/litongle/crypto-quant-app
- **PR #2**: 测试覆盖补齐（已合并 2026-04-28）
- **PR #3**: 前端控制台升级（已合并 2026-04-28）

---

*📅 报告生成时间: 2026-05-01 17:00 (GMT+8)*
