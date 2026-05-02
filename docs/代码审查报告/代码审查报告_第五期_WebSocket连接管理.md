# Crypto-Quant-App 代码审查报告（第五期：WebSocket 连接管理）

**审查时间**: 2026-05-02
**审查范围**: ws/manager.py · ws/proxies.py · ws/endpoints.py
**严重程度**: 🔴 严重 · 🟠 中等 · 🟡 轻微

---

## 一、严重安全与稳定性问题

### 🔴 1. 【严重】WebSocket 连接数限制仅基于 user_id —— 同一用户多标签可耗尽所有连接槽

**文件**: `endpoints.py:51-53`

```python
user_conn_count = sum(1 for sub in manager._subs.values() if sub.user_id == user_id)
if user_conn_count >= 5:
    await websocket.close(code=4002, reason="Too many connections (max 5)")
    return
```

**问题**: 限制的是"同一个 user_id 的连接数"，而非"全局连接数"。在多标签页场景下：
- 用户打开 5 个标签页后，任何一个标签页的 WS 连接都会因为达到上限而被拒绝
- 更重要的是：**全局没有最大连接数限制**。不同用户可以创建无限连接（只受系统 FD 上限约束），耗尽服务器资源
- `conn_id` 用 `id(websocket)` + 时间戳生成，不保证唯一性（极端情况下两个 socket 的 Python 对象 id 可能相同）

**修复建议**: 增加全局连接数上限，按 IP 或 user_id 分别限制。

---

### 🔴 2. 【严重】WebSocket 认证消息未加密传输 —— Token 可能在日志/中间节点泄露

**文件**: `endpoints.py:23-36`

```python
# 等待首条 auth 消息（Token 不再走 URL，防止泄露到日志/Referer）
token = ""
try:
    raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
    cmd = json.loads(raw)
    if cmd.get("action") == "auth":
        token = cmd.get("token", "")  # ← Token 以明文 JSON 传输
```

**问题**: Token 以明文 JSON 字符串在 WebSocket 消息体中传输。虽然避免了 URL 参数泄露，但存在以下风险：
- WebSocket 升级后的明文 HTTP 头可能被中间节点记录
- `manage._subs` 中存储了 `user_id`，但没有任何加密或签名验证
- 没有 `conn_id` 级别的签名，任何知道 user_id 的人都可以连接
- `sub.user_id` 存储为字符串，但 Token 解析后是 `payload.get("sub")`，类型不明确

**修复建议**: 使用子协议（Sec-WebSocket-Protocol）传输认证信息，或使用 HMAC 签名挑战机制。

---

### 🔴 3. 【严重】WebSocket 连接异常后无心跳保活 —— 僵尸连接占用资源

**文件**: `proxies.py:96` · `endpoints.py:88-129`

```python
# BinanceWSProxy
async with websockets.connect(url, ping_interval=20) as ws:  # ← 20s ping interval
    async for raw in ws:  # ← 无超时，无心跳检测
        ...
```

```python
# endpoints.py 的主循环
while True:
    raw = await websocket.receive_text()  # ← 无超时，无心跳保活
    cmd = json.loads(raw)
    if action == "ping":
        await websocket.send_text(...)
```

**问题**:
- Binance/OKX/Huobi 的 WebSocket 都只设置了 `ping_interval=20`，但实际的数据循环中若交易所 WebSocket 服务端未响应，`async for` 会一直等待
- `endpoints.py` 中主 WebSocket 循环没有心跳超时机制。如果客户端网络中断，服务端不会主动检测到连接断开（依赖底层的 TCP keepalive，但间隔不可控）
- `_run_stream` 中的 `async for raw in ws:` 在网络断开时会抛出异常，但主循环中没有类似的保活机制
- `manager._subs` 中存储的 `sub.ws` 可能是已断开的引用，`get_subscribers` 返回的 WebSocket 可能已经是死连接

**修复建议**: 添加主动心跳（定期发送 ping + 等待 pong，超时认为断连），定期清理 `manager._subs` 中的僵尸连接。

---

## 二、代理层逻辑问题

### 🟠 4. 【中等】订阅键缺少 market_type 维度 —— Spot 与 Perp 数据可能互串

**文件**: `manager.py:25` · `manager.py:68-75` · `proxies.py:24`

```python
# manager.py:25
self._routing: dict[tuple[str, str], set[str]] = defaultdict(set)
# ↑ 键是 (channel, symbol)，没有 market_type！

# manager.py:68-75
def get_subscribers(self, channel: str, symbol: str) -> list[WebSocket]:
    conn_ids = self._routing.get((channel, symbol.upper()), set())  # ← 无 market_type
    # BTCUSDT spot 的订阅者和 BTCUSDT perp 的订阅者混在一起
```

```python
# proxies.py:24
def _stream_key(channel: str, symbol: str, market_type: str) -> str:
    return f"{channel}:{symbol}:{market_type}"  # ← 代理层用了 market_type
```

**问题**:
- `manager._routing` 用 `(channel, symbol)` 做键，不区分 spot 和 perp
- 但 `_routing` 是 `manager` 的数据结构，`get_subscribers` 查 `(channel, symbol)` 时不会传 market_type
- 后果：**订阅 BTCUSDT perp 的用户会收到 BTCUSDT spot 的数据**（反之亦然），数据互串

**修复建议**: 将 `manager._routing` 的键改为 `(channel, symbol, market_type)`，并在 `subscribe/unsubscribe/get_subscribers` 中传递 market_type。

---

### 🟠 5. 【中等】Binance WebSocket K线频道硬编码 1 分钟周期 —— 无法订阅其他周期

**文件**: `proxies.py:89-91`

```python
stream = f"{symbol_lower}@ticker" if channel == "ticker" else          f"{symbol_lower}@kline_1m" if channel == "kline" else          f"{symbol_lower}@depth20@100ms"
```

**问题**: 策略可能需要 5 分钟、15 分钟、1 小时的 K 线，但当前硬编码为 1 分钟。前端无法请求其他周期的实时 K 线数据。

---

### 🟠 6. 【中等】重连退避策略固定 5 秒 —— 可能被交易所限流

**文件**: `proxies.py:69-76`

```python
async def _restart_on_error(self, channel: str, symbol: str, market_type: str) -> None:
    await asyncio.sleep(5)  # ← 固定 5 秒，不指数退避
    if self._manager.has_subscribers(channel, symbol):
        self._tasks.pop(_stream_key(channel, symbol, market_type), None)
        await self.start_if_needed(channel, symbol, market_type)
```

**问题**: 固定 5 秒重连，如果连接因限流断开，5 秒后立即重连可能被二次限流。没有指数退避（5s → 10s → 20s → 60s）。

---

### 🟠 7. 【中等】PollingFallback 初始化时无 API Key —— 无法访问私有数据

**文件**: `proxies.py:300-303`

```python
async def _poll_loop(self) -> None:
    from app.core.exchanges.binance import BinanceAdapter
    adapter = BinanceAdapter("", "")  # ← 空 API Key，只能访问公开数据
```

**问题**: PollingFallback 作为 websockets 不可用时的降级方案，用空 API Key 初始化 Adapter。这意味着它只能拉公开行情数据（ticker），无法获取账户私有数据（余额、持仓）。

---

## 三、路由与订阅管理问题

### 🟡 8. 【轻微】`unregister` 后未通知对应 Proxy 停止空闲 Stream

**文件**: `manager.py:32-41`

```python
def unregister(self, conn_id: str) -> None:
    sub = self._subs.pop(conn_id, None)
    if sub:
        for channel in sub.channels:
            for symbol in sub.symbols:
                key = (channel, symbol)
                self._routing[key].discard(conn_id)
                if not self._routing[key]:
                    del self._routing[key]
        # ← 注意：只删除了 routing 记录，但没有通知 proxy.stop_if_idle()
        # 如果最后一个订阅者退出了，proxy 的 _tasks 中的 stream 不会自动停止
```

**问题**: 当最后一个订阅者退订后，`_routing` 记录被删除，但 `Proxy._tasks` 中的 `asyncio.Task` 不会自动取消（需要外部调用 `stop_if_idle`）。虽然在 `endpoints.py:119-122` 的 unsubscribe 动作中有调用，但直接关闭浏览器标签页触发 `unregister` 时，`Proxy._tasks` 不会停止。

---

### 🟡 9. 【轻微】`subscribe` 时未检查 Proxy 是否已注册

**文件**: `endpoints.py:103-107`

```python
p = manager._proxies.get(exchange)
if p:
    for ch in channels:
        for sym in symbols:
            await p.start_if_needed(ch, sym, market_type=market)
```

**问题**: 只检查 `if p`（proxy 存在），不检查 `if p._tasks`（task 已存在）。`start_if_needed` 内部有检查，但逻辑分散。更重要的是：**如果 proxy 不存在（如交易所不支持），静默跳过，没有任何提示给客户端**。

---

### 🟡 10. 【轻微】Huobi WebSocket 使用 GZIP 解压但未处理错误

**文件**: `proxies.py:232`

```python
decompressed = gzip.decompress(raw).decode("utf-8") if isinstance(raw, bytes) else raw
```

**问题**: 如果数据不是 GZIP 格式（如普通 JSON 文本），`gzip.decompress` 会抛出异常。没有 `try/except` 包裹。火币 WebSocket 某些消息可能不压缩。

---

## 四、初始化与清理问题

### 🟠 11. 【中等】`init_ws_proxies` 在启动失败时静默降级为轮询 —— 无告警

**文件**: `endpoints.py:170-178`

```python
async def init_ws_proxies():
    try:
        import websockets
        manager.register_proxy("binance", BinanceWSProxy(manager))
        manager.register_proxy("okx", OKXProxy(manager))
        manager.register_proxy("huobi", HuobiProxy(manager))
    except ImportError:  # ← 只捕获 ImportError
        polling = PollingFallback(manager)
        await polling.start()  # ← 静默降级，没有任何日志或告警
```

**问题**: `except ImportError` 只捕获 websockets 库不存在的情况。但如果：
- 网络错误导致连接失败
- 交易所 WebSocket 服务不可用
- 其他未知异常

都不会触发降级，而且没有任何告警。运维人员不知道 WS 模式是否正常。

---

## 五、总结

| # | 严重程度 | 分类 | 文件 | 问题 |
|---|---------|------|------|------|
| 1 | 🔴 严重 | 安全 | endpoints.py:51 | 全局无连接数限制，单用户多标签耗尽资源 |
| 2 | 🔴 严重 | 安全 | endpoints.py:28 | Token 明文传输，无连接级别签名 |
| 3 | 🔴 严重 | 稳定性 | proxies.py:96 | 无心跳保活，僵尸连接占用资源 |
| 4 | 🟠 中等 | 逻辑 | manager.py:25 | 订阅键缺少 market_type，Spot/Perp 数据互串 |
| 5 | 🟠 中等 | 功能 | proxies.py:89 | K线频道硬编码1分钟，无法订阅其他周期 |
| 6 | 🟠 中等 | 稳定性 | proxies.py:69 | 重连固定5秒，无指数退避 |
| 7 | 🟠 中等 | 功能 | proxies.py:301 | PollingFallback 无API Key，私有数据不可用 |
| 8 | 🟠 中等 | 稳定性 | endpoints.py:170 | ImportError 外静默降级，无告警 |
| 9 | 🟡 轻微 | 逻辑 | manager.py:32 | unregister 不停止空闲 stream task |
| 10 | 🟡 轻微 | 逻辑 | endpoints.py:103 | proxy 不存在时静默跳过 |
| 11 | 🟡 轻微 | 健壮 | proxies.py:232 | GZIP解压无错误处理 |

**第五期总计**: 🔴 严重×3 · 🟠 中等×5 · 🟡 轻微×3

**五期总合计**: 🔴 严重×9 · 🟠 中等×34 · 🟡 轻微×26
