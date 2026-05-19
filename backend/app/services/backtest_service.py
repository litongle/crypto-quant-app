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
from app.database import get_db_context
from app.repositories import kline_cache_repo

logger = logging.getLogger(__name__)


# K 线周期 → 毫秒（用于算 cache 命中覆盖 / 标记"未完成 K 线" cutoff）
_INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}


def _interval_to_ms(interval: str) -> int:
    """K 线周期字符串 → 毫秒。未知周期回退到 1h（保守，宁可少缓存）。"""
    return _INTERVAL_MS.get(interval, 3_600_000)


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


def _iso_z(dt) -> str:
    """ISO 8601 with Z suffix for UTC datetime. tz-aware → "+00:00" 替换成 "Z",
    naive → 假设 UTC 直接加 Z。之前到处 `.isoformat() + "Z"` 在 tz-aware 上会
    产出 "2024-12-11T16:00:00+00:00Z" 这种重复后缀,非标准。
    """
    s = dt.isoformat()
    if s.endswith("+00:00"):
        return s[:-6] + "Z"
    return s + "Z"


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
_FETCH_KLINES_TIMEOUT = 60  # 整体拉K线超时秒数（包含所有分页 + 网络往返）

# 回测超时（秒，可配置）
_BACKTEST_TIMEOUT = 120  # 回测引擎超时（不含拉K线），缩短到 2 分钟避免前端长 hang


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
                    "createdAt": _iso_z(r.created_at) if r.created_at else "",
                }
            )
        return history

    async def delete_result_by_id(self, backtest_id: int, user_id: int) -> bool:
        """删除单条回测历史记录 (校验 user_id 防越权)。返回 True 即删除成功。"""
        if not self.session:
            return False
        from app.models.backtest import BacktestResult

        result = await self.session.execute(
            select(BacktestResult).where(
                BacktestResult.id == backtest_id,
                BacktestResult.user_id == user_id,
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return False
        await self.session.delete(record)
        await self.session.commit()
        return True

    async def delete_all_results(self, user_id: int) -> int:
        """清空当前用户全部回测历史。返回删除条数。"""
        if not self.session:
            return 0
        from sqlalchemy import delete as sa_delete

        from app.models.backtest import BacktestResult

        result = await self.session.execute(
            sa_delete(BacktestResult).where(BacktestResult.user_id == user_id)
        )
        await self.session.commit()
        return result.rowcount or 0

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
            "startTime": _iso_z(record.start_time) if record.start_time else None,
            "endTime": _iso_z(record.end_time) if record.end_time else None,
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

        # 1. 获取K线数据(_fetch_klines 内部自带 _FETCH_KLINES_TIMEOUT 超时保护)。
        # 失败直接抛 ValueError -> 转成 user-facing error,绝不 fallback mock。
        try:
            klines = await self._fetch_klines(
                symbol,
                start_date,
                end_date,
                interval=interval,
                exchange=exchange,
                market=market,
            )
        except ValueError as exc:
            return {
                "error": str(exc),
                "code": 4003,
                "detail": (
                    f"K 线获取失败: {exc} "
                    f"(symbol={symbol}, interval={interval}, range={start_date}~{end_date})"
                ),
            }
        if len(klines) < 50:
            return {
                "error": "回测数据不足，至少需要 50 根K线",
                "code": 4001,
                "detail": f"获取到 {len(klines)} 根K线（{interval_label}级别），需要至少 50 根",
            }

        # 截取
        if len(klines) > _MAX_KLINES:
            klines = klines[-_MAX_KLINES:]

        data_source = f"{exchange}-{market}"

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

        # perp 模式下拉 Binance 真实历史 funding rate(每 8h 一档,30 天 ~90 条).
        # 失败时 fallback 空字典 = 0 funding(不阻塞回测,只少了 funding fee 部分)。
        funding_rates_map: dict[int, Decimal] = {}
        if market.lower() == "perp" and exchange.lower() == "binance" and klines:
            try:
                start_ms = int(klines[0]["timestamp"].timestamp() * 1000)
                end_ms = int(klines[-1]["timestamp"].timestamp() * 1000)
                funding_rates_map = await self._fetch_funding_rates(symbol, start_ms, end_ms)
            except Exception as e:
                logger.warning("[backtest] 拉 funding rate 失败,fallback 到 0: %s", e)

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
                    funding_rates_map=funding_rates_map,
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
        funding_rates_map: dict[int, Decimal] | None = None,
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

        # 策略给的固定 USDT 仓位预算 (DCA 用 invest_per_trade, Martingale 等可扩展);
        # 不为 None 时覆盖 max_invest_pct × capital 默认预算。
        # 策略通过 Signal.metadata["invest_amount"] 设置, process_signal 转存到这里
        _strategy_budget_hint: Decimal | None = None

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
            # 开仓手续费 do_open_long/short 时已经从 capital 扣过且累计在 pos["commission_paid"],
            # trade.pnl 必须把它也扣掉才反映真实净盈亏 — 否则:
            # 1. 用户在交易明细看到的 pnl 比实际多(虚高)
            # 2. sum(trade.pnl) != totalReturn(差额 = 所有开仓费, 数据自相矛盾)
            commission_open_total = pos.get("commission_paid", Decimal("0"))
            gross_pnl = (
                (exec_price - pos["entry_price"]) * pos["quantity"]
                if pos["side"] == "long"
                else (pos["entry_price"] - exec_price) * pos["quantity"]
            )
            pnl = gross_pnl - commission_exit - commission_open_total
            capital += mlocked + gross_pnl - commission_exit
            trades.append(
                TradeRecord(
                    entry_price=pos["entry_price"],
                    exit_price=exec_price,
                    quantity=pos["quantity"],
                    side=pos["side"],
                    entry_time=pos["entry_time"],
                    exit_time=exit_time,
                    pnl=pnl,
                    commission=commission_open_total + commission_exit,
                    adds=int(pos.get("add_count", 0)),
                )
            )
            position = None

        def do_open_long(exec_price: Decimal, entry_time: datetime) -> None:
            nonlocal capital, position, trades
            # 策略 hint (DCA invest_amount) 优先, 否则按 max_invest_pct
            budget = (
                min(_strategy_budget_hint, capital)
                if _strategy_budget_hint is not None and _strategy_budget_hint > 0
                else capital * max_invest_pct
            )
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
            # 策略 hint (DCA invest_amount) 优先, 否则按 max_invest_pct
            budget = (
                min(_strategy_budget_hint, capital)
                if _strategy_budget_hint is not None and _strategy_budget_hint > 0
                else capital * max_invest_pct
            )
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
            # 策略 hint (DCA invest_amount) 优先, 否则按 max_invest_pct
            budget = (
                min(_strategy_budget_hint, capital)
                if _strategy_budget_hint is not None and _strategy_budget_hint > 0
                else capital * max_invest_pct
            )
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
            pos["add_count"] = pos.get("add_count", 0) + 1
            capital -= new_mlocked + commission

        def do_add_short(exec_price: Decimal) -> None:
            nonlocal capital, position, trades
            pos = position
            if pos is None or pos["side"] != "short":
                return
            # 策略 hint (DCA invest_amount) 优先, 否则按 max_invest_pct
            budget = (
                min(_strategy_budget_hint, capital)
                if _strategy_budget_hint is not None and _strategy_budget_hint > 0
                else capital * max_invest_pct
            )
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
            pos["add_count"] = pos.get("add_count", 0) + 1
            capital -= new_mlocked + commission

        def process_signal(sig: Signal | None) -> None:
            nonlocal capital, position, trades, _strategy_budget_hint
            # 解析策略给的固定 USDT 预算 (DCA invest_per_trade 等), 让 do_open_*/
            # do_add_* 优先用它而非 max_invest_pct。None / 缺失则继续按比例下单。
            _strategy_budget_hint = None
            if sig is not None and sig.metadata:
                raw_hint = sig.metadata.get("invest_amount")
                if raw_hint is not None:
                    try:
                        hint_val = Decimal(str(raw_hint))
                        if hint_val > 0:
                            _strategy_budget_hint = hint_val
                    except (TypeError, ValueError):
                        pass
            if sig is None:
                return
            meta = sig.metadata or {}
            intent = meta.get("intent")
            direction_meta = meta.get("direction")

            if not perp:
                if sig.action == "buy":
                    ep = current_price * (Decimal("1") + slippage_pct)
                    if position is None:
                        do_open_long(ep, current_time)
                    elif position["side"] == "long":
                        # DCA / 网格 / 加仓型策略:已开多仓时 buy 信号当加仓处理,
                        # 否则策略发再多 buy 信号都被吞,trades 只有 1 次。
                        # take_profit/stop_loss 路径走 sell,跟 close 逻辑配合正常。
                        do_add_long(ep)
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
            # 加仓型策略(martingale/grid 等不发 intent="add" 的 fallback) —
            # 永续下 buy+持多 / sell+持空 之前被吞,导致 Martingale 加仓功能失效。
            # 与现货 process_signal 对齐:同向 buy → do_add_long, 同向 sell → do_add_short
            elif sig.action == "buy" and position is not None and position["side"] == "long":
                do_add_long(current_price * (Decimal("1") + slippage_pct))
            elif sig.action == "sell" and position is not None and position["side"] == "short":
                do_add_short(current_price * (Decimal("1") - slippage_pct))

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

        engine_t0 = time.monotonic()
        total_bars = len(klines) - min_history
        # 每 ~5% 一次心跳；max(50,...) 让 1000 根以内的小回测也能看见进度
        progress_step = max(50, total_bars // 20)
        logger.info(
            "[backtest] 引擎开始处理 %d 根 K 线（min_history=%d, 总待处理=%d）",
            len(klines),
            min_history,
            total_bars,
        )

        for i in range(min_history, len(klines)):
            processed = i - min_history
            # 每 25 根 K 线让出一次 event loop (~90ms 一次 yield),保证 polling/health
            # 单次 RTT 不超过 100ms。strategy.analyze 标 async 但内部全同步, await 是假
            # await, 主循环不 yield 会卡死整个 worker。sleep(0) 零开销。
            if processed > 0 and processed % 25 == 0:
                await asyncio.sleep(0)
            if processed > 0 and processed % progress_step == 0:
                elapsed = time.monotonic() - engine_t0
                pct = processed / total_bars * 100 if total_bars else 100
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (total_bars - processed) / rate if rate > 0 else -1
                logger.info(
                    "[backtest] 进度 %d/%d (%.1f%%)，速度 %.0f bar/s，已用 %.1fs，预计还需 %.1fs",
                    processed,
                    total_bars,
                    pct,
                    rate,
                    elapsed,
                    eta,
                )

            current_price = klines[i]["close"]
            current_time = klines[i]["timestamp"]

            # 资金费扣减: 优先用真实历史 funding_rates_map(每个 fundingTime 一档),
            # 其次回退到 params.funding_rate_8h × n_f。真实历史更准确反映 perp 持仓成本。
            if i > min_history and perp and position is not None:
                prev_ms = int(klines[i - 1]["timestamp"].timestamp() * 1000)
                curr_ms = int(current_time.timestamp() * 1000)
                mark = current_price
                notional = position["quantity"] * mark
                if funding_rates_map:
                    # 真实历史: 遍历 [prev_ms, curr_ms] 跨过的所有 fundingTime
                    delta = Decimal(0)
                    for ft_ms, rate in funding_rates_map.items():
                        if prev_ms < ft_ms <= curr_ms:
                            delta += notional * rate
                    if delta != 0:
                        if position["side"] == "long":
                            capital -= delta
                        else:
                            capital += delta
                elif funding_rate_8h != 0:
                    # fallback hardcode rate
                    n_f = _count_binance_funding_events_utc(
                        klines[i - 1]["timestamp"], current_time
                    )
                    if n_f > 0:
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
        # 交易记录(最多 100 条) — 取最近 100 笔而非最早 100 笔。
        # 之前 trades[:100] 让 200 笔的回测用户只看到一个月前的旧 trade,
        # 看不到末期策略表现。用户视角更关心最新 N 笔。
        max_trade_display = 100
        trades_to_show = trades[-max_trade_display:] if len(trades) > max_trade_display else trades
        trade_records = []
        for t in trades_to_show:
            trade_records.append(
                {
                    "side": t.side,
                    "entryPrice": float(t.entry_price),
                    "exitPrice": float(t.exit_price),
                    "quantity": float(t.quantity),
                    "pnl": float(round(t.pnl, 2)),
                    "entryTime": _iso_z(t.entry_time),
                    "exitTime": _iso_z(t.exit_time),
                    "adds": int(getattr(t, "adds", 0)),
                }
            )

        logger.info(
            "[backtest] 引擎完成：处理 %d 根 K 线，%d 笔交易，引擎耗时 %.1fs",
            len(klines),
            len(trades),
            time.monotonic() - engine_t0,
        )

        # totalReturn 用 (final_equity - initial_capital) 与 totalReturnPercent 同源,
        # 包含期末未平仓 unrealized pnl。之前 report.total_pnl 只算已平仓 trades.pnl,
        # 与百分比口径不一致,会出现"绝对值 +38 但百分比 -0.05%"的符号矛盾(已平仓
        # 累计赚但当前持仓浮亏)。
        total_return_abs = float(report.final_equity - initial_capital)
        return {
            "totalReturn": total_return_abs,
            "totalReturnPercent": float(report.total_return_pct),
            "annualReturn": float(report.annualized_return_pct),
            "sharpeRatio": float(report.sharpe_ratio),
            "calmarRatio": float(report.calmar_ratio),
            "maxDrawdown": float(report.max_drawdown_pct),
            "maxDrawdownDurationHours": round(report.max_drawdown_duration_hours, 1),
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
            "startTime": _iso_z(report.start_time) if report.start_time else None,
            "endTime": _iso_z(report.end_time) if report.end_time else None,
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

    async def _fetch_funding_rates(
        self, symbol: str, start_ms: int, end_ms: int
    ) -> dict[int, Decimal]:
        """拉 Binance 永续 funding rate 历史。返回 {fundingTime_ms: Decimal(rate)}。

        每 8h 一档,30 天 ~90 条,limit=1000 一次拉够。失败时返空字典(回测继续,
        funding fee = 0)。
        """
        try:
            client = await self._get_client()
            resp = await client.get(
                "https://fapi.binance.com/fapi/v1/fundingRate",
                params={
                    "symbol": symbol,
                    "startTime": start_ms,
                    "endTime": end_ms,
                    "limit": 1000,
                },
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()
            result = {int(r["fundingTime"]): Decimal(r["fundingRate"]) for r in data}
            logger.info(
                "[backtest] 拉 funding rate: %s 共 %d 条 (%s ~ %s)",
                symbol,
                len(result),
                datetime.fromtimestamp(start_ms / 1000, tz=UTC).strftime("%Y-%m-%d"),
                datetime.fromtimestamp(end_ms / 1000, tz=UTC).strftime("%Y-%m-%d"),
            )
            return result
        except Exception as e:
            logger.warning("[backtest] funding rate API 失败: %s", e)
            return {}

    async def _fetch_klines(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1h",
        exchange: str = "binance",
        market: str = "spot",
    ) -> list[dict]:
        """获取历史K线数据，超时由调用方控制。

        内置最大数量限制 _MAX_KLINES，超过自动截断。
        失败/超时一律抛 ValueError,绝不 fallback 假数据 —— 回测必须真实历史。
        """
        try:
            return await asyncio.wait_for(
                self._fetch_klines_impl(symbol, start_date, end_date, interval, exchange, market),
                timeout=_FETCH_KLINES_TIMEOUT,
            )
        except TimeoutError as exc:
            logger.warning(
                "[backtest] 获取K线超时(%d秒,%s %s %s~%s)",
                _FETCH_KLINES_TIMEOUT,
                interval,
                symbol,
                start_date,
                end_date,
            )
            raise ValueError(
                f"拉取 K 线超时({_FETCH_KLINES_TIMEOUT}s),请缩小时间范围或稍后重试"
            ) from exc

    async def _fetch_klines_impl(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1h",
        exchange: str = "binance",
        market: str = "spot",
    ) -> list[dict]:
        """获取历史K线数据内部实现 —— 本地缓存优先。

        策略：
        1. 算 ts 范围 [start_ms, end_ms]，end_ms 不能超过"现在"
        2. cutoff_ms = now - interval_ms：最后一根可能未收盘，不缓存
        3. 读 cache.get_range：若 [start_ms, min(end_ms, cutoff_ms)] 全段都被缓存命中
           （按 interval_ms 等距点检查覆盖）→ 完整命中，直接返
        4. 否则 → 走原拉取逻辑（分页 REST），拉完后只把 ts < cutoff_ms 的部分 upsert 回 cache
        5. 若用户请求范围超过 cutoff，cache 完整命中也要补拉那一小段未完成 K 线（不写回 cache）

        内置最大数量限制 _MAX_KLINES，超过自动截断。
        失败时抛 ValueError(由调用方包装成 user-facing error),不返假数据。
        """
        try:
            start_ms = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
            end_ms = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
        except ValueError as e:
            raise ValueError(f"日期格式错误,需要 YYYY-MM-DD: {e}") from e

        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        end_ms = min(end_ms, now_ms)
        interval_ms = _interval_to_ms(interval)
        cutoff_ms = now_ms - interval_ms  # 严格早于 cutoff 的 K 线视为已完成

        # ===== 缓存读 =====
        cached_klines: list[dict] = []
        cache_hit = False
        try:
            async with get_db_context() as session:
                cached_rows = await kline_cache_repo.get_range(
                    session, exchange, symbol, interval, start_ms, end_ms
                )
            # 检查缓存覆盖：从 start_ms 对齐到 interval，每隔 interval_ms 一个点，
            # 直到 min(end_ms, cutoff_ms)；这些点都必须在 cache 里才算完整命中。
            coverage_end = min(end_ms, cutoff_ms)
            if cached_rows and coverage_end >= start_ms:
                # 用第一根 cached ts 当对齐基准（交易所返回的 ts 本身就按 interval 对齐）
                base_ts = cached_rows[0].ts
                cached_ts_set = {r.ts for r in cached_rows}
                # 期望覆盖的所有 ts 点
                expected_ts = []
                t = base_ts
                # base_ts 必须 <= start_ms + interval_ms（否则区间起点都没缓存）
                if base_ts <= start_ms + interval_ms:
                    while t <= coverage_end:
                        expected_ts.append(t)
                        t += interval_ms
                    cache_hit = all(ts in cached_ts_set for ts in expected_ts) and bool(expected_ts)
            if cache_hit:
                cached_klines = [self._cache_row_to_kline(r, interval_ms) for r in cached_rows]
                logger.info(
                    "[backtest] cache 完整命中 %s %s %s %s~%s（%d 根）",
                    exchange,
                    symbol,
                    interval,
                    start_date,
                    end_date,
                    len(cached_klines),
                )
        except Exception as e:
            logger.warning("[backtest] 读 K 线缓存失败，回退到 REST 拉取: %s", e)
            cache_hit = False
            cached_klines = []

        if cache_hit:
            # 用户请求范围若延伸到 cutoff 之后，可能漏最新 1-2 根；补拉一小段（不写回 cache）
            if end_ms > cutoff_ms and cached_klines:
                last_cached_ts = cached_klines[-1]["timestamp"]
                tail_start_ms = int(last_cached_ts.timestamp() * 1000) + interval_ms
                if tail_start_ms <= end_ms:
                    tail_klines = await self._fetch_from_rest(
                        symbol, tail_start_ms, end_ms, interval, exchange, market
                    )
                    cached_klines.extend(tail_klines)
            return cached_klines[:_MAX_KLINES]

        # ===== cache miss / 部分命中：全量拉 + 写回 =====
        all_klines = await self._fetch_from_rest(
            symbol, start_ms, end_ms, interval, exchange, market
        )
        if all_klines:
            try:
                rows_to_cache = [
                    {
                        "exchange": exchange,
                        "symbol": symbol,
                        "interval": interval,
                        "ts": int(k["timestamp"].timestamp() * 1000),
                        "open": k["open"],
                        "high": k["high"],
                        "low": k["low"],
                        "close": k["close"],
                        "volume": k["volume"],
                    }
                    for k in all_klines
                    if int(k["timestamp"].timestamp() * 1000) < cutoff_ms
                ]
                if rows_to_cache:
                    async with get_db_context() as session:
                        inserted = await kline_cache_repo.bulk_upsert(session, rows_to_cache)
                        await session.commit()
                        logger.info(
                            "[backtest] 写回 cache: %d/%d 根（已跳过未完成 K 线）",
                            inserted,
                            len(rows_to_cache),
                        )
            except Exception as e:
                # 缓存写失败不影响回测主流程
                logger.warning("[backtest] 写 K 线缓存失败，忽略: %s", e)

        return all_klines

    @staticmethod
    def _cache_row_to_kline(row, interval_ms: int) -> dict:
        """KlineCache ORM 行 → 引擎期望的 K 线 dict（timestamp 为 UTC datetime，价格为 Decimal）。"""
        open_ts = datetime.fromtimestamp(row.ts / 1000, tz=UTC)
        close_ts = datetime.fromtimestamp((row.ts + interval_ms - 1) / 1000, tz=UTC)
        return {
            "timestamp": open_ts,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
            "close_time": close_ts,
        }

    async def _fetch_from_rest(
        self,
        symbol: str,
        start_ms: int,
        end_ms: int,
        interval: str,
        exchange: str,
        market: str,
    ) -> list[dict]:
        """从交易所 REST 拉 K 线（原 _fetch_klines_impl 主体）。失败抛 ValueError。"""
        all_klines: list[dict] = []
        fetch_t0 = time.monotonic()
        page_index = 0
        try:
            client = await self._get_client()
            current_start = start_ms
            logger.info(
                "[backtest] 开始拉 K 线 %s %s %d~%d (market=%s)",
                exchange,
                symbol,
                start_ms,
                end_ms,
                market,
            )

            while current_start < end_ms and len(all_klines) < _MAX_KLINES:
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
                    "endTime": end_ms,
                    "limit": 1000,
                }

                page_index += 1
                page_t0 = time.monotonic()
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                page_elapsed_ms = int((time.monotonic() - page_t0) * 1000)

                if not data:
                    logger.info(
                        "[backtest] 第 %d 页空响应，结束分页（累计 %d 根，总耗时 %.1fs）",
                        page_index,
                        len(all_klines),
                        time.monotonic() - fetch_t0,
                    )
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

                logger.info(
                    "[backtest] 第 %d 页 %d 根 K 线，本页 %dms，累计 %d 根，总 %.1fs",
                    page_index,
                    len(data),
                    page_elapsed_ms,
                    len(all_klines),
                    time.monotonic() - fetch_t0,
                )

                current_start = data[-1][6] + 1

                if len(data) < 1000:
                    break

                if len(all_klines) >= _MAX_KLINES:
                    logger.warning(
                        "K线数量已达上限 %d，截断。interval=%s, %d~%d",
                        _MAX_KLINES,
                        interval,
                        start_ms,
                        end_ms,
                    )
                    break

        except Exception as e:
            logger.warning(
                "[backtest] 获取K线数据失败(已分页 %d 次,累计 %d 根,耗时 %.1fs): %s",
                page_index,
                len(all_klines),
                time.monotonic() - fetch_t0,
                e,
            )
            raise ValueError(f"交易所 API 拉 K 线失败: {e}") from e

        logger.info(
            "[backtest] 拉 K 线完成：%d 根，%d 次分页，总耗时 %.1fs",
            len(all_klines),
            page_index,
            time.monotonic() - fetch_t0,
        )

        return all_klines

    # _generate_mock_klines 已删除 — 回测必须用真实历史,拉失败直接抛 ValueError,
    # 不再静默 fallback 假数据让用户误判策略表现。
