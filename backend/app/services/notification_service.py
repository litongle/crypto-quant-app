"""
通知服务 - 统一通知出口

支持渠道:
- Telegram Bot（即时推送，需翻墙）
- 邮箱 SMTP（国内通用兜底，QQ/163/Gmail 均可）

通知类型:
- 策略信号 (signal)
- 止损触发 (stop_loss)
- 止盈触发 (take_profit)
- 大额成交 (large_trade)
- 风控告警 (risk_alert)
- 系统通知 (system)
"""

import logging
import re
from datetime import UTC, datetime
from decimal import Decimal
from email.message import EmailMessage
from typing import Literal

import aiosmtplib
import httpx

logger = logging.getLogger(__name__)

# 通知渠道从 runtime_config 拉取的 key 列表
_NOTIFICATION_KEYS: list[str] = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_TO",
    "SMTP_USE_TLS",
]

NotificationType = Literal[
    "signal", "stop_loss", "take_profit", "large_trade", "risk_alert", "system"
]


class NotificationService:
    """统一通知服务"""

    def __init__(self):
        self._http_client: httpx.AsyncClient | None = None

    async def _load_config(self) -> dict[str, str | None]:
        """每次发送时从 runtime_config 拉最新配置。

        独立的 session（不复用调用方的）— 通知服务跨任何上下文调用，
        包括后台任务/启动钩子，自带 session 避免相互纠缠。
        """
        from app.database import get_session_maker
        from app.services.runtime_config_service import RuntimeConfigService

        session_maker = await get_session_maker()
        async with session_maker() as session:
            return await RuntimeConfigService(session).get_many(_NOTIFICATION_KEYS)

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
        results: dict = {"telegram": False, "email": False, "errors": []}
        cfg = await self._load_config()

        # Telegram
        token = cfg.get("TELEGRAM_BOT_TOKEN")
        chat_id = cfg.get("TELEGRAM_CHAT_ID")
        if token and chat_id:
            try:
                await self._send_telegram(message, token, chat_id)
                results["telegram"] = True
                logger.info("[Notification] Telegram 通知发送成功: %s", title)
            except Exception as exc:
                results["errors"].append(f"Telegram: {exc}")
                logger.warning("[Notification] Telegram 发送失败: %s", exc)

        # 邮箱 SMTP
        if all(cfg.get(k) for k in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_TO")):
            try:
                await self._send_email(cfg, title, message)
                results["email"] = True
                logger.info("[Notification] 邮件通知发送成功: %s", title)
            except Exception as exc:
                results["errors"].append(f"Email: {exc}")
                logger.warning("[Notification] 邮件发送失败: %s", exc)

        # 如果没有配置任何渠道，记录日志
        if not results["telegram"] and not results["email"]:
            logger.info("[Notification] 未配置通知渠道，仅记录日志: %s - %s", title, message[:200])

        # 通知有错误时落 audit event — 用户在前端事件页（type=system, sev=warning）
        # 能看到通知失败记录,而不是只能 docker logs 才能查。用户反馈「前端
        # 也看不见」的核心痛点之一。
        if results["errors"]:
            try:
                from app.database import get_session_maker
                from app.services import audit_service

                session_maker = await get_session_maker()
                await audit_service.log_system(
                    session_maker,
                    event="notification.failed",
                    summary=f"通知发送失败: {title}",
                    severity="warning",
                    detail={
                        "notification_type": notification_type,
                        "title": title,
                        "errors": results["errors"],
                        "telegram_sent": results["telegram"],
                        "email_sent": results["email"],
                    },
                )
            except Exception as audit_exc:
                # 审计失败不能阻塞主流程（也别 cascade 触发通知,会无限循环）
                logger.warning("[Notification] audit log 失败: %s", audit_exc)

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

    async def _send_email(self, cfg: dict[str, str | None], title: str, message: str) -> None:
        """发送告警邮件（同时提供 HTML 与纯文本两种格式，由邮件客户端自选）"""
        from_addr = cfg.get("SMTP_FROM") or cfg["SMTP_USERNAME"]
        msg = EmailMessage()
        msg["Subject"] = f"[CryptoQuant] {title}"
        msg["From"] = from_addr
        msg["To"] = cfg["SMTP_TO"]
        # 纯文本（剥 HTML 标签）
        plain = re.sub(r"<[^>]+>", "", message)
        msg.set_content(plain)
        # HTML 备用视图
        msg.add_alternative(
            f"<h3>{title}</h3><div>{message.replace(chr(10), '<br>')}</div>",
            subtype="html",
        )
        use_tls = str(cfg.get("SMTP_USE_TLS") or "true").lower() == "true"
        await aiosmtplib.send(
            msg,
            hostname=cfg["SMTP_HOST"],
            port=int(cfg.get("SMTP_PORT") or 465),
            username=cfg["SMTP_USERNAME"],
            password=cfg["SMTP_PASSWORD"],
            use_tls=use_tls,
            start_tls=not use_tls,
            timeout=10,
        )


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
