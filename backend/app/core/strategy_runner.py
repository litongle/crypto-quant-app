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

                # 4. 更新 last_run_at
                await self._update_last_run(instance_id)

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

                # 确定下单方向
                if signal.action in ("buy", "sell"):
                    side = signal.action
                elif signal.action == "close":
                    # 平仓信号 → 查找持仓确定方向
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
                        logger.info("[StrategyRunner] 策略 #%d close 信号但无持仓，跳过", instance_id)
                        return
                    side = "sell" if position.side == "long" else "buy"
                else:
                    logger.warning("[StrategyRunner] 未知信号动作: %s", signal.action)
                    return

                # 计算下单数量（P1-7: 使用可配置比例，默认30%）
                max_invest_pct = Decimal(str(config.params.get("max_invest_percent", 30))) / 100
                quantity = self._calculate_order_quantity(
                    account.balance, signal.entry_price, config.symbol, side, max_invest_pct
                )
                if quantity <= 0:
                    logger.warning("[StrategyRunner] 策略 #%d 计算的下单数量 <= 0，跳过", instance_id)
                    if signal_id:
                        await self._update_signal_status(signal_id, "rejected", reason="余额不足")
                    return

                # 创建订单
                from app.services.order_service import OrderService
                order_service = OrderService(session)
                order = await order_service.create_order(
                    user_id=inst.user_id,
                    account_id=account.id,
                    symbol=config.symbol,
                    side=side,
                    order_type="market",
                    quantity=quantity,
                    strategy_instance_id=instance_id,
                )

                # 提交到交易所
                await order_service.submit_order(order.id, inst.user_id)

                # 更新信号状态
                if signal_id:
                    await self._update_signal_status(
                        signal_id, "executed", order_id=order.id
                    )

                logger.info(
                    "[StrategyRunner] 策略 #%d 自动下单成功: order_id=%d, side=%s, qty=%s",
                    instance_id, order.id, side, quantity,
                )

        except Exception as exc:
            logger.error("[StrategyRunner] 策略 #%d 自动下单失败: %s", instance_id, exc)
            if signal_id:
                try:
                    await self._update_signal_status(signal_id, "rejected", reason=str(exc))
                except Exception:
                    pass

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

    async def _update_last_run(self, instance_id: int) -> None:
        """更新策略实例的 last_run_at"""
        try:
            async with self._session_maker() as session:
                result = await session.execute(
                    select(StrategyInstance).where(StrategyInstance.id == instance_id)
                )
                inst = result.scalar_one_or_none()
                if inst:
                    inst.last_run_at = datetime.now(timezone.utc)
                    await session.commit()
        except Exception as exc:
            logger.debug("[StrategyRunner] 更新 last_run_at 失败: %s", exc)

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
