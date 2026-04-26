"""
策略引擎测试 — 信号生成 / 金额计算
"""
import pytest
from decimal import Decimal
from app.core.strategy_runner import StrategyRunner
from app.core.strategy_engine import StrategyConfig, Signal, get_strategy


class TestOrderQuantityCalculation:
    """P1-7: 下单数量计算测试"""

    def setup_method(self):
        self.runner = StrategyRunner.__new__(StrategyRunner)
        self.runner._initialized = True

    def test_default_30_percent(self):
        """默认使用 30% 余额"""
        qty = self.runner._calculate_order_quantity(
            balance=Decimal("1000"),
            entry_price=Decimal("50000"),
            symbol="BTCUSDT",
            side="buy",
        )
        # 1000 * 0.30 / 50000 = 0.006
        assert qty == Decimal("0.006")

    def test_custom_percentage(self):
        """自定义百分比"""
        qty = self.runner._calculate_order_quantity(
            balance=Decimal("1000"),
            entry_price=Decimal("50000"),
            symbol="BTCUSDT",
            side="buy",
            max_invest_percent=Decimal("0.50"),
        )
        # 1000 * 0.50 / 50000 = 0.01
        assert qty == Decimal("0.01")

    def test_zero_entry_price(self):
        """入场价为 0"""
        qty = self.runner._calculate_order_quantity(
            balance=Decimal("1000"),
            entry_price=Decimal("0"),
            symbol="BTCUSDT",
            side="buy",
        )
        assert qty == Decimal("0")

    def test_none_entry_price(self):
        """入场价为 None"""
        qty = self.runner._calculate_order_quantity(
            balance=Decimal("1000"),
            entry_price=None,
            symbol="BTCUSDT",
            side="buy",
        )
        assert qty == Decimal("0")

    def test_sell_always_returns_quantity(self):
        """卖出不受余额限制（平仓场景）"""
        qty = self.runner._calculate_order_quantity(
            balance=Decimal("0.001"),
            entry_price=Decimal("50000"),
            symbol="BTCUSDT",
            side="sell",
        )
        assert qty > 0

    def test_minimum_quantity_btc(self):
        """BTC 最小下单量 0.001"""
        qty = self.runner._calculate_order_quantity(
            balance=Decimal("10"),  # 余额很少
            entry_price=Decimal("50000"),
            symbol="BTCUSDT",
            side="buy",
        )
        # 10 * 0.30 / 50000 = 0.00006 < 0.001 → 返回 0
        assert qty == Decimal("0")

    def test_minimum_quantity_eth(self):
        """ETH 最小下单量 0.01"""
        qty = self.runner._calculate_order_quantity(
            balance=Decimal("100"),
            entry_price=Decimal("3000"),
            symbol="ETHUSDT",
            side="buy",
        )
        # 100 * 0.30 / 3000 = 0.01 ≥ 0.01 → OK
        assert qty >= Decimal("0.01")


class TestStrategyEngine:
    """策略引擎基本测试"""

    def test_get_strategy_ma(self):
        """获取 MA 策略"""
        config = StrategyConfig(symbol="BTCUSDT", exchange="binance")
        strategy = get_strategy("ma", config)
        assert strategy is not None
        assert strategy.strategy_type == "ma"

    def test_get_strategy_rsi(self):
        """获取 RSI 策略"""
        config = StrategyConfig(symbol="BTCUSDT", exchange="binance")
        strategy = get_strategy("rsi", config)
        assert strategy is not None
        assert strategy.strategy_type == "rsi"

    def test_get_strategy_invalid(self):
        """获取不存在的策略"""
        config = StrategyConfig(symbol="BTCUSDT", exchange="binance")
        with pytest.raises(ValueError):
            get_strategy("nonexistent", config)


class TestSignalModel:
    """Signal 数据模型测试"""

    def test_signal_creation(self):
        """创建信号"""
        signal = Signal(
            action="buy",
            confidence=0.85,
            entry_price=Decimal("50000"),
            reason="MA golden cross",
        )
        assert signal.action == "buy"
        assert signal.confidence == 0.85
        assert signal.entry_price == Decimal("50000")

    def test_signal_with_stop_loss(self):
        """带止损的信号"""
        signal = Signal(
            action="buy",
            confidence=0.9,
            entry_price=Decimal("50000"),
            stop_loss_price=Decimal("48000"),
            take_profit_price=Decimal("55000"),
            reason="RSI oversold",
        )
        assert signal.stop_loss_price == Decimal("48000")
        assert signal.take_profit_price == Decimal("55000")
