"""K 线缓存模型 — 回测加速

回测每次拉 5 万根 K 线（60s 超时）是卡死主因。同 (exchange, symbol, interval, ts)
唯一约束 + 复合索引让重复回测秒级命中本地缓存，只缺失段才走 REST。

注意：写入端必须排除"未完成 K 线"（ts >= now - interval_ms 的最后一根可能尚未收盘），
否则缓存到错误价格。这层语义由 backtest_service._fetch_klines 控制，本表不约束。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KlineCache(Base):
    """K 线本地缓存（按交易所/交易对/周期/起始时间唯一）"""

    __tablename__ = "kline_cache"
    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "symbol",
            "interval",
            "ts",
            name="uq_kline_cache_exchange_symbol_interval_ts",
        ),
        Index(
            "ix_kline_cache_lookup",
            "exchange",
            "symbol",
            "interval",
            "ts",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(40), nullable=False)
    interval: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="1m/5m/15m/1h/4h/1d 等"
    )
    ts: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="K线起始时间 epoch 毫秒")

    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<KlineCache(exchange={self.exchange}, symbol={self.symbol}, "
            f"interval={self.interval}, ts={self.ts})>"
        )
