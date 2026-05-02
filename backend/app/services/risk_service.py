"""
风控服务 - P1-7

提供全局风险监控：
- 总敞口占比（持仓价值 / 总资产）
- 单币种集中度
- 最大回撤监控
- 风控告警阈值
"""

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exchange import ExchangeAccount, Position

logger = logging.getLogger(__name__)


class RiskService:
    """风控服务"""

    DEFAULT_ALERT_THRESHOLDS = {
        "exposure_pct": 80,
        "concentration_pct": 50,
        "drawdown_pct": -20,
    }

    def __init__(self, session: AsyncSession, alert_thresholds: dict | None = None):
        self.session = session
        self.alert_thresholds = {**self.DEFAULT_ALERT_THRESHOLDS, **(alert_thresholds or {})}

    async def get_risk_dashboard(self, user_id: int) -> dict[str, Any]:
        """获取风控仪表盘数据"""
        # 获取用户所有活跃账户
        result = await self.session.execute(
            select(ExchangeAccount).where(
                ExchangeAccount.user_id == user_id,
                ExchangeAccount.is_active,
            )
        )
        accounts = result.scalars().all()

        if not accounts:
            return self._empty_dashboard()

        account_ids = [a.id for a in accounts]

        # 总资产
        total_balance = sum(
            (a.balance or Decimal("0")) + (a.frozen_balance or Decimal("0")) for a in accounts
        )

        # 持仓价值
        result = await self.session.execute(
            select(Position).where(
                Position.account_id.in_(account_ids),
                Position.status == "open",
            )
        )
        positions = result.scalars().all()

        total_position_value = Decimal("0")
        symbol_values: dict[str, Decimal] = {}
        unrealized_pnl = Decimal("0")
        unrealized_pnl_pct = Decimal("0")

        for pos in positions:
            pos_value = (pos.current_price or pos.entry_price) * pos.quantity
            total_position_value += pos_value
            symbol_values.setdefault(pos.symbol, Decimal("0"))
            symbol_values[pos.symbol] += pos_value
            unrealized_pnl += pos.unrealized_pnl or Decimal("0")

        # 总敞口占比
        exposure_pct = (
            (total_position_value / total_balance * 100) if total_balance > 0 else Decimal("0")
        )

        # 异常状态检测：balance=0 但有持仓（穿仓/冻结/杠杆爆仓后剩余债务）
        if total_balance == 0 and total_position_value > 0:
            logger.warning(
                "[RiskService] 异常状态检测: user_id=%s, total_balance=0 但存在持仓 total_position_value=%s",
                user_id,
                total_position_value,
            )
            return self._empty_dashboard() | {
                "totalPositionValue": float(total_position_value),
                "alerts": [
                    {
                        "type": "data_anomaly",
                        "level": "danger",
                        "message": "账户余额为0但存在持仓，请检查账户状态（可能已穿仓或余额被冻结）",
                        "threshold": "N/A",
                        "current": "余额异常",
                    }
                ],
                "positionCount": len(positions),
            }

        # 已实现盈亏百分比
        if total_balance > 0:
            unrealized_pnl_pct = unrealized_pnl / total_balance * 100

        # 单币种集中度
        concentration = [
            {
                "symbol": sym,
                "value": float(val),
                "percentage": float(val / total_balance * 100) if total_balance > 0 else 0,
            }
            for sym, val in sorted(symbol_values.items(), key=lambda x: x[1], reverse=True)
        ]

        # 持仓详情
        position_details = []
        for pos in positions:
            position_details.append(
                {
                    "id": pos.id,
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "quantity": float(pos.quantity),
                    "entryPrice": float(pos.entry_price) if pos.entry_price else 0,
                    "currentPrice": float(pos.current_price) if pos.current_price else 0,
                    "positionValue": float((pos.current_price or pos.entry_price) * pos.quantity),
                    "unrealizedPnl": float(pos.unrealized_pnl or 0),
                    "unrealizedPnlPercent": float(pos.unrealized_pnl_percent or 0),
                    "accountId": pos.account_id,
                }
            )

        # 风控告警
        alerts = self._check_alerts(
            exposure_pct=exposure_pct,
            concentration=concentration,
            unrealized_pnl_pct=unrealized_pnl_pct,
            positions=position_details,
        )

        return {
            "totalBalance": float(total_balance),
            "totalPositionValue": float(total_position_value),
            "exposurePercent": float(exposure_pct),
            "unrealizedPnl": float(unrealized_pnl),
            "unrealizedPnlPercent": float(unrealized_pnl_pct),
            "concentration": concentration,
            "positions": position_details,
            "alerts": alerts,
            "positionCount": len(positions),
        }

    def _empty_dashboard(self) -> dict:
        return {
            "totalBalance": 0,
            "totalPositionValue": 0,
            "exposurePercent": 0,
            "unrealizedPnl": 0,
            "unrealizedPnlPercent": 0,
            "concentration": [],
            "positions": [],
            "alerts": [],
            "positionCount": 0,
        }

    def _check_alerts(
        self,
        exposure_pct: Decimal,
        concentration: list[dict],
        unrealized_pnl_pct: Decimal,
        positions: list[dict],
    ) -> list[dict]:
        """检查风控告警阈值"""
        alerts = []
        exposure_threshold = self.alert_thresholds["exposure_pct"]
        concentration_threshold = self.alert_thresholds["concentration_pct"]
        drawdown_threshold = self.alert_thresholds["drawdown_pct"]

        # 敞口过大
        if exposure_pct > exposure_threshold:
            alerts.append(
                {
                    "type": "exposure",
                    "level": "warning" if exposure_pct < exposure_threshold + 15 else "danger",
                    "message": f"总敞口占比 {float(exposure_pct):.1f}% 超过 {exposure_threshold}% 警戒线",
                    "threshold": exposure_threshold,
                    "current": float(exposure_pct),
                }
            )

        # 单币种过度集中
        for c in concentration:
            if c["percentage"] > concentration_threshold:
                alerts.append(
                    {
                        "type": "concentration",
                        "level": "warning"
                        if c["percentage"] < concentration_threshold + 20
                        else "danger",
                        "message": f"{c['symbol']} 集中度 {c['percentage']:.1f}% 超过 {concentration_threshold}% 警戒线",
                        "threshold": concentration_threshold,
                        "current": c["percentage"],
                    }
                )

        # 浮亏过大
        if unrealized_pnl_pct < drawdown_threshold:
            alerts.append(
                {
                    "type": "drawdown",
                    "level": "warning"
                    if unrealized_pnl_pct > drawdown_threshold - 15
                    else "danger",
                    "message": f"未实现亏损 {float(unrealized_pnl_pct):.1f}% 超过 {drawdown_threshold}% 警戒线",
                    "threshold": drawdown_threshold,
                    "current": float(unrealized_pnl_pct),
                }
            )

        return alerts
