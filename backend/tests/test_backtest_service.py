from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core import strategy_engine as strategy_engine_mod
from app.core.strategy_engine import BaseStrategy, Signal
from app.services.backtest_service import (
    BacktestService,
    _count_binance_funding_events_utc,
)


def test_count_binance_funding_events_utc():
    t0 = datetime(2026, 1, 1, 7, 0, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    assert _count_binance_funding_events_utc(t0, t1) == 1
    t2 = datetime(2026, 1, 1, 16, 0, tzinfo=UTC)
    assert _count_binance_funding_events_utc(t0, t2) == 2


def _make_klines(count: int = 80) -> list[dict]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    klines: list[dict] = []
    price = Decimal("100")
    for idx in range(count):
        drift = Decimal(str(((idx % 10) - 5) * 0.8))
        close = price + drift
        high = close + Decimal("1.5")
        low = close - Decimal("1.5")
        klines.append(
            {
                "timestamp": start + timedelta(hours=idx),
                "open": close - Decimal("0.3"),
                "high": high,
                "low": low,
                "close": close,
                "volume": Decimal("10"),
                "close_time": start + timedelta(hours=idx, minutes=59),
            }
        )
    return klines


@pytest.mark.parametrize(
    ("template_id", "params"),
    [
        ("rule_custom", {"rules": {"buy_rules": {"logic": "AND", "conditions": []}}}),
        ("rsi_layered", {"kline_interval": "1h"}),
        ("bollinger", {"period": 20, "stdDev": 2.0}),
        ("grid", {"gridCount": 10, "priceRange": 10}),
        ("martingale", {"multiplier": 2.0, "maxLosses": 5}),
    ],
)
async def test_execute_backtest_supports_public_template_types(template_id, params, monkeypatch):
    service = BacktestService()
    captured = {}

    async def fake_fetch_klines(
        symbol,
        start_date,
        end_date,
        interval="1h",
        exchange="binance",
        market="spot",
    ):
        captured["exchange"] = exchange
        captured["market"] = market
        return _make_klines()

    monkeypatch.setattr(service, "_fetch_klines", fake_fetch_klines)

    result = await service.execute_backtest(
        template_id=template_id,
        symbol="BTCUSDT",
        exchange="binance",
        market="spot",
        start_date="2026-01-01",
        end_date="2026-01-05",
        params=params,
    )

    assert "error" not in result
    assert "finalCapital" in result
    assert "equityCurve" in result
    assert captured == {"exchange": "binance", "market": "spot"}


async def test_execute_backtest_full_analysis_window_prefix(monkeypatch):
    """默认 analysis_window：策略每步收到的 K 线长度为 1..i+1 前缀（首步为 min_history+1）。"""
    service = BacktestService()
    lengths: list[int] = []

    async def fake_fetch_klines(*_a, **_kw):
        return _make_klines(80)

    orig_analyze = strategy_engine_mod.MAStrategy.analyze

    async def capture_analyze(self, klines):
        lengths.append(len(klines))
        return await orig_analyze(self, klines)

    monkeypatch.setattr(service, "_fetch_klines", fake_fetch_klines)
    monkeypatch.setattr(strategy_engine_mod.MAStrategy, "analyze", capture_analyze)

    result = await service.execute_backtest(
        template_id="ma_cross",
        symbol="BTCUSDT",
        exchange="binance",
        market="spot",
        start_date="2026-01-01",
        end_date="2026-01-05",
        params={"short_window": 5, "long_window": 20},
    )

    assert "error" not in result
    assert result.get("analysisWindow") is None
    assert lengths, "MAStrategy.analyze should have been called"
    assert lengths[0] == 51  # i=50 → indices 0..50 inclusive
    assert lengths[-1] == 80


async def test_execute_backtest_limited_analysis_window(monkeypatch):
    service = BacktestService()
    lengths: list[int] = []

    async def fake_fetch_klines(*_a, **_kw):
        return _make_klines(80)

    orig_analyze = strategy_engine_mod.MAStrategy.analyze

    async def capture_analyze(self, klines):
        lengths.append(len(klines))
        return await orig_analyze(self, klines)

    monkeypatch.setattr(service, "_fetch_klines", fake_fetch_klines)
    monkeypatch.setattr(strategy_engine_mod.MAStrategy, "analyze", capture_analyze)

    result = await service.execute_backtest(
        template_id="ma_cross",
        symbol="BTCUSDT",
        exchange="binance",
        market="spot",
        start_date="2026-01-01",
        end_date="2026-01-05",
        params={"short_window": 5, "long_window": 20},
        analysis_window=12,
    )

    assert "error" not in result
    assert result.get("analysisWindow") == 12
    assert all(n == 12 for n in lengths)


async def test_execute_backtest_analysis_window_from_params(monkeypatch):
    service = BacktestService()

    async def fake_fetch_klines(*_a, **_kw):
        return _make_klines(80)

    monkeypatch.setattr(service, "_fetch_klines", fake_fetch_klines)

    result = await service.execute_backtest(
        template_id="ma_cross",
        symbol="BTCUSDT",
        exchange="binance",
        market="spot",
        start_date="2026-01-01",
        end_date="2026-01-05",
        params={"short_window": 5, "long_window": 20, "backtest_analysis_window": 25},
    )

    assert "error" not in result
    assert result.get("analysisWindow") == 25


async def test_perp_backtest_can_open_short_via_metadata(monkeypatch):
    """永续 + metadata intent/direction 时允许开空并最终平仓。"""

    class OpenShortOnce(BaseStrategy):
        strategy_type = "ma"
        n = 0

        async def analyze(self, klines):
            self.n += 1
            if self.n == 1:
                return Signal(
                    action="sell",
                    metadata={"intent": "open", "direction": "short"},
                )
            return None

    async def fake_fetch(*_a, **_k):
        return _make_klines(80)

    def fake_get_strategy(_st, cfg):
        return OpenShortOnce(cfg)

    monkeypatch.setattr("app.services.backtest_service.get_strategy", fake_get_strategy)
    service = BacktestService()
    monkeypatch.setattr(service, "_fetch_klines", fake_fetch)

    result = await service.execute_backtest(
        template_id="ma_cross",
        symbol="BTCUSDT",
        exchange="binance",
        market="perp",
        start_date="2026-01-01",
        end_date="2026-01-05",
        params={},
    )

    assert "error" not in result
    assert result.get("market") == "perp"
    assert any(t.get("side") == "short" for t in result["trades"])


async def test_perp_funding_many_periods_final_capital_nonnegative(monkeypatch):
    """多档资金费结算后 finalCapital 仍应合理（防资金费/保证金记账 bug）。"""

    class HoldLong(BaseStrategy):
        strategy_type = "ma"
        n = 0

        async def analyze(self, klines):
            self.n += 1
            if self.n == 1:
                return Signal(
                    action="buy",
                    metadata={"intent": "open", "direction": "long"},
                )
            return None

    async def fake_fetch(*_a, **_k):
        return _make_klines(200)

    def fake_get_strategy(_st, cfg):
        return HoldLong(cfg)

    monkeypatch.setattr("app.services.backtest_service.get_strategy", fake_get_strategy)
    service = BacktestService()
    monkeypatch.setattr(service, "_fetch_klines", fake_fetch)

    result = await service.execute_backtest(
        template_id="ma_cross",
        symbol="BTCUSDT",
        exchange="binance",
        market="perp",
        start_date="2026-01-01",
        end_date="2026-01-10",
        initial_capital=500_000.0,
        params={"funding_rate_8h": 0.0003, "max_invest_percent": 25, "leverage": 10},
    )

    assert "error" not in result
    assert float(result["finalCapital"]) > 0


async def test_execute_backtest_passes_perp_market_to_fetcher(monkeypatch):
    service = BacktestService()
    captured = {}

    async def fake_fetch_klines(
        symbol,
        start_date,
        end_date,
        interval="1h",
        exchange="binance",
        market="spot",
    ):
        captured["symbol"] = symbol
        captured["exchange"] = exchange
        captured["market"] = market
        return _make_klines()

    monkeypatch.setattr(service, "_fetch_klines", fake_fetch_klines)

    result = await service.execute_backtest(
        template_id="rsi_layered",
        symbol="BTCUSDT",
        exchange="binance",
        market="perp",
        start_date="2026-01-01",
        end_date="2026-01-05",
        params={"kline_interval": "1h"},
    )

    assert "error" not in result
    assert captured == {
        "symbol": "BTCUSDT",
        "exchange": "binance",
        "market": "perp",
    }


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


async def test_fetch_klines_impl_uses_binance_perp_host(monkeypatch):
    service = BacktestService()
    captured = {}

    class FakeClient:
        async def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            return _FakeResponse(
                [
                    [1704067200000, "100", "110", "90", "105", "10", 1704070800000],
                ]
            )

    async def fake_get_client(cls):
        return FakeClient()

    monkeypatch.setattr(BacktestService, "_get_client", fake_get_client)

    klines = await service._fetch_klines_impl(
        symbol="BTCUSDT",
        start_date="2026-01-01",
        end_date="2026-01-02",
        interval="1h",
        exchange="binance",
        market="perp",
    )

    assert captured["url"] == "https://fapi.binance.com/fapi/v1/klines"
    assert captured["params"]["symbol"] == "BTCUSDT"
    assert klines[0]["close"] == Decimal("105")


async def test_get_result_by_id_works_without_optional_db_columns(db_session, test_user):
    """BacktestResult 表无 max_wins/final_capital/duration 列时，详情接口仍可返回。"""
    import json

    from app.models.backtest import BacktestResult

    curve = [{"date": "2026-01-05", "equity": 102_500.0}]
    trades = [
        {
            "side": "long",
            "entryPrice": 100.0,
            "exitPrice": 101.0,
            "quantity": 1.0,
            "pnl": 50.0,
            "entryTime": "2026-01-01T00:00:00Z",
            "exitTime": "2026-01-02T00:00:00Z",
        }
    ]
    row = BacktestResult(
        user_id=test_user.id,
        template_id="ma_cross",
        symbol="BTCUSDT",
        exchange="binance",
        start_date="2026-01-01",
        end_date="2026-01-10",
        initial_capital=Decimal("100000"),
        params=json.dumps({"short_window": 5}),
        total_return=Decimal("2500"),
        total_return_pct=Decimal("2.5"),
        annual_return=Decimal("10"),
        sharpe_ratio=Decimal("1.2"),
        calmar_ratio=Decimal("0.8"),
        max_drawdown=Decimal("3"),
        win_rate=Decimal("55"),
        profit_factor=Decimal("1.5"),
        total_trades=10,
        profit_trades=6,
        loss_trades=4,
        avg_profit=Decimal("100"),
        avg_loss=Decimal("50"),
        equity_curve=json.dumps(curve),
        trades=json.dumps(trades),
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)

    svc = BacktestService(db_session)
    out = await svc.get_result_by_id(row.id, test_user.id)
    assert out is not None
    assert out["finalCapital"] == 102_500.0
    assert out["duration"] == 9
    assert out["maxConsecutiveWins"] == 0
    assert out["maxConsecutiveLosses"] == 0
    assert len(out["equityCurve"]) == 1
    assert out["trades"][0]["entryPrice"] == 100.0
