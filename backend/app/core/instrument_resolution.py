"""
交易品种解析：与前端 symbol-selector 的 *.P 永续后缀及 params.market_type 对齐。

用于 StrategyRunner / OrderService 在调用交易所适配器前得到统一的
「现货/永续」语义与契约符号（尤其 OKX 须 ETH-USDT-SWAP）。
"""


def strip_ui_perp_suffix(symbol: str) -> tuple[str, bool]:
    s = (symbol or "").strip().upper()
    if s.endswith(".P"):
        return s[:-2], True
    return s, False


def is_perp_from_params(params: dict | None) -> bool:
    if not params:
        return False
    mt = str(params.get("market_type") or params.get("market") or "").lower()
    return mt in ("perp", "futures", "future", "swap")


def resolve_execution_context(symbol: str, params: dict | None) -> tuple[str, bool]:
    """返回 (基础符号如 ETHUSDT, 是否按永续路由)."""
    base, from_suffix = strip_ui_perp_suffix(symbol)
    return base, from_suffix or is_perp_from_params(params)


def adapter_symbol_for_klines(exchange: str, base_symbol: str, is_perp: bool) -> str:
    """公开 K 线请求用的符号：OKX 永续须 instId 含 -SWAP。"""
    ex = (exchange or "").lower()
    sym = base_symbol.upper()
    if not is_perp:
        return sym
    if ex == "okx":
        return _okx_swap_inst_id(sym) or sym
    return sym


def adapter_symbol_for_okx_order(base_symbol: str, is_perp: bool) -> str:
    """OKX 下单 instId；现货仍用 ETH-USDT 形式。"""
    sym = base_symbol.upper()
    if not is_perp:
        return sym
    return _okx_swap_inst_id(sym) or sym


def _okx_swap_inst_id(concat_pair: str) -> str | None:
    """ETHUSDT -> ETH-USDT-SWAP"""
    for quote in ("USDT", "USDC", "BUSD"):
        if concat_pair.endswith(quote) and len(concat_pair) > len(quote):
            base = concat_pair[: -len(quote)]
            return f"{base}-{quote}-SWAP"
    return None
