"""
回测服务 v2 - 内存优化版

核心行为：
1. K线数据量上限可截断，跨度过大自动升级时间级别（1h→4h→1d）——除非 params 指定 kline_interval
2. 策略 analyze：默认传入「从序列起点到当前 bar」的完整前缀（与早期全量语义一致）；
   可选 analysis_window / params.backtest_analysis_window 限制为最近 N 根以节省内存
3. 权益曲线采样展示；绩效用采样点集
4. 超时保护
5. K线预转换为 float，避免循环内重复 Decimal 转换
6. 永续：单笔名义与 runner 对齐 `max_invest_percent`；初始保证金率 = `initial_margin_rate`（>0）否则 `1/leverage`；
   资金费 `funding_rate_8h` 按 UTC 00/08/16 档计数，名义×费率（正=多付空收）。现货保证金率视为 100%。
"""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.performance import (
    EquityPoint,
    PerformanceCalculator,
    TradeRecord,
)
from app.core.strategy_engine import (
    BaseStrategy,
    Signal,
    StrategyConfig,
    get_strategy,
)
from app.core.strategy_runner import CLOSE_INTENTS

logger = logging.getLogger(__name__)


def _coerce_analysis_window(raw: object) -> int | None:
    """解析回测 K 线窗口：None/缺省/≤0 表示全量前缀；正整数表示仅最近 N 根。"""
    if raw is None:
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return n


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _first_binance_funding_utc_after(t: datetime) -> datetime:
    """Binance USDT 永续常见结算锚点：UTC 00:00 / 08:00 / 16:00 后的下一档（严格晚于 t）。"""
    t = _ensure_utc(t)
    day0 = t.replace(hour=0, minute=0, second=0, microsecond=0)
    for h in (0, 8, 16):
        cand = day0.replace(hour=h)
        if cand > t:
            return cand
    return day0 + timedelta(days=1)


def _count_binance_funding_events_utc(t_lo: datetime, t_hi: datetime) -> int:
    """统计 (t_lo, t_hi] 内落在 UTC 00/08/16 档的资金费结算次数（与按整点结算的近似一致）。"""
    t_lo = _ensure_utc(t_lo)
    t_hi = _ensure_utc(t_hi)
    if t_hi <= t_lo:
        return 0
    n = 0
    cur = _first_binance_funding_utc_after(t_lo)
    while cur <= t_hi:
        n += 1
        cur = _first_binance_funding_utc_after(cur)
    return n


def _backtest_margin_and_sizing_params(params: dict) -> tuple[Decimal, Decimal, Decimal, int]:
    """(max_invest_pct, initial_margin_rate, funding_rate_8h, leverage)

    max_invest_pct: 与 strategy_runner 一致，单笔占用可用余额比例。
    initial_margin_rate: 永续初始保证金占名义本金比例；未显式设置时用 1/杠杆。
    funding_rate_8h: 每期资金费率（Binance 符号：正=多付空收），名义×费率每期扣/加在现金上。
    """
    max_pct = Decimal(str(params.get("max_invest_percent", 30))) / Decimal("100")
    if max_pct <= 0 or max_pct > 1:
        max_pct = Decimal("0.30")

    lev = int(params.get("leverage", 20) or 20)
    if lev < 1:
        lev = 1

    imr_raw = params.get("initial_margin_rate")
    if imr_raw is not None and str(imr_raw).strip() != "":
        imr = Decimal(str(imr_raw))
        if imr <= 0 or imr > 1:
            imr = Decimal("1") / Decimal(str(lev))
    else:
        imr = Decimal("1") / Decimal(str(lev))

    fr = Decimal(str(params.get("funding_rate_8h", 0)))
    return max_pct, imr, fr, lev


# templateId → strategy_type 映射
_TEMPLATE_MAP = {
    "ma_cross": "ma",
    "ma": "ma",
    "rsi": "rsi",
    "rule_custom": "rule",
    "rsi_layered": "rsi_layered",
    "bollinger": "bollinger",
    "grid": "grid",
    "martingale": "martingale",
    "dca": "dca",
    "multi_symbol": "multi_symbol",
}

# 时间级别配置：(interval, 每天约多少根, 最大支持天数)
_INTERVAL_CONFIG = [
    ("1h", 24, 200),  # 200天以内用1h
    ("4h", 6, 800),  # 200-800天用4h
    ("1d", 1, 3650),  # 800天-10年用1d
]

# 最大K线数量（可配置）
_MAX_KLINES = 50000  # 从 5000 提升到 50000

# 回测超时（秒，可配置）
_BACKTEST_TIMEOUT = 300  # 从 60 秒提升到 300 秒（5分钟）


class BacktestService:
    """回测服务 v2"""

    def __init__(self, session: AsyncSession | None = None):
        self.session = session

    _shared_client: httpx.AsyncClient | None = None

    async def get_user_history(self, user_id: int, limit: int = 20) -> list[dict]:
        """获取用户回测历史 (P2-17)"""
        if not self.session:
            return []

        from app.models.backtest import BacktestResult
        from app.seed_data import STRATEGY_TEMPLATES

        name_map = {t["code"]: t["name"] for t in STRATEGY_TEMPLATES}

        result = await self.session.execute(
            select(BacktestResult)
            .where(BacktestResult.user_id == user_id)
            .order_by(desc(BacktestResult.created_at))
            .limit(limit)
        )
        records = result.scalars().all()

        history = []
        for r in records:
            history.append(
                {
                    "id": r.id,
                    "templateId": r.template_id,
                    "templateName": name_map.get(r.template_id, r.template_id),
                    "symbol": r.symbol,
                    "exchange": r.exchange,
                    "startDate": r.start_date,
                    "endDate": r.end_date,
                    "initialCapital": float(r.initial_capital),
                    "totalReturn": float(r.total_return),
                    "totalReturnPercent": float(r.total_return_pct),
                    "sharpeRatio": float(r.sharpe_ratio),
                    "maxDrawdown": float(r.max_drawdown),
                    "winRate": float(r.win_rate),
                    "totalTrades": r.total_trades,
                    "createdAt": r.created_at.isoformat() + "Z" if r.created_at else "",
                }
            )
        return history

    async def get_result_by_id(self, backtest_id: int, user_id: int) -> dict | None:
        """获取回测详情 (P2-17)"""
        if not self.session:
            return None

        from app.models.backtest import BacktestResult

        result = await self.session.execute(
            select(BacktestResult).where(
                BacktestResult.id == backtest_id,
                BacktestResult.user_id == user_id,
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return None

        # 模型未持久化 max_wins / final_capital / duration 等字段时，用 getattr + 推导
        max_wins = getattr(record, "max_wins", None)
        max_losses = getattr(record, "max_losses", None)
        final_cap = getattr(record, "final_capital", None)
        duration_days = getattr(record, "duration", None)

        equity_curve: list = []
        if record.equity_curve:
            try:
                equity_curve = json.loads(record.equity_curve)
            except (json.JSONDecodeError, TypeError):
                equity_curve = []

        trades_raw: list = []
        if record.trades:
            try:
                trades_raw = json.loads(record.trades)
            except (json.JSONDecodeError, TypeError):
                trades_raw = []

        init_f = float(record.initial_capital)
        tot_ret = float(record.total_return)
        if final_cap is None:
            if equity_curve:
                last = equity_curve[-1]
                if isinstance(last, dict) and last.get("equity") is not None:
                    final_cap = float(last["equity"])
                else:
                    final_cap = init_f + tot_ret
            else:
                final_cap = init_f + tot_ret
        else:
            final_cap = float(final_cap)

        if duration_days is None:
            try:
                from datetime import datetime as dt_mod

                d0 = dt_mod.strptime(record.start_date[:10], "%Y-%m-%d")
                d1 = dt_mod.strptime(record.end_date[:10], "%Y-%m-%d")
                duration_days = max(1, (d1 - d0).days)
            except (ValueError, TypeError):
                duration_days = 0

        return {
            "id": record.id,
            "templateId": record.template_id,
            "symbol": record.symbol,
            "exchange": record.exchange,
            "startDate": record.start_date,
            "endDate": record.end_date,
            "initialCapital": init_f,
            "params": json.loads(record.params) if record.params else {},
            "totalReturn": tot_ret,
            "totalReturnPercent": float(record.total_return_pct),
            "annualReturn": float(record.annual_return),
            "sharpeRatio": float(record.sharpe_ratio),
            "calmarRatio": float(record.calmar_ratio),
            "maxDrawdown": float(record.max_drawdown),
            "winRate": float(record.win_rate),
            "profitFactor": float(record.profit_factor),
            "totalTrades": record.total_trades,
            "profitTrades": record.profit_trades,
            "lossTrades": record.loss_trades,
            "avgProfit": float(record.avg_profit),
            "avgLoss": float(record.avg_loss),
            "maxConsecutiveWins": int(max_wins) if max_wins is not None else 0,
            "maxConsecutiveLosses": int(max_losses) if max_losses is not None else 0,
            "finalCapital": final_cap,
            "duration": int(duration_days) if duration_days is not None else 0,
            "equityCurve": equity_curve,
            "trades": trades_raw,
            "startTime": record.start_time.isoformat() + "Z" if record.start_time else None,
            "endTime": record.end_time.isoformat() + "Z" if record.end_time else None,
        }

    @classmethod
    async def _get_client(cls) -> httpx.AsyncClient:
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(
                timeout=10.0,  # 单次请求最多10秒（原30s），配合整体45s超时
                headers={"User-Agent": "CryptoQuant-Backtest/1.0"},
            )
        return cls._shared_client

    @classmethod
    async def close_client(cls) -> None:
        if cls._shared_client and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
            cls._shared_client = None

    def _select_interval(self, start_date: str, end_date: str) -> tuple[str, str]:
        """根据日期跨度自动选择K线时间级别"""
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            days = (end - start).days
        except ValueError:
            days = 90

        for interval, _bars_per_day, max_days in _INTERVAL_CONFIG:
            if days <= max_days:
                label_map = {"1h": "1小时", "4h": "4小时", "1d": "日线"}
                return interval, label_map.get(interval, interval)

        return "1d", "日线"

    async def execute_backtest(
        self,
        template_id: str,
        symbol: str,
        exchange: str,
        market: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 100000,
        params: dict | None = None,
        analysis_window: int | None = None,
    ) -> dict:
        """执行策略回测

        analysis_window:
            None / ≤0：每根 bar 向策略传入从第 0 根到当前根的完整 K 线前缀（默认，与早期语义一致）。
            正整数：仅传入最近 N 根（省内存，长指标会失真）。
            亦可由 params['backtest_analysis_window'] 提供；本参数优先于后者。
        """
        params = dict(params or {})
        start_time = time.monotonic()

        resolved_aw = _coerce_analysis_window(analysis_window)
        if resolved_aw is None:
            resolved_aw = _coerce_analysis_window(params.pop("backtest_analysis_window", None))
        else:
            params.pop("backtest_analysis_window", None)

        # 优先使用策略参数里指定的 kline_interval(与实盘运行对齐),
        # 否则按时间跨度自动选择,保证旧数据兼容。
        user_interval = params.get("kline_interval")
        if user_interval:
            interval = str(user_interval)
            label_map = {
                "1m": "1分钟",
                "5m": "5分钟",
                "15m": "15分钟",
                "30m": "30分钟",
                "1h": "1小时",
                "4h": "4小时",
                "1d": "日线",
            }
            interval_label = label_map.get(interval, interval)
        else:
            interval, interval_label = self._select_interval(start_date, end_date)

        # 1. 获取K线数据（_fetch_klines 内部自带45秒超时保护）
        klines, is_mock = await self._fetch_klines(
            symbol,
            start_date,
            end_date,
            interval=interval,
            exchange=exchange,
            market=market,
        )
        if len(klines) < 50:
            return {
                "error": "回测数据不足，至少需要 50 根K线",
                "code": 4001,
                "detail": f"获取到 {len(klines)} 根K线（{interval_label}级别），需要至少 50 根",
            }

        # 截取
        if len(klines) > _MAX_KLINES:
            klines = klines[-_MAX_KLINES:]

        data_source = "mock" if is_mock else f"{exchange}-{market}"

        # 2. 创建策略实例
        strategy_type = _TEMPLATE_MAP.get(template_id.lower(), template_id.lower())
        config = StrategyConfig(
            symbol=symbol.upper(),
            exchange=exchange.lower(),
            direction="both",
            params=params,
            risk_params={"stop_loss_percent": params.get("stop_loss_percent", 2.0)},
        )

        try:
            strategy = get_strategy(strategy_type, config)
        except ValueError:
            return {"error": f"不支持的策略类型: {template_id}", "code": 3001}

        # 3. 运行回测引擎（带超时保护）
        try:
            result = await asyncio.wait_for(
                self._run_backtest_engine(
                    strategy=strategy,
                    klines=klines,
                    initial_capital=Decimal(str(initial_capital)),
                    interval_label=interval_label,
                    data_source=data_source,
                    analysis_window=resolved_aw,
                    market=market,
                ),
                timeout=_BACKTEST_TIMEOUT,
            )
        except TimeoutError:
            return {
                "error": f"回测超时（{_BACKTEST_TIMEOUT}秒），请缩小时间范围",
                "code": 4002,
            }

        elapsed = time.monotonic() - start_time
        result["elapsedSeconds"] = round(elapsed, 1)
        result["interval"] = interval_label
        result["klineCount"] = len(klines)
        result["analysisWindow"] = resolved_aw

        return result

    async def _run_backtest_engine(
        self,
        strategy: BaseStrategy,
        klines: list[dict],
        initial_capital: Decimal,
        interval_label: str = "",
        data_source: str = "mock",
        analysis_window: int | None = None,
        market: str = "spot",
    ) -> dict:
        """回测引擎核心 v2 — 内存优化版

        analysis_window 为 None 时传入 float_klines[0:i+1]；为正时传入最近 N 根。
        market=perp 时启用合约双向语义（metadata.intent/direction 与 strategy_runner 对齐；
        无 metadata 时：买开多、卖开空、对手方向平仓）。
        spot 保持仅做多（卖仅平多）。
        """
        capital = initial_capital
        position: dict | None = None
        trades: list[TradeRecord] = []
        perp = market.lower() == "perp"
        max_invest_pct, initial_margin_rate, funding_rate_8h, leverage_used = (
            _backtest_margin_and_sizing_params(strategy.params or {})
        )
        # 现货：全额本金占用（保证金率=100%）；永续：初始保证金 = 名义 × initial_margin_rate
        order_margin_rate = initial_margin_rate if perp else Decimal("1")
        # P1-8: 按 maker/taker 分手续费，加滑点模拟
        taker_fee = Decimal("0.001")  # 0.1% taker (Binance 默认)
        slippage_pct = Decimal("0.0005")  # 0.05% 滑点
        # 使用 params 中指定的手续费率（如有）
        if strategy.params:
            taker_fee = Decimal(str(strategy.params.get("taker_fee", 0.001)))
            slippage_pct = Decimal(str(strategy.params.get("slippage_pct", 0.0005)))

        # 预转换K线为 float 格式（只做一次，O(n)）
        float_klines = [
            {
                "open": float(k["open"]),
                "high": float(k["high"]),
                "low": float(k["low"]),
                "close": float(k["close"]),
                "volume": float(k["volume"]),
            }
            for k in klines
        ]

        min_history = 50

        # 权益曲线采样：用于前端展示（最多 200 个点）
        _sample_step = max(1, (len(klines) - min_history) // 200)
        display_equity: list[dict] = []

        # 精确权益曲线：用于绩效计算（采样保存，最多 500 个点）
        _perf_step = max(1, (len(klines) - min_history) // 500)
        perf_equity: list[EquityPoint] = [
            EquityPoint(timestamp=klines[0]["timestamp"], equity=initial_capital)
        ]

        # 初始展示点
        display_equity.append(
            {
                "date": klines[0]["timestamp"].strftime("%Y-%m-%d %H:%M"),
                "equity": float(initial_capital),
            }
        )

        def do_close(exec_price: Decimal, exit_time: datetime) -> None:
            nonlocal capital, position, trades
            pos = position
            if pos is None:
                return
            commission_exit = pos["quantity"] * exec_price * taker_fee
            mlocked = pos.get("margin_locked") or pos.get("margin_notional") or Decimal(0)
            if pos["side"] == "long":
                pnl = (exec_price - pos["entry_price"]) * pos["quantity"] - commission_exit
                capital += (
                    mlocked + (exec_price - pos["entry_price"]) * pos["quantity"] - commission_exit
                )
            else:
                pnl = (pos["entry_price"] - exec_price) * pos["quantity"] - commission_exit
                capital += (
                    mlocked + (pos["entry_price"] - exec_price) * pos["quantity"] - commission_exit
                )
            trades.append(
                TradeRecord(
                    entry_price=pos["entry_price"],
                    exit_price=exec_price,
                    quantity=pos["quantity"],
                    side=pos["side"],
                    entry_time=pos["entry_time"],
                    exit_time=exit_time,
                    pnl=pnl,
                    commission=pos["commission_paid"] + commission_exit,
                )
            )
            position = None

        def do_open_long(exec_price: Decimal, entry_time: datetime) -> None:
            nonlocal capital, position, trades
            budget = capital * max_invest_pct
            quantity = budget / exec_price
            notional = quantity * exec_price
            commission = notional * taker_fee
            mlocked = notional * order_margin_rate
            position = {
                "side": "long",
                "quantity": quantity,
                "entry_price": exec_price,
                "entry_time": entry_time,
                "commission_paid": commission,
                "margin_locked": mlocked,
                "margin_notional": notional,
            }
            capital -= mlocked + commission

        def do_open_short(exec_price: Decimal, entry_time: datetime) -> None:
            nonlocal capital, position, trades
            budget = capital * max_invest_pct
            quantity = budget / exec_price
            notional = quantity * exec_price
            commission = notional * taker_fee
            mlocked = notional * order_margin_rate
            position = {
                "side": "short",
                "quantity": quantity,
                "entry_price": exec_price,
                "entry_time": entry_time,
                "commission_paid": commission,
                "margin_locked": mlocked,
                "margin_notional": notional,
            }
            capital -= mlocked + commission

        def do_add_long(exec_price: Decimal) -> None:
            nonlocal capital, position, trades
            pos = position
            if pos is None or pos["side"] != "long":
                return
            budget = capital * max_invest_pct
            new_qty = budget / exec_price
            new_notional = new_qty * exec_price
            commission = new_notional * taker_fee
            new_mlocked = new_notional * order_margin_rate
            old_q, old_e = pos["quantity"], pos["entry_price"]
            total_q = old_q + new_qty
            new_entry = (old_e * old_q + exec_price * new_qty) / total_q
            pos["quantity"] = total_q
            pos["entry_price"] = new_entry
            pos["commission_paid"] += commission
            pos["margin_locked"] = pos.get("margin_locked", Decimal(0)) + new_mlocked
            pos["margin_notional"] = pos.get("margin_notional", old_e * old_q) + new_notional
            capital -= new_mlocked + commission

        def do_add_short(exec_price: Decimal) -> None:
            nonlocal capital, position, trades
            pos = position
            if pos is None or pos["side"] != "short":
                return
            budget = capital * max_invest_pct
            new_qty = budget / exec_price
            new_notional = new_qty * exec_price
            commission = new_notional * taker_fee
            new_mlocked = new_notional * order_margin_rate
            old_q, old_e = pos["quantity"], pos["entry_price"]
            total_q = old_q + new_qty
            new_entry = (old_e * old_q + exec_price * new_qty) / total_q
            pos["quantity"] = total_q
            pos["entry_price"] = new_entry
            pos["commission_paid"] += commission
            pos["margin_locked"] = pos.get("margin_locked", Decimal(0)) + new_mlocked
            pos["margin_notional"] = pos.get("margin_notional", old_e * old_q) + new_notional
            capital -= new_mlocked + commission

        def process_signal(sig: Signal | None) -> None:
            nonlocal capital, position, trades
            if sig is None:
                return
            meta = sig.metadata or {}
            intent = meta.get("intent")
            direction_meta = meta.get("direction")

            if not perp:
                if sig.action == "buy" and position is None:
                    ep = current_price * (Decimal("1") + slippage_pct)
                    do_open_long(ep, current_time)
                elif sig.action == "sell" and position is not None:
                    ep = current_price * (Decimal("1") - slippage_pct)
                    do_close(ep, current_time)
                return

            if intent in CLOSE_INTENTS and position is not None:
                if direction_meta is None or position["side"] == direction_meta:
                    if position["side"] == "long":
                        ep = current_price * (Decimal("1") - slippage_pct)
                    else:
                        ep = current_price * (Decimal("1") + slippage_pct)
                    do_close(ep, current_time)
                return

            if intent == "reverse":
                if position is not None:
                    if position["side"] == "long":
                        ep = current_price * (Decimal("1") - slippage_pct)
                    else:
                        ep = current_price * (Decimal("1") + slippage_pct)
                    do_close(ep, current_time)
                tgt = meta.get("direction")
                if tgt == "long":
                    do_open_long(current_price * (Decimal("1") + slippage_pct), current_time)
                elif tgt == "short":
                    do_open_short(current_price * (Decimal("1") - slippage_pct), current_time)
                return

            if intent in ("open", "add") and direction_meta in ("long", "short"):
                if intent == "open" and position is None:
                    if direction_meta == "long" and sig.action == "buy":
                        do_open_long(current_price * (Decimal("1") + slippage_pct), current_time)
                    elif direction_meta == "short" and sig.action == "sell":
                        do_open_short(current_price * (Decimal("1") - slippage_pct), current_time)
                elif (
                    intent == "add" and position is not None and position["side"] == direction_meta
                ):
                    if direction_meta == "long" and sig.action == "buy":
                        do_add_long(current_price * (Decimal("1") + slippage_pct))
                    elif direction_meta == "short" and sig.action == "sell":
                        do_add_short(current_price * (Decimal("1") - slippage_pct))
                return

            if sig.action == "buy" and position is None:
                do_open_long(current_price * (Decimal("1") + slippage_pct), current_time)
            elif sig.action == "sell" and position is None:
                do_open_short(current_price * (Decimal("1") - slippage_pct), current_time)
            elif sig.action == "buy" and position is not None and position["side"] == "short":
                ep = current_price * (Decimal("1") + slippage_pct)
                do_close(ep, current_time)
            elif sig.action == "sell" and position is not None and position["side"] == "long":
                ep = current_price * (Decimal("1") - slippage_pct)
                do_close(ep, current_time)

        def mark_equity(cp: Decimal) -> Decimal:
            if position is None:
                return capital
            mlocked = position.get("margin_locked") or position.get("margin_notional")
            if mlocked is None:
                mlocked = position["quantity"] * position["entry_price"]
            if position["side"] == "long":
                unreal = position["quantity"] * (cp - position["entry_price"])
                return capital + mlocked + unreal
            unreal = position["quantity"] * (position["entry_price"] - cp)
            return capital + mlocked + unreal

        for i in range(min_history, len(klines)):
            current_price = klines[i]["close"]
            current_time = klines[i]["timestamp"]

            if i > min_history and perp and funding_rate_8h != 0 and position is not None:
                n_f = _count_binance_funding_events_utc(klines[i - 1]["timestamp"], current_time)
                if n_f > 0:
                    mark = current_price
                    notional = position["quantity"] * mark
                    delta = notional * funding_rate_8h * Decimal(n_f)
                    if position["side"] == "long":
                        capital -= delta
                    else:
                        capital += delta

            hist_end = i + 1
            window_start = 0 if analysis_window is None else max(0, hist_end - analysis_window)
            history_slice = float_klines[window_start:hist_end]

            # 策略分析
            signal = await strategy.analyze(history_slice)

            process_signal(signal)

            # 止损止盈 — P1-8: 滑点可能触发更快/更慢
            if position is not None:
                sl_price = signal.stop_loss_price if signal else None
                tp_price = signal.take_profit_price if signal else None

                should_close = False
                if position["side"] == "long":
                    if (sl_price and current_price <= sl_price) or (
                        tp_price and current_price >= tp_price
                    ):
                        should_close = True
                else:
                    if (sl_price and current_price >= sl_price) or (
                        tp_price and current_price <= tp_price
                    ):
                        should_close = True

                if should_close:
                    if position["side"] == "long":
                        exec_tp = current_price * (Decimal("1") - slippage_pct)
                    else:
                        exec_tp = current_price * (Decimal("1") + slippage_pct)
                    do_close(exec_tp, current_time)

            # 当前权益
            current_equity = mark_equity(current_price)

            # 采样：展示权益曲线
            idx = i - min_history
            if idx % _sample_step == 0:
                display_equity.append(
                    {
                        "date": current_time.strftime("%Y-%m-%d %H:%M"),
                        "equity": float(round(current_equity, 2)),
                    }
                )

            # 采样：绩效权益曲线
            if idx % _perf_step == 0:
                perf_equity.append(
                    EquityPoint(
                        timestamp=current_time,
                        equity=current_equity,
                    )
                )

        # 平仓未结束的头寸 — P1-8: 按滑点后的 taker 价格平仓
        if position is not None:
            final_price_raw = klines[-1]["close"]
            if position["side"] == "long":
                final_price = final_price_raw * (Decimal("1") - slippage_pct)
            else:
                final_price = final_price_raw * (Decimal("1") + slippage_pct)
            do_close(final_price, klines[-1]["timestamp"])

        # 最终权益
        final_equity = capital
        display_equity.append(
            {
                "date": klines[-1]["timestamp"].strftime("%Y-%m-%d %H:%M"),
                "equity": float(round(final_equity, 2)),
            }
        )
        perf_equity.append(
            EquityPoint(
                timestamp=klines[-1]["timestamp"],
                equity=final_equity,
            )
        )

        # 绩效计算
        report = PerformanceCalculator.calculate(
            trades=trades,
            equity_curve=perf_equity,
            initial_capital=initial_capital,
        )
        # 交易记录（最多 100 条）
        trade_records = []
        for t in trades[:100]:
            trade_records.append(
                {
                    "side": t.side,
                    "entryPrice": float(t.entry_price),
                    "exitPrice": float(t.exit_price),
                    "quantity": float(t.quantity),
                    "pnl": float(round(t.pnl, 2)),
                    "entryTime": t.entry_time.isoformat() + "Z",
                    "exitTime": t.exit_time.isoformat() + "Z",
                }
            )

        return {
            "totalReturn": float(report.total_pnl),
            "totalReturnPercent": float(report.total_return_pct),
            "annualReturn": float(report.annualized_return_pct),
            "sharpeRatio": float(report.sharpe_ratio),
            "calmarRatio": float(report.calmar_ratio),
            "maxDrawdown": float(report.max_drawdown_pct),
            "winRate": float(report.win_rate),
            "profitFactor": float(report.profit_loss_ratio),
            "totalTrades": report.total_trades,
            "profitTrades": report.winning_trades,
            "lossTrades": report.losing_trades,
            "avgProfit": float(report.avg_profit),
            "avgLoss": float(report.avg_loss),
            "maxConsecutiveWins": report.max_consecutive_wins,
            "maxConsecutiveLosses": report.max_consecutive_losses,
            "initialCapital": float(initial_capital),
            "finalCapital": float(report.final_equity),
            "duration": report.trading_days,
            "equityCurve": display_equity,
            "trades": trade_records,
            "startTime": report.start_time.isoformat() + "Z" if report.start_time else None,
            "endTime": report.end_time.isoformat() + "Z" if report.end_time else None,
            "dataSource": data_source,
            "market": market,
            "maxInvestPercent": float(max_invest_pct * 100),
            "leverage": leverage_used,
            "initialMarginRate": float(initial_margin_rate),
            "fundingRate8h": float(funding_rate_8h),
            "warning": (
                "⚠️ 使用模拟数据回测，结果可能失真，仅供参考" if data_source == "mock" else None
            ),
        }

    async def _fetch_klines(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1h",
        exchange: str = "binance",
        market: str = "spot",
    ) -> tuple[list[dict], bool]:
        """获取历史K线数据，超时由调用方控制。

        内置最大数量限制 _MAX_KLINES，超过自动截断。
        返回 (klines, is_mock)
        """
        try:
            return await asyncio.wait_for(
                self._fetch_klines_impl(symbol, start_date, end_date, interval, exchange, market),
                timeout=45.0,
            )
        except TimeoutError:
            logger.warning("获取K线超时（45秒），切换为模拟数据")
            return self._generate_mock_klines(symbol, start_date, end_date, interval), True

    async def _fetch_klines_impl(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1h",
        exchange: str = "binance",
        market: str = "spot",
    ) -> tuple[list[dict], bool]:
        """获取历史K线数据内部实现。

        内置最大数量限制 _MAX_KLINES，超过自动截断。
        返回 (klines, is_mock)
        """
        all_klines = []
        is_mock = False
        try:
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

            client = await self._get_client()
            current_start = start_ts

            while current_start < end_ts and len(all_klines) < _MAX_KLINES:
                if exchange != "binance":
                    raise ValueError(f"暂不支持 {exchange} 回测数据拉取")

                url = (
                    "https://fapi.binance.com/fapi/v1/klines"
                    if market == "perp"
                    else "https://api.binance.com/api/v3/klines"
                )
                params = {
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "startTime": current_start,
                    "endTime": end_ts,
                    "limit": 1000,
                }

                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                if not data:
                    break

                for k in data:
                    all_klines.append(
                        {
                            "timestamp": datetime.fromtimestamp(k[0] / 1000, tz=UTC),
                            "open": Decimal(k[1]),
                            "high": Decimal(k[2]),
                            "low": Decimal(k[3]),
                            "close": Decimal(k[4]),
                            "volume": Decimal(k[5]),
                            "close_time": datetime.fromtimestamp(k[6] / 1000, tz=UTC),
                        }
                    )

                current_start = data[-1][6] + 1

                if len(data) < 1000:
                    break

                if len(all_klines) >= _MAX_KLINES:
                    logger.warning(
                        "K线数量已达上限 %d，截断。interval=%s, %s ~ %s",
                        _MAX_KLINES,
                        interval,
                        start_date,
                        end_date,
                    )
                    break

        except Exception as e:
            logger.warning("获取K线数据失败: %s，使用模拟数据", e)
            all_klines = self._generate_mock_klines(symbol, start_date, end_date, interval)
            is_mock = True
        else:
            is_mock = False

        return all_klines, is_mock

    def _generate_mock_klines(
        self, symbol: str, start_date: str, end_date: str, interval: str = "1h"
    ) -> list[dict]:
        """生成模拟K线数据（降级用）

        根据 interval 自动调整生成频率，总量不超过 _MAX_KLINES。
        P3-23: 使用 zlib.crc32 代替 md5 进行确定性随机（更轻量，且不受 FIPS 限制）
        """
        import zlib

        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            days = max((end - start).days, 1)
        except ValueError:
            days = 90

        base_prices = {
            "BTCUSDT": 98000.0,
            "ETHUSDT": 3200.0,
            "SOLUSDT": 185.0,
            "BNBUSDT": 620.0,
            "DOGEUSDT": 0.38,
        }
        base = base_prices.get(symbol.upper(), 100.0)

        interval_hours = {
            "1m": 1 / 60,
            "5m": 5 / 60,
            "15m": 15 / 60,
            "30m": 30 / 60,
            "1h": 1,
            "4h": 4,
            "1d": 24,
        }
        hours_per_bar = interval_hours.get(interval, 1)
        total_bars = min(int(days * 24 / hours_per_bar), _MAX_KLINES)

        klines = []
        current_time = start.replace(tzinfo=UTC)
        price = base

        for i in range(total_bars):
            seed = zlib.crc32(f"{symbol}_{interval}_{i}".encode()) % 10000
            change = ((seed / 10000.0) - 0.48) * 0.02
            price = price * (1 + change)

            open_price = price
            high = price * (1 + abs(change) * 0.5)
            low = price * (1 - abs(change) * 0.5)
            close = price * (1 + ((seed % 7) - 3) * 0.001)
            volume = base * 1000 * (1 + (seed % 5) * 0.1)

            klines.append(
                {
                    "timestamp": current_time,
                    "open": Decimal(str(round(open_price, 8))),
                    "high": Decimal(str(round(high, 8))),
                    "low": Decimal(str(round(low, 8))),
                    "close": Decimal(str(round(close, 8))),
                    "volume": Decimal(str(round(volume, 2))),
                    "close_time": current_time,
                }
            )

            current_time += timedelta(hours=hours_per_bar)

        return klines
