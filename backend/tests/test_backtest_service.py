from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.backtest_service import BacktestService


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

    async def fake_fetch_klines(symbol, start_date, end_date, interval="1h"):
        return _make_klines(), False

    monkeypatch.setattr(service, "_fetch_klines", fake_fetch_klines)

    result = await service.execute_backtest(
        template_id=template_id,
        symbol="BTCUSDT",
        exchange="binance",
        start_date="2026-01-01",
        end_date="2026-01-05",
        params=params,
    )

    assert "error" not in result
    assert "finalCapital" in result
    assert "equityCurve" in result
