"""
F1: market_service 永续合约路由单元测试

只测纯逻辑(URL 构建 + symbol 转换 + 校验),不打交易所网络。
联调留给 docker compose 启动后的手工 smoke。
"""
import pytest

from app.services.market_service import (
    MarketService,
    SUPPORTED_MARKET_TYPES,
)
from app.core.exceptions import AppException


@pytest.fixture
def svc():
    return MarketService(session=None)


# ── 校验 ──────────────────────────────────────────────────

class TestMarketTypeValidation:
    def test_unknown_market_type_raises(self, svc):
        with pytest.raises(AppException) as e:
            svc._validate_symbol_market("BTCUSDT", "futures")
        assert "市场类型" in e.value.message

    def test_unknown_symbol_raises(self, svc):
        with pytest.raises(AppException) as e:
            svc._validate_symbol_market("XYZUSDT", "spot")
        assert "交易对" in e.value.message

    def test_supported_combos_pass(self, svc):
        # 不抛异常即通过
        svc._validate_symbol_market("BTCUSDT", "spot")
        svc._validate_symbol_market("BTCUSDT", "perp")
        svc._validate_symbol_market("ETHUSDT", "perp")

    def test_supported_market_types_constant(self):
        assert SUPPORTED_MARKET_TYPES == {"spot", "perp"}


# ── Binance URL 路由(spot vs perp 是不同 host) ─────────────

class TestBinanceUrlRouting:
    def test_spot_ticker_uses_api_binance_com(self, svc):
        url, params = svc._build_ticker_request("binance", "BTCUSDT", "spot")
        assert url.startswith("https://api.binance.com/api/v3/")
        assert params == {"symbol": "BTCUSDT"}

    def test_perp_ticker_uses_fapi_binance_com(self, svc):
        url, params = svc._build_ticker_request("binance", "BTCUSDT", "perp")
        assert url.startswith("https://fapi.binance.com/fapi/v1/")
        assert params == {"symbol": "BTCUSDT"}

    def test_spot_kline_uses_api_v3(self, svc):
        url, _ = svc._build_kline_request("binance", "BTCUSDT", "1h", 100, "spot")
        assert "api.binance.com/api/v3/klines" in url

    def test_perp_kline_uses_fapi_v1(self, svc):
        url, _ = svc._build_kline_request("binance", "BTCUSDT", "1h", 100, "perp")
        assert "fapi.binance.com/fapi/v1/klines" in url

    def test_spot_orderbook(self, svc):
        url, _ = svc._build_orderbook_request("binance", "BTCUSDT", 20, "spot")
        assert "api.binance.com/api/v3/depth" in url

    def test_perp_orderbook(self, svc):
        url, _ = svc._build_orderbook_request("binance", "BTCUSDT", 20, "perp")
        assert "fapi.binance.com/fapi/v1/depth" in url


# ── OKX URL 路由(同 host,instId 不同) ─────────────────────

class TestOkxRouting:
    def test_spot_inst_id(self, svc):
        assert svc._to_okx_inst_id("BTCUSDT", "spot") == "BTC-USDT"

    def test_perp_inst_id_appends_swap(self, svc):
        assert svc._to_okx_inst_id("BTCUSDT", "perp") == "BTC-USDT-SWAP"

    def test_perp_inst_id_other_quote(self, svc):
        # OKX 也支持 USDC perp,确保后缀策略不挑剔
        assert svc._to_okx_inst_id("BTCUSDC", "perp") == "BTC-USDC-SWAP"

    def test_spot_ticker_url(self, svc):
        url, params = svc._build_ticker_request("okx", "BTCUSDT", "spot")
        assert url == "https://www.okx.com/api/v5/market/ticker"
        assert params["instId"] == "BTC-USDT"

    def test_perp_ticker_url_same_host_different_inst(self, svc):
        url, params = svc._build_ticker_request("okx", "BTCUSDT", "perp")
        assert url == "https://www.okx.com/api/v5/market/ticker"
        assert params["instId"] == "BTC-USDT-SWAP"

    def test_perp_kline_uses_swap_inst(self, svc):
        url, params = svc._build_kline_request("okx", "BTCUSDT", "1h", 50, "perp")
        assert "okx.com/api/v5/market/candles" in url
        assert params["instId"] == "BTC-USDT-SWAP"
        assert params["bar"] == "1H"


# ── Huobi/HTX URL 路由(spot 和 perp host + 字段全不同) ─────

class TestHuobiRouting:
    def test_perp_code_format(self, svc):
        assert svc._to_huobi_perp_code("BTCUSDT") == "BTC-USDT"
        assert svc._to_huobi_perp_code("ETHUSDT") == "ETH-USDT"
        assert svc._to_huobi_perp_code("SOLUSDC") == "SOL-USDC"

    def test_spot_ticker_uses_huobi_pro(self, svc):
        url, params = svc._build_ticker_request("huobi", "BTCUSDT", "spot")
        assert url == "https://api.huobi.pro/market/detail/merged"
        assert params == {"symbol": "btcusdt"}  # spot 用小写 symbol 字段

    def test_perp_ticker_uses_futures_htx_com(self, svc):
        url, params = svc._build_ticker_request("huobi", "BTCUSDT", "perp")
        # F1 修复: 旧 api.hbdm.com 在部分网络被墙,改 futures.htx.com
        assert "futures.htx.com" in url
        assert "linear-swap-ex" in url
        assert params == {"contract_code": "BTC-USDT"}  # perp 用大写 contract_code

    def test_perp_kline_uses_correct_path_and_period(self, svc):
        url, params = svc._build_kline_request("huobi", "BTCUSDT", "1h", 50, "perp")
        assert "futures.htx.com/linear-swap-ex/market/history/kline" in url
        assert params["contract_code"] == "BTC-USDT"
        assert params["period"] == "60min"  # huobi 周期映射

    def test_perp_orderbook_no_depth_param(self, svc):
        # 火币线性永续 depth 接口不接 depth 参数(只接 type)
        _, params = svc._build_orderbook_request("huobi", "BTCUSDT", 20, "perp")
        assert "depth" not in params
        assert params["type"] == "step0"


# ── 不支持的交易所 ───────────────────────────────────────

class TestUnsupportedExchange:
    def test_ticker_raises(self, svc):
        with pytest.raises(AppException) as e:
            svc._build_ticker_request("kraken", "BTCUSDT", "spot")
        assert "不支持的交易所" in e.value.message

    def test_kline_raises(self, svc):
        with pytest.raises(AppException):
            svc._build_kline_request("kraken", "BTCUSDT", "1h", 50, "spot")

    def test_orderbook_raises(self, svc):
        with pytest.raises(AppException):
            svc._build_orderbook_request("kraken", "BTCUSDT", 20, "spot")
