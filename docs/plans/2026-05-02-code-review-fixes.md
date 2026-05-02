# 代码审查修复设计文档

**日期**: 2026-05-02
**审查报告**: 代码审查报告_crypto-quant-app.md
**状态**: 已验证 → 设计完成

## 验证结论

原报告 13 项中，2 项🔴严重被证伪（service 层已有所有权校验），2 项🟡轻微合并，实际需修复 **7 项**：

| # | 严重度 | 问题 | 验证结果 |
|---|--------|------|---------|
| 1 | 中高 | `_auto_trade` 未验证 account_id 归属 | ✅ 确认 |
| 2 | 中高 | 联合唯一约束 `(exchange_order_id, account_id)` 缺失 | ✅ 确认 |
| 3 | 中 | `refresh token` 并发竞态 | ✅ 确认 |
| 4 | 低 | `submit_order` 非 HTTPException 幽灵订单 | ⚠️ 部分存在 |
| 5 | 低 | `strategyType` 默认空值防御 | ⚠️ 存在未触发 |
| 6 | 低 | `escapeHtml` 全局依赖 + 部分未 escape | ⚠️ 部分存在 |
| 7 | 低 | `APIResponse` 格式不一致 | ⚠️ 轻微 |

## 修复方案

### Fix-1: `_auto_trade` 验证 account_id 归属（中高）

**文件**: `backend/app/core/strategy_runner.py` ~L443

**当前代码**:
```python
acct_result = await session.execute(
    select(ExchangeAccount).where(ExchangeAccount.id == inst.account_id)
)
account = acct_result.scalar_one_or_none()
if not account or not account.is_active:
```

**修复**: 增加归属校验
```python
if not account or not account.is_active or account.user_id != inst.user_id:
```

**同时**修复 `strategy_service.py` 的 `update_instance`，在 `allowed_fields` 中移除 `account_id`（或增加归属校验）：
- 移除 `account_id` from `allowed_fields`，因为当前 API 路由未暴露此字段，不应允许服务层随意修改
- 如果需要修改 account_id，应走专门的 `change_account` 方法并校验归属

### Fix-2: 添加联合唯一约束（中高）

**文件**: `backend/app/models/order.py`

**当前代码**:
```python
__table_args__ = (
    # P2-6: 联合唯一约束，不同交易所订单ID可能重复
    {"sqlite_autoincrement": True},
)
```

**修复**:
```python
from sqlalchemy import UniqueConstraint

__table_args__ = (
    UniqueConstraint('exchange_order_id', 'account_id', name='uq_order_exchange_account'),
    {"sqlite_autoincrement": True},
)
```

**需要**：创建 Alembic 迁移添加此约束

### Fix-3: refresh token 并发竞态（中）

**文件**: `backend/app/web/static/js/api.js`

**修复**: 使用 Promise 缓存（单例模式）
```javascript
async _refreshAccessToken() {
    if (this._refreshPromise) return this._refreshPromise;
    this._refreshPromise = this._doRefresh();
    try {
        return await this._refreshPromise;
    } finally {
        this._refreshPromise = null;
    }
}

async _doRefresh() {
    // 原 _refreshAccessToken 逻辑
}
```

### Fix-4: submit_order 非 HTTPException 幽灵订单（低）

**文件**: `backend/app/api/v1/orders.py` ~L244

**当前代码**: `except HTTPException:` 只捕获 HTTPException

**修复**: 扩大捕获范围
```python
try:
    order = await service.submit_order(order.id, current_user.id)
except HTTPException:
    try:
        await service.order_repo.delete(order.id)
        await session.commit()
    except Exception:
        pass
    raise
except Exception:
    # 非 HTTPException 也需清理（如 AppException）
    try:
        await service.order_repo.delete(order.id)
        await session.commit()
    except Exception:
        pass
    raise HTTPException(status_code=502, detail="下单失败，请检查订单状态")
```

### Fix-5: strategyType 默认空值防御（低）

**文件**: `backend/app/api/v1/strategies.py` ~L93

**修复**: 在模板序列化时强制校验 strategy_type
```python
"strategyType": t.get("strategy_type") or t.get("code", ""),
```
确保 rule 类型模板不会因字段缺失而走 slider 渲染路径。

### Fix-6: escapeHtml 全局依赖（低）

**文件**: `backend/app/web/static/js/strategy.js` 等多个文件

**修复**: 将 `escapeHtml` 从 `dashboard.js` 移到 `api.js`（最先加载的工具库），确保全局可用

### Fix-7: APIResponse 格式一致性（低）

**文件**: 多个路由文件

**修复**:
- `strategies.py`: `PREDEFINED_TEMPLATES` 列表中的 dict 改为使用 Schema 序列化
- 统一 `delete` 操作返回格式：要么都有 data，要么都用 message-only

## 不修复项（原报告证伪）

- ~~问题1: order_service IDOR~~ → service 层已有 position → account → user 链式校验
- ~~问题2: strategy_service IDOR~~ → service 层已有 instance.user_id 校验

## 执行顺序

1. Fix-1 + Fix-2（P0 级，安全相关）
2. Fix-3（P1 级，竞态条件）
3. Fix-4 + Fix-5 + Fix-6 + Fix-7（P2 级，防御性改进）
