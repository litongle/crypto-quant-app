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
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.strategy_engine import (
    BaseStrategy,
    Signal,
    StrategyConfig,
    get_strategy,
)
from app.core.trade_schemas import WSMessage
from app.models.strategy import StrategyInstance, StrategyTemplate

logger = logging.getLogger(__name__)

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
        self._running = False
        self._session_maker = None

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
                .join(StrategyTemplate)
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
        if instance_id in self._runners:
            logger.warning("[StrategyRunner] 策略 #%d 已在运行", instance_id)
            return False

        async with self._session_maker() as session:
            result = await session.execute(
                select(StrategyInstance)
                .where(StrategyInstance.id == instance_id)
                .join(StrategyTemplate)
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
                strategy.from_dict(inst.state_json)
                logger.info(
                    "[StrategyRunner] 策略 #%d 状态已从 DB 恢复",
                    inst.id,
                )
            except Exception as exc:
                # 恢复失败不阻塞启动 — 退化为从零开始,记录告警
                logger.warning(
                    "[StrategyRunner] 策略 #%d 状态恢复失败,从零开始: %s",
                    inst.id, exc,
                )

        self._strategies[inst.id] = strategy
        self._runners[inst.id] = asyncio.create_task(
            self._run_loop(inst.id, strategy, config),
            name=f"strategy-runner-{inst.id}",
        )
        logger.info(
            "[StrategyRunner] 策略 #%d (%s/%s) 已启动",
            inst.id, strategy_type, inst.symbol,
        )

    async def _run_loop(self, instance_id: int, strategy: BaseStrategy, config: StrategyConfig) -> None:
        """策略运行主循环"""
        # 轮询间隔（秒），从策略参数读取
        interval = config.params.get("interval", 60)  # 默认 60 秒
        kline_limit = 100  # 获取最近 100 根 K 线

        while self._running:
            try:
                # 1. 获取 K 线数据
                klines = await self._fetch_klines(config.exchange, config.symbol, kline_limit)

                if not klines:
                    await asyncio.sleep(interval)
                    continue

                # 2. 调用策略分析
                signal = await strategy.analyze(klines)

                # 3. 处理信号
                if signal:
                    await self._handle_signal(instance_id, signal, config)

                # 4. 更新 last_run_at + Step 3: 持久化策略状态
                await self._update_last_run_and_state(instance_id, strategy)

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                logger.info("[StrategyRunner] 策略 #%d 运行任务被取消", instance_id)
                break
            except Exception as exc:
                logger.error("[StrategyRunner] 策略 #%d 运行异常: %s", instance_id, exc)
                await asyncio.sleep(min(interval * 2, 300))  # 异常后等待更长时间

    async def _fetch_klines(
        self, exchange: str, symbol: str, limit: int
    ) -> list[dict]:
        """从交易所获取 K 线数据"""
        try:
            from app.core.exchange_adapter import get_exchange_adapter
            # 使用公开数据不需要 API Key，传入空字符串
            adapter = get_exchange_adapter(
                exchange=exchange,
                api_key="",
                secret_key="",
            )
            klines = await adapter.get_klines(symbol, interval="1m", limit=limit)
            return [
                {
                    "open": float(k.open),
                    "high": float(k.high),
                    "low": float(k.low),
                    "close": float(k.close),
                    "volume": float(k.volume),
                    "timestamp": k.timestamp,
                }
                for k in klines
            ]
        except Exception as exc:
            logger.warning("[StrategyRunner] 获取K线失败 %s/%s: %s", exchange, symbol, exc)
            return []

    async def _handle_signal(self, instance_id: int, signal: Signal, config: StrategyConfig) -> None:
        """处理策略信号：持久化信号 + WS推送 + 自动下单"""
        # 防抖：60 秒内同策略不重复发信号
        now = datetime.now(timezone.utc)
        last = self._last_signal_at.get(instance_id)
        if last and (now - last).total_seconds() < 60:
            return

        self._last_signal_at[instance_id] = now

        logger.info(
            "[StrategyRunner] 策略 #%d 产生信号: action=%s, confidence=%.2f, reason=%s",
            instance_id, signal.action, signal.confidence, signal.reason,
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
                    "stop_loss_price": str(signal.stop_loss_price) if signal.stop_loss_price else None,
                    "take_profit_price": str(signal.take_profit_price) if signal.take_profit_price else None,
                    "reason": signal.reason,
                },
            )
            subscribers = manager.get_subscribers("signal", config.symbol)
            for ws in subscribers:
                try:
                    await ws.send_text(msg.model_dump_json())
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("[StrategyRunner] WS 推送信号失败: %s", exc)

        # ③ 自动下单（需要用户在策略参数中开启 auto_trade + 绑定账户）
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
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
                session.add(db_signal)
                await session.commit()
                await session.refresh(db_signal)
                logger.info("[StrategyRunner] 信号已持久化: signal_id=%d, action=%s", db_signal.id, signal.action)
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
                    select(StrategyInstance)
                    .where(StrategyInstance.id == instance_id)
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
                        await self._update_signal_status(signal_id, "rejected", reason="未绑定交易所账户")
                    return

                # 获取绑定的交易所账户
                from app.models.exchange import ExchangeAccount
                acct_result = await session.execute(
                    select(ExchangeAccount).where(ExchangeAccount.id == inst.account_id)
                )
                account = acct_result.scalar_one_or_none()
                if not account or not account.is_active:
                    logger.warning(
                        "[StrategyRunner] 策略 #%d 绑定的账户 #%d 不可用",
                        instance_id, inst.account_id,
                    )
                    if signal_id:
                        await self._update_signal_status(signal_id, "rejected", reason="交易所账户不可用")
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
                try:
                    await self._update_signal_status(signal_id, "rejected", reason=str(exc))
                except Exception:
                    pass

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

        # 计算下单数量
        max_invest_pct = Decimal(str(config.params.get("max_invest_percent", 30))) / 100
        quantity = self._calculate_order_quantity(
            account.balance, signal.entry_price, config.symbol, side, max_invest_pct,
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
        await order_service.submit_order(order.id, user_id)

        if signal_id:
            await self._update_signal_status(signal_id, "executed", order_id=order.id)

        logger.info(
            "[StrategyRunner] 策略 #%d 下单成功: order_id=%d, side=%s, qty=%s",
            instance_id, order.id, side, quantity,
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
                    signal_id, "rejected", reason="reverse 平原仓失败",
                )
            return False

        # 2. 再开: 调 _auto_open_position
        logger.info(
            "[StrategyRunner] 策略 #%d reverse 平仓成功,开新 %s 仓",
            instance_id, target_direction,
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

    def _calculate_order_quantity(
        self,
        balance: Decimal,
        entry_price: Decimal | None,
        symbol: str,
        side: str,
        max_invest_percent: Decimal = Decimal("0.30"),  # P1-7: 默认30%，可配置
    ) -> Decimal:
        """计算下单数量

        Args:
            max_invest_percent: 最大使用余额比例，默认0.30(30%)
        """
        if not entry_price or entry_price <= 0:
            return Decimal("0")

        invest_amount = balance * max_invest_percent
        quantity = invest_amount / entry_price

        # 根据交易对确定最小下单量
        symbol_upper = symbol.upper()
        if "BTC" in symbol_upper:
            min_qty = Decimal("0.001")
        elif "ETH" in symbol_upper:
            min_qty = Decimal("0.01")
        elif "SOL" in symbol_upper:
            min_qty = Decimal("0.1")
        else:
            min_qty = Decimal("1")

        # 卖出不受余额限制（平仓场景）
        if side == "sell":
            return quantity

        return max(quantity, min_qty) if quantity >= min_qty else Decimal("0")

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
                        db_signal.executed_at = datetime.now(timezone.utc)
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
            result = await session.execute(
                select(Position).where(
                    Position.account_id == account.id,
                    Position.symbol == config.symbol,
                    Position.status == "open",
                )
            )
            positions = list(result.scalars().all())

            if not positions:
                logger.warning(
                    "[StrategyRunner] 策略 #%d intent=%s 但 DB 无开仓,跳过平仓。"
                    "策略状态可能与 DB 不一致(手工平仓 / 上次平仓未持久化?)",
                    instance_id, intent,
                )
                if signal_id:
                    await self._update_signal_status(
                        signal_id, "rejected",
                        reason=f"intent={intent} 但 DB 无开仓",
                    )
                return False

            position = select_position_to_close(positions, instance_id, direction)
            if position is None:
                # 理论上 not positions 已先返回,这里走不到。保险起见再处理一次。
                logger.warning(
                    "[StrategyRunner] 策略 #%d intent=%s 选不出平仓目标,跳过",
                    instance_id, intent,
                )
                if signal_id:
                    await self._update_signal_status(
                        signal_id, "rejected", reason=f"intent={intent} 无匹配持仓",
                    )
                return False

            if len(positions) > 1:
                logger.warning(
                    "[StrategyRunner] 策略 #%d intent=%s 该 symbol 上有 %d 个开仓,"
                    "选择 #%d (其余暂不处理,需手动检视)",
                    instance_id, intent, len(positions), position.id,
                )

            # 调 OrderService.close_position(已有事务安全顺序:
            # 先提交交易所成功后再标记 closed)
            order_service = OrderService(session)
            await order_service.close_position(position.id, user_id)

            logger.info(
                "[StrategyRunner] 策略 #%d intent=%s 平仓成功: position_id=%d",
                instance_id, intent, position.id,
            )
            if signal_id:
                await self._update_signal_status(signal_id, "executed")
            return True
        except Exception as exc:
            logger.error(
                "[StrategyRunner] 策略 #%d intent=%s 平仓失败: %s",
                instance_id, intent, exc,
            )
            if signal_id:
                try:
                    await self._update_signal_status(
                        signal_id, "rejected", reason=str(exc),
                    )
                except Exception:
                    pass
            return False

    async def _update_last_run_and_state(
        self, instance_id: int, strategy: BaseStrategy,
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
                instance_id, exc,
            )
            state = None

        try:
            async with self._session_maker() as session:
                result = await session.execute(
                    select(StrategyInstance).where(StrategyInstance.id == instance_id)
                )
                inst = result.scalar_one_or_none()
                if inst:
                    inst.last_run_at = datetime.now(timezone.utc)
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
        if instance_id not in self._runners:
            return {"running": False}
        task = self._runners[instance_id]
        strategy = self._strategies.get(instance_id)
        return {
            "running": not task.done(),
            "strategy_type": strategy.strategy_type if strategy else None,
            "last_signal_at": self._last_signal_at.get(instance_id, None),
        }


# 全局单例
strategy_runner = StrategyRunner()
