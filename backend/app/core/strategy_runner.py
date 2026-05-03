"""
实时策略运行器

职责：
- 管理 running 状态的策略实例
- 定期从交易所获取K线数据喂给策略引擎
- 收到信号后调用 OrderService 执行交易
- 更新策略实例的统计字段（total_pnl, win_rate, total_trades）

架构:
  StrategyRunner（单例）
    ├── _runners: dict[instance_id → asyncio.Task]
    ├── 启动时加载所有 running 实例
    ├── 每个实例一个 asyncio.Task 循环:
    │     1. 获取K线（exchange_adapter.get_klines）
    │     2. 调用 strategy.analyze(klines)
    │     3. 如果有信号 → OrderService.create_order + submit_order
    │     4. 更新统计 → strategy_instance.total_pnl 等
    │     5. sleep(interval) 后重复
    └── 关闭时清理所有 Task
"""

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.strategy_engine import (
    BaseStrategy,
    Signal,
    StrategyConfig,
    get_strategy,
)
from app.core.trade_schemas import WSMessage
from app.models.strategy import StrategyInstance

logger = logging.getLogger(__name__)


# K 线周期 → 推荐轮询节奏(秒)
# 思路:每根 K 线封盘附近触发一次 analyze,既不延迟太多也不过度频繁。
# 短周期为减少封盘漏触发取约 1/2 K 线长度,长周期取 1/4 K 线长度封顶 5 分钟。
_KLINE_INTERVAL_TO_POLL_SECONDS = {
    "1m": 30,
    "5m": 60,
    "15m": 120,
    "30m": 180,
    "1h": 300,
    "4h": 300,
    "1d": 300,
}


def _normalize_kline_timestamp(value: Any) -> int:
    """统一 K 线时间戳为毫秒整数。"""
    if value is None:
        return 0
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _kline_poll_seconds(kline_interval: str) -> int:
    """根据 K 线周期返回推荐的轮询节奏(秒)。"""
    return _KLINE_INTERVAL_TO_POLL_SECONDS.get(kline_interval, 60)


# 信号 metadata.intent 取值,与 RsiLayered 等富语义策略对齐:
#   open                            开新仓
#   add                             加仓 — 与开仓走同一路径(余额自然递减)
#   take_profit/stop_loss/timeout   平掉现有持仓 → _auto_close_position
#   reverse                         反手(先平再开) → _auto_reverse_position
# 其他 intent 或缺省 metadata → 退回到 signal.action 旧路径
CLOSE_INTENTS = frozenset({"take_profit", "stop_loss", "timeout"})


def select_position_to_close(
    positions: list,
    instance_id: int,
    direction: str | None,
):
    """从开仓 Position 列表里选出本次平仓的目标。

    抽成纯函数便于单测。规则:
      1. 列表为空 → 返回 None
      2. 优先匹配 strategy_instance_id == instance_id 的(该实例自己开的)
      3. 再用 direction(long/short) 过滤,过滤后无结果就回退到上一步
      4. 取第一个;有多个时调用方应该 log warning

    Args:
        positions: 已查到的 status=open 的 Position 列表
        instance_id: 当前策略实例 ID
        direction: metadata.direction("long" / "short" / None)

    Returns:
        选中的 Position 或 None
    """
    if not positions:
        return None

    same_instance = [p for p in positions if p.strategy_instance_id == instance_id]
    candidates = same_instance or positions

    if direction in ("long", "short"):
        filtered = [p for p in candidates if p.side == direction]
        if filtered:
            candidates = filtered

    return candidates[0] if candidates else None


class StrategyRunner:
    """实时策略运行器 — 单例模式"""

    _instance: "StrategyRunner | None" = None

    def __new__(cls) -> "StrategyRunner":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        # instance_id → asyncio.Task
        self._runners: dict[int, asyncio.Task] = {}
        # instance_id → BaseStrategy（有状态策略如马丁格尔需要保持）
        self._strategies: dict[int, BaseStrategy] = {}
        # instance_id → 上次信号时间（防抖：同策略 60s 内不重复发信号）
        self._last_signal_at: dict[int, datetime] = {}
        self._last_runtime_error: dict[int, str] = {}
        self._last_runtime_error_at: dict[int, datetime] = {}
        self._running = False
        self._session_maker = None
        # K线请求去重: (exchange, symbol, interval) → (timestamp, klines)
        self._kline_cache: dict[tuple[str, str, str], tuple[float, list[dict]]] = {}
        # K线请求 flight lock: (exchange, symbol, interval) → asyncio.Event
        self._kline_locks: dict[tuple[str, str, str], asyncio.Event | None] = {}
        # 交易对最小下单量缓存（评审问题2：不再硬编码白名单）
        self._symbol_min_qty_cache: dict[tuple[str, str], Decimal] = {}
        # 余额同步防抖：account_id → last_sync_ts
        self._balance_sync_at: dict[int, float] = {}

    async def start(self, session_maker) -> None:
        """启动运行器，加载所有 running 状态的策略实例"""
        if self._running:
            return
        self._running = True
        self._session_maker = session_maker

        async with session_maker() as session:
            result = await session.execute(
                select(StrategyInstance)
                .where(StrategyInstance.status == "running")
                .options(joinedload(StrategyInstance.template))
            )
            instances = result.scalars().all()

        for inst in instances:
            await self._start_instance(inst)

        logger.info("[StrategyRunner] 启动，加载 %d 个运行中策略", len(instances))

    async def stop(self) -> None:
        """停止所有策略运行"""
        self._running = False
        for inst_id, task in list(self._runners.items()):
            task.cancel()
            logger.info("[StrategyRunner] 停止策略 #%d", inst_id)
        self._runners.clear()
        self._strategies.clear()
        self._last_signal_at.clear()

    async def start_instance(self, instance_id: int) -> bool:
        """启动单个策略实例"""
        existing_task = self._runners.get(instance_id)
        if existing_task and not existing_task.done():
            logger.warning("[StrategyRunner] 策略 #%d 已在运行", instance_id)
            return False
        if existing_task and existing_task.done():
            self._forget_instance(instance_id, existing_task)
            logger.warning("[StrategyRunner] 策略 #%d 检测到僵尸任务，已清理后重启", instance_id)

        async with self._session_maker() as session:
            result = await session.execute(
                select(StrategyInstance)
                .where(StrategyInstance.id == instance_id)
                .options(joinedload(StrategyInstance.template))
            )
            inst = result.scalar_one_or_none()

        if not inst:
            return False

        await self._start_instance(inst)
        return True

    async def stop_instance(self, instance_id: int) -> None:
        """停止单个策略实例"""
        task = self._runners.pop(instance_id, None)
        if task:
            task.cancel()
            self._strategies.pop(instance_id, None)
            self._last_signal_at.pop(instance_id, None)
            logger.info("[StrategyRunner] 策略 #%d 已停止", instance_id)

    async def restart_instance(self, instance_id: int) -> bool:
        """重启策略实例（用于参数更新后热加载）

        stop_instance 将 task 从 _runners 移除 + cancel，
        start_instance 从 DB 重新读取实例创建新 task，
        二者操作不同对象，无竞态。
        """
        await self.stop_instance(instance_id)
        return await self.start_instance(instance_id)

    def _forget_instance(self, instance_id: int, task: asyncio.Task | None = None) -> None:
        current = self._runners.get(instance_id)
        if task is None or current is task:
            self._runners.pop(instance_id, None)
        self._strategies.pop(instance_id, None)
        self._last_signal_at.pop(instance_id, None)

    def _handle_task_done(self, instance_id: int, task: asyncio.Task) -> None:
        self._forget_instance(instance_id, task)

        if task.cancelled():
            return

        exc = task.exception()
        if exc is None:
            if self._running:
                message = "runner task exited unexpectedly"
                self._last_runtime_error[instance_id] = message
                self._last_runtime_error_at[instance_id] = datetime.now(UTC)
                logger.warning("[StrategyRunner] 策略 #%d 任务异常结束", instance_id)
                asyncio.create_task(self._mark_instance_stopped(instance_id, message))
            return

        message = str(exc)
        self._last_runtime_error[instance_id] = message
        self._last_runtime_error_at[instance_id] = datetime.now(UTC)
        logger.error("[StrategyRunner] 策略 #%d 任务崩溃: %s", instance_id, exc)
        if self._running:
            asyncio.create_task(self._mark_instance_stopped(instance_id, message))

    async def _mark_instance_stopped(self, instance_id: int, reason: str) -> None:
        if not self._session_maker:
            return
        try:
            async with self._session_maker() as session:
                result = await session.execute(
                    select(StrategyInstance).where(StrategyInstance.id == instance_id)
                )
                inst = result.scalar_one_or_none()
                if not inst or inst.status != "running":
                    return
                inst.status = "stopped"
                inst.workspace_state = "library"
                inst.last_stopped_at = datetime.now(UTC)
                await session.commit()
                logger.warning(
                    "[StrategyRunner] 策略 #%d 已自动标记为 stopped: %s",
                    instance_id,
                    reason,
                )
        except Exception as exc:
            logger.warning("[StrategyRunner] 自动校正策略 #%d 状态失败: %s", instance_id, exc)

    async def _start_instance(self, inst: StrategyInstance) -> None:
        """内部：为策略实例创建运行 Task"""
        # 从模板的 strategy_type 创建策略引擎实例
        strategy_type = inst.template.strategy_type if inst.template else "ma"
        config = StrategyConfig(
            symbol=inst.symbol,
            exchange=inst.exchange,
            direction=inst.direction or "both",
            params=inst.params or {},
            risk_params=inst.risk_params or {},
        )

        try:
            strategy = get_strategy(strategy_type, config)
        except ValueError:
            logger.error("[StrategyRunner] 不支持的策略类型: %s (实例 #%d)", strategy_type, inst.id)
            return

        # Step 3: 启动时从 DB 恢复策略状态机(重启不丢仓位/极值/cooling)
        if inst.state_json:
            try:
                # 评审问题5: 恢复前校验关键字段
                state = inst.state_json
                mode = state.get("mode", "monitoring")
                if mode not in ("monitoring", "long", "short", "cooling"):
                    logger.warning(
                        "[StrategyRunner] 策略 #%d 状态 mode=%s 非法,重置为 monitoring",
                        inst.id,
                        mode,
                    )
                    state = {}
                strategy.from_dict(state)
                logger.info(
                    "[StrategyRunner] 策略 #%d 状态已从 DB 恢复 (mode=%s)",
                    inst.id,
                    mode if state else "monitoring",
                )
            except Exception as exc:
                # 恢复失败不阻塞启动 — 退化为从零开始,记录告警
                logger.warning(
                    "[StrategyRunner] 策略 #%d 状态恢复失败,从零开始: %s",
                    inst.id,
                    exc,
                )

        # 评审问题9: 启动时从 DB 同步真实持仓状态，覆盖策略内部状态
        if inst.account_id and strategy_type == "rsi_layered":
            await self._sync_strategy_state_from_db(inst.id, inst.account_id, inst.symbol, strategy)

        self._strategies[inst.id] = strategy
        self._last_runtime_error.pop(inst.id, None)
        self._last_runtime_error_at.pop(inst.id, None)
        task = asyncio.create_task(
            self._run_loop(inst.id, strategy, config),
            name=f"strategy-runner-{inst.id}",
        )
        task.add_done_callback(lambda done_task, inst_id=inst.id: self._handle_task_done(inst_id, done_task))
        self._runners[inst.id] = task
        logger.info(
            "[StrategyRunner] 策略 #%d (%s/%s) 已启动",
            inst.id,
            strategy_type,
            inst.symbol,
        )

    async def _run_loop(
        self, instance_id: int, strategy: BaseStrategy, config: StrategyConfig
    ) -> None:
        """策略运行主循环"""
        # K 线周期 — 决定信号触发的时间精度,与回测一致
        kline_interval = str(config.params.get("kline_interval", "1h"))
        # 轮询节奏跟 K 线周期对齐:每根 K 线封盘前后再触发一次分析
        # 1m → 30s 轮询(更频繁追新封盘)、5m+ → 半根 K 线长度
        poll_interval = _kline_poll_seconds(kline_interval)
        # 兼容旧参数:若用户显式给了 interval(秒),仍尊重之
        interval = int(config.params.get("interval", poll_interval))
        kline_limit = 100  # 获取最近 100 根 K 线

        while self._running:
            try:
                # 1. 获取 K 线数据（去重缓存：同交易对+周期的策略共享请求）
                klines = await self._fetch_klines_cached(
                    config.exchange,
                    config.symbol,
                    kline_limit,
                    kline_interval,
                    cache_ttl_seconds=max(30, interval // 2),
                )

                if not klines:
                    await asyncio.sleep(interval)
                    continue

                # 2. 调用策略分析
                signal = await strategy.analyze(klines)

                # 3. 处理信号
                if signal:
                    await self._handle_signal(instance_id, signal, config)

                # 4. 更新持仓价格 — P0-2: 持仓价格自动刷新
                #    同时把信号（含止损/止盈价格）传下去（评审问题3：动态止损/止盈）
                if klines:
                    current_price = Decimal(str(klines[-1]["close"]))
                    await self._update_position_prices(
                        instance_id, config.symbol, current_price, signal=signal
                    )

                # 5. 更新 last_run_at + Step 3: 持久化策略状态
                await self._update_last_run_and_state(instance_id, strategy)

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                logger.info("[StrategyRunner] 策略 #%d 运行任务被取消", instance_id)
                break
            except Exception as exc:
                logger.error("[StrategyRunner] 策略 #%d 运行异常: %s", instance_id, exc)
                # 评审问题10: 区分异常类型，缩短网络抖动重试间隔
                retry_delay = self._calc_retry_delay(exc, interval)
                logger.info(
                    "[StrategyRunner] 策略 #%d 异常重试,等待 %.1f 秒",
                    instance_id,
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)

    async def _fetch_klines_cached(
        self,
        exchange: str,
        symbol: str,
        limit: int,
        interval: str = "1h",
        cache_ttl_seconds: int = 60,
    ) -> list[dict]:
        """获取 K 线数据，带内存缓存去重

        多策略共享同一交易对+周期时，合并为一次 API 请求。
        使用 asyncio Event 作为飞行锁，避免并发重复请求。
        """
        import time

        cache_key = (exchange, symbol, interval)
        now = time.time()

        # 缓存命中 → 直接返回
        if cache_key in self._kline_cache:
            cached_at, cached_data = self._kline_cache[cache_key]
            if now - cached_at < cache_ttl_seconds:
                logger.debug(
                    "[StrategyRunner] K线缓存命中: %s/%s/%s (%.1fs 前)",
                    exchange,
                    symbol,
                    interval,
                    now - cached_at,
                )
                return cached_data

        # 飞行锁: 已有在途请求 → 等待它完成
        inflight = self._kline_locks.get(cache_key)
        if inflight is not None:
            logger.debug(
                "[StrategyRunner] K线请求已在进行中，等待: %s/%s/%s",
                exchange,
                symbol,
                interval,
            )
            await inflight.wait()
            # 请求完成后从缓存读
            if cache_key in self._kline_cache:
                return self._kline_cache[cache_key][1]

        # 无缓存且无在途请求 → 发起新请求
        lock = asyncio.Event()
        self._kline_locks[cache_key] = lock
        try:
            klines = await self._fetch_klines(exchange, symbol, limit, interval)
            if klines:
                self._kline_cache[cache_key] = (now, klines)
            return klines
        finally:
            self._kline_locks.pop(cache_key, None)
            lock.set()  # 唤醒所有等待者

    async def _fetch_klines(
        self, exchange: str, symbol: str, limit: int, interval: str = "1h"
    ) -> list[dict]:
        """从交易所获取 K 线数据(按策略配置的 kline_interval)"""
        try:
            from app.core.exchange_adapter import get_exchange_adapter

            # 使用公开数据不需要 API Key，传入空字符串
            adapter = get_exchange_adapter(
                exchange=exchange,
                api_key="",
                secret_key="",
            )
            klines = await adapter.get_klines(symbol, interval=interval, limit=limit)
            return [
                {
                    "open": float(k.open),
                    "high": float(k.high),
                    "low": float(k.low),
                    "close": float(k.close),
                    "volume": float(k.volume),
                    "timestamp": _normalize_kline_timestamp(k.timestamp),
                }
                for k in klines
            ]
        except Exception as exc:
            logger.warning("[StrategyRunner] 获取K线失败 %s/%s: %s", exchange, symbol, exc)
            return []

    async def _handle_signal(
        self, instance_id: int, signal: Signal, config: StrategyConfig
    ) -> None:
        """处理策略信号：持久化信号 + WS推送 + 通知 + 自动下单"""
        # 防抖：60 秒内同策略不重复发信号
        now = datetime.now(UTC)
        last = self._last_signal_at.get(instance_id)
        if last and (now - last).total_seconds() < 60:
            return

        self._last_signal_at[instance_id] = now

        logger.info(
            "[StrategyRunner] 策略 #%d 产生信号: action=%s, confidence=%.2f, reason=%s",
            instance_id,
            signal.action,
            signal.confidence,
            signal.reason,
        )

        # ① 持久化信号到数据库
        signal_id = await self._persist_signal(instance_id, signal, config)

        # ② 通过 WebSocket 推送信号通知
        try:
            from app.api.v1.ws_market import manager

            msg = WSMessage(
                type="signal",
                exchange=config.exchange,
                symbol=config.symbol,
                data={
                    "instance_id": instance_id,
                    "signal_id": signal_id,
                    "action": signal.action,
                    "confidence": signal.confidence,
                    "entry_price": str(signal.entry_price) if signal.entry_price else None,
                    "stop_loss_price": str(signal.stop_loss_price)
                    if signal.stop_loss_price
                    else None,
                    "take_profit_price": str(signal.take_profit_price)
                    if signal.take_profit_price
                    else None,
                    "reason": signal.reason,
                },
            )
            subscribers = manager.get_subscribers("signal", config.symbol)
            for ws in subscribers:
                with suppress(Exception):
                    await ws.send_text(msg.model_dump_json())
        except Exception as exc:
            logger.debug("[StrategyRunner] WS 推送信号失败: %s", exc)

        # ③ 推送通知（Telegram/企微）— P0-1: 信号通知系统
        try:
            from app.services.notification_service import notify_signal

            await notify_signal(
                symbol=config.symbol,
                action=signal.action,
                confidence=signal.confidence,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss_price,
                take_profit=signal.take_profit_price,
                reason=signal.reason,
                strategy_name=config.params.get("strategy_name", f"策略#{instance_id}"),
            )
        except Exception as exc:
            logger.warning("[StrategyRunner] 通知推送失败: %s", exc)

        # ④ 自动下单（需要用户在策略参数中开启 auto_trade + 绑定账户）
        auto_trade = config.params.get("auto_trade", False)
        if not auto_trade:
            logger.info("[StrategyRunner] 策略 #%d auto_trade 未开启，跳过自动下单", instance_id)
            return

        await self._auto_trade(instance_id, signal, config, signal_id)

    async def _persist_signal(
        self, instance_id: int, signal: Signal, config: StrategyConfig
    ) -> int | None:
        """将信号写入数据库，返回 signal_id"""
        try:
            async with self._session_maker() as session:
                from app.models.order import Signal as SignalModel

                db_signal = SignalModel(
                    strategy_instance_id=instance_id,
                    symbol=config.symbol,
                    action=signal.action,
                    confidence=Decimal(str(round(signal.confidence, 4))),
                    entry_price=signal.entry_price,
                    stop_loss_price=signal.stop_loss_price,
                    take_profit_price=signal.take_profit_price,
                    status="pending",
                    reason=signal.reason,
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
                session.add(db_signal)
                await session.commit()
                await session.refresh(db_signal)
                logger.info(
                    "[StrategyRunner] 信号已持久化: signal_id=%d, action=%s",
                    db_signal.id,
                    signal.action,
                )
                return db_signal.id
        except Exception as exc:
            logger.error("[StrategyRunner] 信号持久化失败: %s", exc)
            return None

    async def _auto_trade(
        self,
        instance_id: int,
        signal: Signal,
        config: StrategyConfig,
        signal_id: int | None,
    ) -> None:
        """自动下单：查找绑定的交易所账户 → 创建订单 → 提交到交易所"""
        try:
            async with self._session_maker() as session:
                # 查找策略实例及其绑定的账户
                result = await session.execute(
                    select(StrategyInstance).where(StrategyInstance.id == instance_id)
                )
                inst = result.scalar_one_or_none()
                if not inst:
                    logger.error("[StrategyRunner] 策略实例 #%d 不存在", instance_id)
                    return

                if not inst.account_id:
                    logger.warning(
                        "[StrategyRunner] 策略 #%d 未绑定交易所账户，无法自动下单",
                        instance_id,
                    )
                    # 更新信号状态为 rejected
                    if signal_id:
                        await self._update_signal_status(
                            signal_id, "rejected", reason="未绑定交易所账户"
                        )
                    return

                # 获取绑定的交易所账户
                from app.models.exchange import ExchangeAccount

                acct_result = await session.execute(
                    select(ExchangeAccount).where(ExchangeAccount.id == inst.account_id)
                )
                account = acct_result.scalar_one_or_none()
                if not account or not account.is_active or account.user_id != inst.user_id:
                    logger.warning(
                        "[StrategyRunner] 策略 #%d 绑定的账户 #%d 不可用",
                        instance_id,
                        inst.account_id,
                    )
                    if signal_id:
                        await self._update_signal_status(
                            signal_id, "rejected", reason="交易所账户不可用"
                        )
                    return

                # ── intent 路由(Step 2a) ────────────────────────
                # 富语义策略(如 RsiLayered)在 metadata.intent 里告诉我们
                # 这是开仓/加仓/平仓/反手。没 metadata 的旧策略走旧路径。
                meta = signal.metadata or {}
                intent = meta.get("intent")
                direction = meta.get("direction")

                if intent in CLOSE_INTENTS:
                    await self._auto_close_position(
                        session=session,
                        instance_id=instance_id,
                        account=account,
                        config=config,
                        user_id=inst.user_id,
                        direction=direction,
                        intent=intent,
                        signal_id=signal_id,
                    )
                    return

                # 反手 (Step 2b): 先平掉现有仓,再开反向仓
                if intent == "reverse":
                    await self._auto_reverse_position(
                        session=session,
                        instance_id=instance_id,
                        account=account,
                        config=config,
                        user_id=inst.user_id,
                        signal=signal,
                        signal_id=signal_id,
                    )
                    return

                # 加仓 (intent=add): 与开仓逻辑一致 — 在同方向再开一单。
                # 余额自然递减,策略层用 max_additional_positions 控制次数。
                # open / add / 无 metadata / 旧策略(MA/Rule) 全走这里。

                await self._auto_open_position(
                    session=session,
                    instance_id=instance_id,
                    account=account,
                    config=config,
                    user_id=inst.user_id,
                    signal=signal,
                    signal_id=signal_id,
                )

        except Exception as exc:
            logger.error("[StrategyRunner] 策略 #%d 自动下单失败: %s", instance_id, exc)
            if signal_id:
                with suppress(Exception):
                    await self._update_signal_status(signal_id, "rejected", reason=str(exc))

    async def _auto_open_position(
        self,
        *,
        session,
        instance_id: int,
        account,
        config: StrategyConfig,
        user_id: int,
        signal: Signal,
        signal_id: int | None,
    ) -> bool:
        """开仓 / 加仓: 把信号转换成市价单提交到交易所。

        side 决策:
          - signal.action ∈ {buy, sell} → 直接使用
          - signal.action == "close" → 查持仓决定反向(向后兼容旧策略)
          - 其他 → 拒绝

        Returns:
            True  — 订单已提交成功
            False — 跳过/拒绝/失败
        """
        from app.services.order_service import OrderService

        # 决定 side
        if signal.action in ("buy", "sell"):
            side = signal.action
        elif signal.action == "close":
            # 旧路径: 没 metadata.intent 但 action=close 的策略,查持仓反推方向
            from app.models.exchange import Position

            pos_result = await session.execute(
                select(Position).where(
                    Position.account_id == account.id,
                    Position.symbol == config.symbol,
                    Position.status == "open",
                )
            )
            position = pos_result.scalar_one_or_none()
            if not position:
                logger.info("[StrategyRunner] 策略 #%d close 信号但无持仓,跳过", instance_id)
                return False
            side = "sell" if position.side == "long" else "buy"
        else:
            logger.warning("[StrategyRunner] 未知信号动作: %s", signal.action)
            return False

        # 评审问题8：先同步余额，避免使用过期余额计算下单量
        import time

        acct_id = account.id
        now = time.time()
        last_sync = self._balance_sync_at.get(acct_id, 0)
        if now - last_sync > 60:  # 60 秒内不同步第二次
            try:
                from app.services.order_service import OrderService

                svc = OrderService(session)
                account = await svc.sync_account_balance(acct_id)
                self._balance_sync_at[acct_id] = now
            except Exception as exc:
                logger.warning(
                    "[StrategyRunner] 余额同步失败,使用缓存余额: %s",
                    exc,
                )

        # 评审问题2：从交易所 API 获取真实 min_qty
        min_qty = await self._get_symbol_min_qty(config.exchange, config.symbol)

        # 计算下单数量
        max_invest_pct = Decimal(str(config.params.get("max_invest_percent", 30))) / 100
        quantity = self._calculate_order_quantity(
            account.balance,
            signal.entry_price,
            config.symbol,
            side,
            max_invest_pct,
            min_qty=min_qty,
        )
        if quantity <= 0:
            logger.warning("[StrategyRunner] 策略 #%d 计算的下单数量 <= 0,跳过", instance_id)
            if signal_id:
                await self._update_signal_status(signal_id, "rejected", reason="余额不足")
            return False

        order_service = OrderService(session)
        order = await order_service.create_order(
            user_id=user_id,
            account_id=account.id,
            symbol=config.symbol,
            side=side,
            order_type="market",
            quantity=quantity,
            strategy_instance_id=instance_id,
        )
        try:
            await order_service.submit_order(order.id, user_id)
        except Exception:
            # P0-3: 提交失败，清理残留订单避免幽灵订单
            try:
                await order_service.order_repo.delete(order.id)
                await session.commit()
            except Exception:
                pass
            if signal_id:
                await self._update_signal_status(signal_id, "rejected", reason="下单失败")
            raise

        if signal_id:
            await self._update_signal_status(signal_id, "executed", order_id=order.id)

        logger.info(
            "[StrategyRunner] 策略 #%d 下单成功: order_id=%d, side=%s, qty=%s",
            instance_id,
            order.id,
            side,
            quantity,
        )
        return True

    async def _auto_reverse_position(
        self,
        *,
        session,
        instance_id: int,
        account,
        config: StrategyConfig,
        user_id: int,
        signal: Signal,
        signal_id: int | None,
    ) -> bool:
        """反手 (Step 2b): 先平掉现有反方向仓,再开 metadata.direction 方向新仓。

        语义注意:
          metadata.direction 是 "目标方向"(反手后的新仓方向),
          所以要平掉的是 "另一方向" 的现有仓。

          示例: RsiLayered 从多翻空发出
            action=sell, intent=reverse, direction=short
          这里我们应该:
            1. 平掉账户上 status=open 的 long 仓(direction 反过来传 None
               让 select 不过滤,直接选第一个开仓 — 策略已自管,
               理论上同 symbol 只有一个仓)
            2. 开新空仓(direction=short, side=sell)

        失败处理:
          - 平仓失败 → 不开新仓,信号 reject(_auto_close_position 已写入)
          - 平仓成功但开新仓失败 → 信号 reject。账户处于"无仓"状态,
            下一根 K 线策略会重新评估。
        """
        meta = signal.metadata or {}
        intent = meta.get("intent", "reverse")
        target_direction = meta.get("direction")

        # 1. 先平: 用 direction=None 不过滤 — 反手时 symbol 上理应只有一个仓
        closed = await self._auto_close_position(
            session=session,
            instance_id=instance_id,
            account=account,
            config=config,
            user_id=user_id,
            direction=None,
            intent=intent,
            signal_id=None,  # signal_id 留给开新仓后再更新,避免重复 reject/executed
        )

        if not closed:
            # _auto_close_position 已 log,但没更新 signal_id(我们传的 None)
            # 这里统一做拒绝
            logger.warning(
                "[StrategyRunner] 策略 #%d reverse 失败: 平原仓未成功,放弃开新仓",
                instance_id,
            )
            if signal_id:
                await self._update_signal_status(
                    signal_id,
                    "rejected",
                    reason="reverse 平原仓失败",
                )
            return False

        # 2. 再开: 调 _auto_open_position
        logger.info(
            "[StrategyRunner] 策略 #%d reverse 平仓成功,开新 %s 仓",
            instance_id,
            target_direction,
        )
        opened = await self._auto_open_position(
            session=session,
            instance_id=instance_id,
            account=account,
            config=config,
            user_id=user_id,
            signal=signal,
            signal_id=signal_id,
        )
        return opened

    # ── 辅助方法 ─────────────────────────────────────────

    async def _sync_strategy_state_from_db(
        self,
        instance_id: int,
        account_id: int,
        symbol: str,
        strategy,
    ) -> None:
        """评审问题9：启动时从 DB 加载真实持仓，覆盖策略内部状态

        若用户手动在交易所平仓（绕过系统），DB 的 Position 为 open 但
        策略内部状态机认为有持仓，会导致信号卡死。这里以 DB 为准同步。
        """
        try:
            async with self._session_maker() as session:
                from app.models.exchange import Position

                result = await session.execute(
                    select(Position).where(
                        Position.account_id == account_id,
                        Position.symbol == symbol.upper(),
                        Position.status == "open",
                        Position.strategy_instance_id == instance_id,
                    )
                )
                db_positions = result.scalars().all()

                # RsiLayered 策略有 _position_dir 字段追踪内部持仓方向
                strategy_pos_dir = getattr(strategy, "_position_dir", None)

                if not db_positions and strategy_pos_dir is not None:
                    logger.warning(
                        "[StrategyRunner] 策略 #%d DB 无持仓但策略状态有 %s 仓,"
                        "重置为 monitoring (可能手动平仓)",
                        instance_id,
                        strategy_pos_dir,
                    )
                    strategy._mode = "monitoring"
                    strategy._position_dir = None
                    strategy._entry_price = None
                    strategy._holding_periods = 0
                    strategy._max_profit = 0.0
                    strategy._additional_positions_count = 0
                elif db_positions and strategy_pos_dir != db_positions[0].side:
                    logger.warning(
                        "[StrategyRunner] 策略 #%d DB 持仓方向 %s 与策略内部 %s 不一致,以 DB 为准",
                        instance_id,
                        db_positions[0].side,
                        strategy_pos_dir,
                    )
                    db_side = db_positions[0].side
                    strategy._mode = db_side
                    strategy._position_dir = db_side
                    strategy._entry_price = float(db_positions[0].entry_price)
        except Exception as exc:
            logger.warning(
                "[StrategyRunner] 策略 #%d 持仓状态同步失败: %s",
                instance_id,
                exc,
            )

    async def _get_symbol_min_qty(
        self,
        exchange: str,
        symbol: str,
    ) -> Decimal:
        """获取交易对最小下单量（评审问题2：从交易所API动态获取，带缓存）

        优先从缓存取，缓存未命中则调用交易所 get_exchange_info。
        交易所 API 调用失败时降级为保守默认值 0.001。
        """
        cache_key = (exchange, symbol.upper())
        if cache_key in self._symbol_min_qty_cache:
            return self._symbol_min_qty_cache[cache_key]

        try:
            from app.core.exchange_adapter import get_exchange_adapter

            adapter = get_exchange_adapter(
                exchange=exchange,
                api_key="",
                secret_key="",
            )
            info = await adapter.get_exchange_info(symbol)
            min_qty = info.min_qty if info.min_qty > 0 else Decimal("0.001")
            self._symbol_min_qty_cache[cache_key] = min_qty
            logger.debug(
                "[StrategyRunner] 获取 %s min_qty=%s (来源: %s)",
                symbol,
                min_qty,
                exchange,
            )
            return min_qty
        except Exception as exc:
            logger.warning(
                "[StrategyRunner] 获取 %s 最小下单量失败,降级为 0.001: %s",
                symbol,
                exc,
            )
            fallback = Decimal("0.001")
            self._symbol_min_qty_cache[cache_key] = fallback
            return fallback

    def _calc_retry_delay(self, exc: Exception, interval: int) -> float:
        """评审问题10：根据异常类型计算重试间隔

        - 网络错误（timeout/connection）→ 10s 快速重试
        - 限流（429/RateLimitError）→ 60s
        - 其他错误 → min(interval*2, 120)
        """
        exc_name = type(exc).__name__
        msg = str(exc).lower()

        # 网络层错误
        if (
            "timeout" in msg
            or "connection" in msg
            or "connect" in msg
            or "NetworkError" in exc_name
            or "Timeout" in exc_name
        ):
            return 10.0

        # 限流错误
        if "429" in msg or "rate" in msg or "RateLimit" in exc_name or "too many" in msg:
            return 60.0

        # 其他错误
        return min(interval * 2, 120)

    def _calculate_order_quantity(
        self,
        balance: Decimal,
        entry_price: Decimal | None,
        symbol: str,
        side: str,
        max_invest_percent: Decimal = Decimal("0.30"),
        min_qty: Decimal = Decimal("0.001"),  # 评审问题2：外部传入精度
    ) -> Decimal:
        """计算下单数量

        Args:
            max_invest_percent: 最大使用余额比例，默认0.30(30%)
            min_qty: 最小下单量（从交易所API获取），默认 0.001
        """
        if not entry_price or entry_price <= 0:
            return Decimal("0")

        invest_amount = balance * max_invest_percent
        quantity = invest_amount / entry_price

        min_qty = self._resolve_min_qty(symbol, min_qty)

        # 卖出不受余额限制（平仓场景）
        if side == "sell":
            return quantity

        return max(quantity, min_qty) if quantity >= min_qty else Decimal("0")

    @staticmethod
    def _resolve_min_qty(symbol: str, min_qty: Decimal) -> Decimal:
        """为测试直调和运行时动态精度都提供稳定的最小下单量。"""
        normalized_symbol = symbol.upper()
        if min_qty > 0 and min_qty != Decimal("0.001"):
            return min_qty

        default_min_qty_map = {
            "BTCUSDT": Decimal("0.001"),
            "ETHUSDT": Decimal("0.001"),
            "SOLUSDT": Decimal("0.001"),
        }
        if min_qty <= 0:
            return default_min_qty_map.get(normalized_symbol, Decimal("1"))

        return default_min_qty_map.get(normalized_symbol, Decimal("1"))

    async def _update_position_prices(
        self,
        instance_id: int,
        symbol: str,
        current_price: Decimal,
        signal: Signal | None = None,  # 评审问题3：接收信号以更新止损/止盈
    ) -> None:
        """更新持仓价格 — P0-2: 持仓价格自动刷新

        查找该策略实例绑定的账户上该交易对的所有 open 持仓，
        更新 current_price 和 unrealized_pnl。
        """
        try:
            async with self._session_maker() as session:
                from app.models.exchange import Position

                # 先找到策略实例获取 account_id
                result = await session.execute(
                    select(StrategyInstance).where(StrategyInstance.id == instance_id)
                )
                inst = result.scalar_one_or_none()
                if not inst or not inst.account_id:
                    return

                # 查找该账户该交易对的 open 持仓
                pos_result = await session.execute(
                    select(Position).where(
                        Position.account_id == inst.account_id,
                        Position.symbol == symbol.upper(),
                        Position.status == "open",
                    )
                )
                positions = pos_result.scalars().all()

                for position in positions:
                    position.current_price = current_price

                    # 计算未实现盈亏
                    if position.side == "long":
                        position.unrealized_pnl = (
                            current_price - position.entry_price
                        ) * position.quantity
                    else:  # short
                        position.unrealized_pnl = (
                            position.entry_price - current_price
                        ) * position.quantity

                    # 计算百分比
                    if position.entry_price and position.entry_price > 0:
                        position.unrealized_pnl_percent = (
                            position.unrealized_pnl
                            / (position.entry_price * position.quantity)
                            * 100
                        )

                    # 评审问题3：信号包含止损/止盈时同步更新持仓
                    if signal is not None:
                        if signal.stop_loss_price is not None:
                            position.stop_loss_price = signal.stop_loss_price
                        if signal.take_profit_price is not None:
                            position.take_profit_price = signal.take_profit_price

                if positions:
                    await session.commit()

                    # 通过 WS 推送持仓更新
                    try:
                        from app.api.v1.ws_market import manager
                        from app.core.trade_schemas import WSMessage

                        for position in positions:
                            msg = WSMessage(
                                type="position_update",
                                exchange=inst.exchange,
                                symbol=symbol,
                                data={
                                    "position_id": position.id,
                                    "current_price": str(current_price),
                                    "unrealized_pnl": str(position.unrealized_pnl),
                                    "unrealized_pnl_percent": str(position.unrealized_pnl_percent),
                                },
                            )
                            subscribers = manager.get_subscribers("position", symbol)
                            for ws in subscribers:
                                with suppress(Exception):
                                    await ws.send_text(msg.model_dump_json())
                    except Exception as exc:
                        logger.debug("[StrategyRunner] WS 推送持仓更新失败: %s", exc)

        except Exception as exc:
            logger.debug("[StrategyRunner] 更新持仓价格失败: %s", exc)

    async def _update_signal_status(
        self,
        signal_id: int,
        status: str,
        order_id: int | None = None,
        reason: str | None = None,
    ) -> None:
        """更新信号状态"""
        try:
            async with self._session_maker() as session:
                from app.models.order import Signal as SignalModel

                result = await session.execute(
                    select(SignalModel).where(SignalModel.id == signal_id)
                )
                db_signal = result.scalar_one_or_none()
                if db_signal:
                    db_signal.status = status
                    if order_id:
                        db_signal.executed_order_id = order_id
                        db_signal.executed_at = datetime.now(UTC)
                    if reason and status == "rejected":
                        db_signal.reason = (db_signal.reason or "") + f" [{reason}]"
                    await session.commit()
        except Exception as exc:
            logger.error("[StrategyRunner] 更新信号状态失败: %s", exc)

    async def _auto_close_position(
        self,
        *,
        session,
        instance_id: int,
        account,
        config: StrategyConfig,
        user_id: int,
        direction: str | None,
        intent: str,
        signal_id: int | None,
    ) -> bool:
        """处理平仓类信号(take_profit / stop_loss / timeout)

        策略已自管持仓状态(在它自己的状态机里),所以这里它说要平,
        我们就找匹配的开仓 Position 并通过 OrderService 反向平掉。

        匹配优先级:
          1. account_id + symbol + status=open 必须满足
          2. 优先匹配 strategy_instance_id == instance_id (该实例自己开的仓)
          3. 然后用 metadata.direction 过滤(long/short)
          4. 找不到 → 拒绝信号(策略与 DB 状态不一致,告警但不爆炸)

        Returns:
            True  — 平仓订单已提交成功(交易所确认 + position 标记 closed)
            False — 跳过(无开仓)或失败(异常 / 选不出目标)
        """
        from app.models.exchange import Position
        from app.services.order_service import OrderService

        try:
            # 找该账户在该交易对上所有 open 持仓
            # 评审问题1: 若已知方向，查询时直接过滤，避免双向持仓选错
            if direction in ("long", "short"):
                pos_query = select(Position).where(
                    Position.account_id == account.id,
                    Position.symbol == config.symbol,
                    Position.status == "open",
                    Position.side == direction,
                )
            else:
                pos_query = select(Position).where(
                    Position.account_id == account.id,
                    Position.symbol == config.symbol,
                    Position.status == "open",
                )
            result = await session.execute(pos_query)
            positions = list(result.scalars().all())

            # 评审问题1: 若未指定方向但存在双向持仓，明确拒绝
            if direction is None and len(positions) > 0:
                sides = {p.side for p in positions}
                if len(sides) > 1:
                    logger.error(
                        "[StrategyRunner] 策略 #%d intent=%s 双向持仓(%s),拒绝平仓"
                        "（请手动处理或指定 direction）",
                        instance_id,
                        intent,
                        ",".join(sorted(sides)),
                    )
                    if signal_id:
                        await self._update_signal_status(
                            signal_id,
                            "rejected",
                            reason=f"intent={intent} 双向持仓拒绝",
                        )
                    return False

            if not positions:
                logger.warning(
                    "[StrategyRunner] 策略 #%d intent=%s 但 DB 无开仓,跳过平仓。"
                    "策略状态可能与 DB 不一致(手工平仓 / 上次平仓未持久化?)",
                    instance_id,
                    intent,
                )
                if signal_id:
                    await self._update_signal_status(
                        signal_id,
                        "rejected",
                        reason=f"intent={intent} 但 DB 无开仓",
                    )
                return False

            position = select_position_to_close(positions, instance_id, direction)
            if position is None:
                # 理论上 not positions 已先返回,这里走不到。保险起见再处理一次。
                logger.warning(
                    "[StrategyRunner] 策略 #%d intent=%s 选不出平仓目标,跳过",
                    instance_id,
                    intent,
                )
                if signal_id:
                    await self._update_signal_status(
                        signal_id,
                        "rejected",
                        reason=f"intent={intent} 无匹配持仓",
                    )
                return False

            if len(positions) > 1:
                logger.warning(
                    "[StrategyRunner] 策略 #%d intent=%s 该 symbol 上有 %d 个开仓,"
                    "选择 #%d (其余暂不处理,需手动检视)",
                    instance_id,
                    intent,
                    len(positions),
                    position.id,
                )

            # 调 OrderService.close_position(已有事务安全顺序:
            # 先提交交易所成功后再标记 closed)
            order_service = OrderService(session)
            await order_service.close_position(position.id, user_id)

            logger.info(
                "[StrategyRunner] 策略 #%d intent=%s 平仓成功: position_id=%d",
                instance_id,
                intent,
                position.id,
            )
            if signal_id:
                await self._update_signal_status(signal_id, "executed")
            return True
        except Exception as exc:
            logger.error(
                "[StrategyRunner] 策略 #%d intent=%s 平仓失败: %s",
                instance_id,
                intent,
                exc,
            )
            if signal_id:
                with suppress(Exception):
                    await self._update_signal_status(
                        signal_id,
                        "rejected",
                        reason=str(exc),
                    )
            return False

    async def _update_last_run_and_state(
        self,
        instance_id: int,
        strategy: BaseStrategy,
    ) -> None:
        """更新 last_run_at + 持久化策略状态机(Step 3)。

        每 tick 末调用一次。即使 to_dict 返回 {}(无状态策略)也照样写,
        保持简单一致。失败不阻塞主循环。
        """
        try:
            state = strategy.to_dict()
        except Exception as exc:
            logger.warning(
                "[StrategyRunner] 策略 #%d to_dict 失败,跳过状态持久化: %s",
                instance_id,
                exc,
            )
            state = None

        try:
            async with self._session_maker() as session:
                result = await session.execute(
                    select(StrategyInstance).where(StrategyInstance.id == instance_id)
                )
                inst = result.scalar_one_or_none()
                if inst:
                    inst.last_run_at = datetime.now(UTC)
                    if state is not None:
                        inst.state_json = state
                    await session.commit()
        except Exception as exc:
            logger.debug("[StrategyRunner] 更新 last_run_at/state_json 失败: %s", exc)

    async def update_stats(
        self,
        instance_id: int,
        pnl: Decimal,
        is_win: bool,
    ) -> None:
        """更新策略实例统计

        每笔交易完成后由 OrderService 调用。
        """
        try:
            async with self._session_maker() as session:
                result = await session.execute(
                    select(StrategyInstance).where(StrategyInstance.id == instance_id)
                )
                inst = result.scalar_one_or_none()
                if not inst:
                    return

                inst.total_pnl = (inst.total_pnl or Decimal("0")) + pnl
                inst.total_trades = (inst.total_trades or 0) + 1

                # 计算胜率
                if inst.total_trades > 0:
                    # 简化：用盈亏正负判断胜负
                    # 实际应由外部传入 is_win
                    wins = int(float(inst.win_rate or 0) * (inst.total_trades - 1) / 100)
                    if is_win:
                        wins += 1
                    inst.win_rate = Decimal(str(round(wins / inst.total_trades * 100, 2)))

                # 计算盈亏百分比
                # 基于初始资金（如果有）
                initial_capital = Decimal(str(inst.params.get("initial_capital", 100000)))
                if initial_capital > 0:
                    inst.total_pnl_percent = inst.total_pnl / initial_capital * 100

                await session.commit()
        except Exception as exc:
            logger.error("[StrategyRunner] 更新统计失败: %s", exc)

    @property
    def active_count(self) -> int:
        """当前运行的策略数"""
        return len(self._runners)

    def get_status(self, instance_id: int) -> dict[str, Any]:
        """获取策略运行状态"""
        task = self._runners.get(instance_id)
        if task is None:
            last_error = self._last_runtime_error.get(instance_id)
            return {
                "running": False,
                "runtime_active": False,
                "runtime_healthy": last_error is None,
                "last_error": last_error,
                "last_error_at": self._last_runtime_error_at.get(instance_id),
            }
        strategy = self._strategies.get(instance_id)
        last_error = self._last_runtime_error.get(instance_id)
        return {
            "running": not task.done(),
            "runtime_active": not task.done(),
            "runtime_healthy": not task.done() and last_error is None,
            "last_error": last_error,
            "last_error_at": self._last_runtime_error_at.get(instance_id),
            "strategy_type": strategy.strategy_type if strategy else None,
            "last_signal_at": self._last_signal_at.get(instance_id, None),
        }


# 全局单例
strategy_runner = StrategyRunner()
