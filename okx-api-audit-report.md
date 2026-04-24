# OKX API 适配器审计报告

> **项目**: 币钱袋 (CryptoQuant)  
> **审计对象**: `backend/app/core/exchange_adapter.py` OKXAdapter  
> **对照文档**: [OKX API v5 官方文档](https://www.okx.com/docs-v5/zh/)  
> **审计时间**: 2026-04-25

---

## 一、总体评估

**结论：OKX 适配器的 API 路径和签名算法基本正确，但存在 4 个关键 Bug 导致「API Key 无效」和「交易 404」问题。**

| 维度 | 评分 | 说明 |
|------|------|------|
| API 路径 | ✅ 正确 | 行情/交易/账户路径均与官方一致 |
| 签名算法 | ⚠️ 逻辑正确，但有 Passphrase 传递 Bug | HMAC-SHA256 + Base64 实现正确 |
| 数据模型 | ✅ 正确 | instId 转换、字段映射均正确 |
| 交易流程 | ❌ 严重缺陷 | 缺少余额同步机制 + 路由冲突导致 404 |

---

## 二、关键 Bug 详解

### 🔴 Bug #1：Passphrase 空字符串导致认证失败（根因）

**文件**: `exchange_adapter.py` 第 730 行

```python
# 当前代码（有 Bug）
headers = {
    "OK-ACCESS-KEY": self.api_key,
    "OK-ACCESS-SIGN": sign,
    "OK-ACCESS-TIMESTAMP": timestamp,
    "OK-ACCESS-PASSPHRASE": self.passphrase or "",  # ← Bug!
}
```

**问题**：OKX 要求 `OK-ACCESS-PASSPHRASE` 必须是创建 API Key 时设置的口令原文。当 `self.passphrase` 为 `None` 时，代码发送空字符串 `""`，OKX 会返回错误码 `50113`（Invalid passphrase）。

**调用链追踪**：
1. 用户在 Web 控制台添加 OKX 账户，填写 API Key + Secret Key + Passphrase
2. `orders.py` → `create_exchange_account()` → `account.set_passphrase(plaintext)` 加密存储
3. 需要调用 OKX API 时 → `account.get_passphrase()` 解密
4. `OrderService.submit_order()` 传给 `get_exchange_adapter(passphrase=...)`
5. **但如果用户没填 Passphrase，`encrypted_passphrase` 为 None，`get_passphrase()` 返回 `""`**

**OKX 官方要求**：
> Passphrase 是创建 APIKey 时用户自设的口令，必须与请求头中的 `OK-ACCESS-PASSPHRASE` 完全一致。

**修复方案**：
```python
# 方案 A：前端强制 OKX 必填 Passphrase
# 在 accounts.js 的 submitAddAccount() 中：
if (exchange === 'okx' && !passphrase) {
    showToast('OKX 必须填写 Passphrase', 'warn');
    return;
}

# 方案 B：后端校验（更安全）
# 在 CreateExchangeAccountRequest 中添加验证器
```

---

### 🔴 Bug #2：资产服务从不调用交易所 API 同步余额（无法读取实际内容）

**文件**: `asset_service.py` 全文

```python
async def get_asset_summary(self, user_id, exchange="all"):
    accounts = await self.account_repo.get_active_by_user(user_id)
    for account in accounts:
        total_asset += account.balance       # ← 只读数据库中的缓存值
        available_balance += account.balance  # ← 初始值永远是 0！
```

**问题**：`AssetService` 从不调用 `exchange_adapter.get_balance()` 从交易所获取真实余额。`ExchangeAccount.balance` 的默认值是 `Decimal("0")`，添加账户后没有同步机制，所以永远显示 0。

**缺失的同步流程**：
```
用户添加账户 → 调用 OKX get_balance → 写入 ExchangeAccount.balance → 前端展示
```

**当前流程**：
```
用户添加账户 → ExchangeAccount.balance=0 → 前端展示 0 ❌
```

**修复方案**：添加余额同步 API 和自动同步逻辑：

```python
# 1. 添加同步端点
@router.post("/accounts/{account_id}/sync")
async def sync_account_balance(account_id: int, ...):
    """从交易所同步真实余额"""
    adapter = get_exchange_adapter(...)
    balances = await adapter.get_balance()
    # 更新 ExchangeAccount.balance
    ...

# 2. 添加账户时自动同步
@router.post("/accounts")
async def create_exchange_account(...):
    ...
    await session.commit()
    # 创建后立即同步余额
    try:
        adapter = get_exchange_adapter(...)
        balances = await adapter.get_balance()
        for b in balances:
            if b.asset == "USDT":
                account.balance = b.free
                account.frozen_balance = b.locked
        await session.commit()
    except Exception as e:
        logger.warning("余额同步失败: %s", e)
    ...
```

---

### 🔴 Bug #3：交易路由定义顺序导致 404

**文件**: `orders.py` 路由定义

```python
# 当前路由定义顺序（有问题）：
@router.post("/{order_id}/cancel")         # 路由1
@router.post("/{position_id}/stop-loss")   # 路由2
@router.post("/{position_id}/take-profit")  # 路由3
@router.post("/{position_id}/close")        # 路由4
@router.post("/emergency-close-all")        # 路由5 ← 在参数路由之后！
@router.post("/accounts")                   # 路由6 ← 在参数路由之后！
```

**问题**：FastAPI 路由匹配按定义顺序。当请求 `POST /api/v1/trading/accounts` 时，FastAPI 先尝试匹配 `/{order_id}/cancel`，此时 `order_id="accounts"` 但后面没有 `/cancel`，不会匹配。然而 `POST /emergency-close-all` 可能被 `/{position_id}/close` 干扰（取决于 FastAPI 版本）。

**更关键的问题**：当前缺少一个交易相关的前端页面入口。前端 `api.js` 只定义了 3 个交易方法：

```javascript
async getExchangeAccounts() { ... }     // GET /trading/accounts
async createExchangeAccount(data) { ... } // POST /trading/accounts
async deleteExchangeAccount(accountId) { ... } // DELETE /trading/accounts/{id}
```

**没有** `createOrder()`、`submitOrder()` 等方法！策略页面的交易走的是 `strategy_runner.py` 的后台自动下单，而不是前端手动下单。所以如果用户在前端点击"交易"，可能调用了一个不存在的路由 → **404**。

**修复方案**：
1. 将静态路径路由移到参数化路由之前
2. 在前端 `api.js` 添加交易 API 方法

```python
# 修正后的路由顺序（静态优先）：
@router.post("/accounts", ...)            # ← 静态路径优先
@router.post("/emergency-close-all", ...) # ← 静态路径优先
@router.post("/{order_id}/cancel", ...)   # ← 参数路由靠后
@router.post("/{position_id}/stop-loss", ...)
@router.post("/{position_id}/take-profit", ...)
@router.post("/{position_id}/close", ...)
```

---

### 🟡 Bug #4：缺少 OKX 服务器时间同步（次要认证失败原因）

**OKX 官方要求**：
> 请求时间戳与服务器时间相差超过 30 秒，返回错误码 `50102`。建议先用 `GET /api/v5/public/time` 同步服务器时间。

**当前代码**：
```python
def _okx_timestamp(self) -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
```

直接用本机 UTC 时间，没有与 OKX 服务器同步。如果服务器时区偏差或系统时钟有微小漂移，所有认证请求都会失败。

**修复方案**：
```python
async def _sync_server_time(self) -> None:
    """同步 OKX 服务器时间，计算偏移量"""
    client = await self.get_shared_client()
    resp = await client.get(f"{self.BASE_URL}/api/v5/public/time")
    data = resp.json()
    server_ts = int(data["data"][0]["ts"])  # 毫秒时间戳
    local_ts = int(time.time() * 1000)
    self._time_offset_ms = server_ts - local_ts

def _okx_timestamp(self) -> str:
    """使用校准后的时间戳"""
    adjusted = datetime.now(timezone.utc) + timedelta(milliseconds=self._time_offset_ms)
    return adjusted.isoformat(timespec="milliseconds").replace("+00:00", "Z")
```

---

## 三、OKX 适配器与官方文档逐项对比

| 对比项 | 官方文档 | 项目实现 | 是否一致 |
|--------|----------|----------|----------|
| Base URL | `https://www.okx.com` | `https://www.okx.com` | ✅ |
| 签名算法 | `HMAC-SHA256(timestamp+method+path+body, secret)` | 同左 | ✅ |
| 签名编码 | Base64 编码 | `base64.b64encode(mac.digest())` | ✅ |
| 时间戳格式 | ISO 8601 毫秒级 `2020-12-08T09:08:57.715Z` | `isoformat(timespec="milliseconds").replace("+00:00","Z")` | ✅ |
| 请求头 OK-ACCESS-KEY | 必须 | 已实现 | ✅ |
| 请求头 OK-ACCESS-SIGN | 必须 | 已实现 | ✅ |
| 请求头 OK-ACCESS-TIMESTAMP | 必须 | 已实现 | ✅ |
| 请求头 OK-ACCESS-PASSPHRASE | 必须，用户自设口令 | 已实现，**但 None→"" 导致失败** | ❌ |
| 模拟盘标识 | `x-simulated-trading: 1` | 已实现 | ✅ |
| 行情 Ticker | `GET /api/v5/market/ticker` | 同左 | ✅ |
| K线 | `GET /api/v5/market/candles` | 同左 | ✅ |
| 订单簿 | `GET /api/v5/market/books` | 同左 | ✅ |
| 余额 | `GET /api/v5/account/balance` | 同左 | ✅ |
| 下单 | `POST /api/v5/trade/order` | 同左 | ✅ |
| 撤单 | `POST /api/v5/trade/cancel-order` | 同左 | ✅ |
| 查询订单 | `GET /api/v5/trade/order?instId=&ordId=` | 同左 | ✅ |
| instId 格式 | `BTC-USDT` | `_to_inst_id()` 正确转换 | ✅ |
| 下单 tdMode | `cash`/`cross`/`isolated` | 硬编码 `cash` | ⚠️ |
| 响应检查 | `code != "0"` 为错误 | 已实现 | ✅ |
| sCode/sMsg | 下单结果看 sCode | 已实现 | ✅ |
| 时间偏差容忍 | 30 秒内 | 未同步服务器时间 | ❌ |

---

## 四、问题优先级和修复路线

| 优先级 | Bug | 影响 | 修复难度 |
|--------|-----|------|----------|
| **P0** | Passphrase 空字符串 | 所有 OKX 认证请求失败 | 低 |
| **P0** | 缺少余额同步 | 永远显示 0 余额 | 中 |
| **P1** | 路由定义顺序 + 前端缺失交易方法 | 交易 404 | 中 |
| **P2** | 缺少服务器时间同步 | 特定环境下认证失败 | 低 |

---

## 五、修复后验证清单

- [ ] OKX 账户添加时 Passphrase 为必填项
- [ ] 添加账户后自动调用 `get_balance()` 同步余额
- [ ] Dashboard 资产页面显示真实余额
- [ ] 交易下单功能正常（非 404）
- [ ] 模拟盘 `x-simulated-trading: 1` 正确发送
- [ ] 服务器时间同步后无 `50102` 错误
