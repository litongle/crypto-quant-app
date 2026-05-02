"""
通知服务 - 统一通知出口

支持渠道:
- Telegram Bot
- 企微 Webhook

通知类型:
- 策略信号 (signal)
- 止损触发 (stop_loss)
- 止盈触发 (take_profit)
- 大额成交 (large_trade)
- 风控告警 (risk_alert)
- 系统通知 (system)
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

NotificationType = Literal[
    "signal", "stop_loss", "take_profit", "large_trade", "risk_alert", "system"
]


class NotificationService:
    """统一通知服务"""

    def __init__(self):
        self._http_client: httpx.AsyncClient | None = None
        self._settings = get_settings()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def close(self):
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    # ── 公开 API ──────────────────────────────────────────

    async def notify_signal(
        self,
        symbol: str,
        action: str,
        confidence: float,
        entry_price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        reason: str | None = None,
        strategy_name: str | None = None,
    ) -> dict:
        """推送策略信号通知"""
        title = f"📊 策略信号 | {symbol}"
        lines = [
            f"<b>策略:</b> {strategy_name or '未知策略'}",
            f"<b>交易对:</b> {symbol}",
            f"<b>动作:</b> {'🟢 买入' if action == 'buy' else '🔴 卖出' if action == 'sell' else '⚪ 平仓'}",
            f"<b>置信度:</b> {confidence * 100:.1f}%",
        ]
        if entry_price:
            lines.append(f"<b>建议价格:</b> {float(entry_price):,.2f} USDT")
        if stop_loss:
            lines.append(f"<b>止损:</b> {float(stop_loss):,.2f} USDT")
        if take_profit:
            lines.append(f"<b>止盈:</b> {float(take_profit):,.2f} USDT")
        if reason:
            lines.append(f"<b>原因:</b> {reason}")

        lines.append(f"\n<i>{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC</i>")

        return await self._send(title, "\n".join(lines), "signal")

    async def notify_stop_loss(
        self,
        symbol: str,
        side: str,
        entry_price: Decimal,
        stop_price: Decimal,
        exit_price: Decimal,
        pnl: Decimal,
        quantity: Decimal,
        position_id: int | None = None,
    ) -> dict:
        """推送止损触发通知"""
        title = f"🛑 止损触发 | {symbol}"
        pnl_pct = (
            (exit_price - entry_price) / entry_price * 100
            if side == "long"
            else (entry_price - exit_price) / entry_price * 100
        )
        lines = [
            f"<b>交易对:</b> {symbol}",
            f"<b>方向:</b> {'📈 多头' if side == 'long' else '📉 空头'}",
            f"<b>开仓价:</b> {float(entry_price):,.2f} USDT",
            f"<b>止损价:</b> {float(stop_price):,.2f} USDT",
            f"<b>成交价:</b> {float(exit_price):,.2f} USDT",
            f"<b>数量:</b> {float(quantity):,.4f}",
            f"<b>盈亏:</b> {'🟢 +' if pnl >= 0 else '🔴 '}{float(pnl):,.2f} USDT ({pnl_pct:+.2f}%)",
        ]
        if position_id:
            lines.append(f"<b>持仓ID:</b> #{position_id}")

        lines.append(f"\n<i>{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC</i>")

        return await self._send(title, "\n".join(lines), "stop_loss")

    async def notify_take_profit(
        self,
        symbol: str,
        side: str,
        entry_price: Decimal,
        tp_price: Decimal,
        exit_price: Decimal,
        pnl: Decimal,
        quantity: Decimal,
        position_id: int | None = None,
    ) -> dict:
        """推送止盈触发通知"""
        title = f"🎯 止盈触发 | {symbol}"
        pnl_pct = (
            (exit_price - entry_price) / entry_price * 100
            if side == "long"
            else (entry_price - exit_price) / entry_price * 100
        )
        lines = [
            f"<b>交易对:</b> {symbol}",
            f"<b>方向:</b> {'📈 多头' if side == 'long' else '📉 空头'}",
            f"<b>开仓价:</b> {float(entry_price):,.2f} USDT",
            f"<b>止盈价:</b> {float(tp_price):,.2f} USDT",
            f"<b>成交价:</b> {float(exit_price):,.2f} USDT",
            f"<b>数量:</b> {float(quantity):,.4f}",
            f"<b>盈亏:</b> {'🟢 +' if pnl >= 0 else '🔴 '}{float(pnl):,.2f} USDT ({pnl_pct:+.2f}%)",
        ]
        if position_id:
            lines.append(f"<b>持仓ID:</b> #{position_id}")

        lines.append(f"\n<i>{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC</i>")

        return await self._send(title, "\n".join(lines), "take_profit")

    async def notify_large_trade(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal,
        order_value: Decimal,
        order_id: int,
    ) -> dict:
        """推送大额成交通知"""
        title = f"💰 大额成交 | {symbol}"
        lines = [
            f"<b>交易对:</b> {symbol}",
            f"<b>方向:</b> {'🟢 买入' if side == 'buy' else '🔴 卖出'}",
            f"<b>类型:</b> {order_type.upper()}",
            f"<b>数量:</b> {float(quantity):,.4f}",
            f"<b>价格:</b> {float(price):,.2f} USDT",
            f"<b>订单价值:</b> {float(order_value):,.2f} USDT",
            f"<b>订单ID:</b> #{order_id}",
            f"\n<i>{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC</i>",
        ]

        return await self._send(title, "\n".join(lines), "large_trade")

    async def notify_risk_alert(
        self,
        alert_type: str,
        message: str,
        metrics: dict | None = None,
    ) -> dict:
        """推送风控告警"""
        title = f"⚠️ 风控告警 | {alert_type}"
        lines = [f"<b>类型:</b> {alert_type}", f"<b>详情:</b> {message}"]
        if metrics:
            for k, v in metrics.items():
                lines.append(f"<b>{k}:</b> {v}")
        lines.append(f"\n<i>{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC</i>")

        return await self._send(title, "\n".join(lines), "risk_alert")

    async def notify_system(self, title: str, message: str) -> dict:
        """推送系统通知"""
        lines = [
            f"<b>{title}</b>",
            "",
            message,
            f"\n<i>{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC</i>",
        ]
        return await self._send(title, "\n".join(lines), "system")

    # ── 内部发送逻辑 ──────────────────────────────────────

    async def _send(self, title: str, message: str, notification_type: NotificationType) -> dict:
        """发送通知到所有已配置的渠道"""
        results = {"telegram": False, "wecom": False, "errors": []}

        # Telegram
        telegram_bot_token = getattr(self._settings, "telegram_bot_token", None)
        telegram_chat_id = getattr(self._settings, "telegram_chat_id", None)
        if telegram_bot_token and telegram_chat_id:
            try:
                await self._send_telegram(message, telegram_bot_token, telegram_chat_id)
                results["telegram"] = True
                logger.info("[Notification] Telegram 通知发送成功: %s", title)
            except Exception as exc:
                results["errors"].append(f"Telegram: {exc}")
                logger.warning("[Notification] Telegram 发送失败: %s", exc)

        # 企微 Webhook
        wecom_webhook_url = getattr(self._settings, "wecom_webhook_url", None)
        if wecom_webhook_url:
            try:
                await self._send_wecom(title, message, wecom_webhook_url)
                results["wecom"] = True
                logger.info("[Notification] 企微通知发送成功: %s", title)
            except Exception as exc:
                results["errors"].append(f"WeCom: {exc}")
                logger.warning("[Notification] 企微发送失败: %s", exc)

        # 如果没有配置任何渠道，记录日志
        if not results["telegram"] and not results["wecom"]:
            logger.info("[Notification] 未配置通知渠道，仅记录日志: %s - %s", title, message[:200])

        return results

    async def _send_telegram(self, message: str, bot_token: str, chat_id: str) -> None:
        """发送 Telegram 消息"""
        client = await self._get_client()
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data.get('description')}")

    async def _send_wecom(self, title: str, message: str, webhook_url: str) -> None:
        """发送企微 Webhook 消息"""
        client = await self._get_client()
        # 企微不支持 HTML，转换为 markdown
        plain_text = message.replace("<b>", "**").replace("</b>", "**")
        plain_text = plain_text.replace("<i>", "").replace("</i>", "")

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"**{title}**\n\n{plain_text}",
            },
        }
        resp = await client.post(webhook_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("errcode") != 0:
            raise RuntimeError(f"WeCom API error: {data.get('errmsg')}")


# 全局单例
notification_service = NotificationService()


# ── 便捷函数（供其他模块直接调用）─────────────────────────


async def notify_signal(
    symbol: str,
    action: str,
    confidence: float,
    **kwargs,
) -> dict:
    """便捷函数：推送策略信号"""
    return await notification_service.notify_signal(symbol, action, confidence, **kwargs)


async def notify_stop_loss(**kwargs) -> dict:
    """便捷函数：推送止损触发"""
    return await notification_service.notify_stop_loss(**kwargs)


async def notify_take_profit(**kwargs) -> dict:
    """便捷函数：推送止盈触发"""
    return await notification_service.notify_take_profit(**kwargs)


async def notify_large_trade(**kwargs) -> dict:
    """便捷函数：推送大额成交"""
    return await notification_service.notify_large_trade(**kwargs)


async def notify_risk_alert(**kwargs) -> dict:
    """便捷函数：推送风控告警"""
    return await notification_service.notify_risk_alert(**kwargs)
