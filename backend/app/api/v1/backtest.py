"""
回测 API - 完整版

支持：
- 运行回测（使用真实策略引擎 + 历史K线数据）
- 回测历史记录存储与查询
- 回测结果详情查看
- 所有 5 种策略类型
"""
import json
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.schemas import APIResponse
from app.services.backtest_service import BacktestService

logger = logging.getLogger(__name__)
router = APIRouter()


# ============ 请求模型 ============

class BacktestRequest(BaseModel):
    """回测请求"""
    templateId: str = Field(..., description="策略模板ID (ma_cross/rsi/bollinger/grid/martingale)")
    symbol: str = Field(..., description="交易对 (BTCUSDT)")
    exchange: str = Field(default="binance", description="交易所")
    startDate: str = Field(..., description="开始日期 YYYY-MM-DD")
    endDate: str = Field(default="", description="结束日期 YYYY-MM-DD，默认今天")
    initialCapital: float = Field(default=100000.0, gt=0, description="初始资金 USDT，必须大于0")
    params: dict = Field(default_factory=dict, description="策略参数")


# ============ 路由 ============

@router.post("/run")
async def run_backtest(
    request: BacktestRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> APIResponse:
    """
    运行回测

    基于给定的策略参数和时间范围，运行历史数据回测并返回绩效指标。
    使用真实策略引擎（StrategyFactory）+ Binance 公开 API K线数据。
    """
    # 解析日期
    end_date = request.endDate or datetime.now().strftime("%Y-%m-%d")

    # 执行回测
    service = BacktestService()
    result = await service.execute_backtest(
        template_id=request.templateId,
        symbol=request.symbol,
        exchange=request.exchange,
        start_date=request.startDate,
        end_date=end_date,
        initial_capital=request.initialCapital,
        params=request.params,
    )

    # 检查错误
    if "error" in result:
        return APIResponse(
            code=result.get("code", 5000),
            message=result["error"],
            data={"detail": result.get("detail", "")},
        )

    # 存储回测历史（异步，不阻塞返回）
    try:
        await _save_backtest_history(
            session=session,
            user_id=current_user.id,
            template_id=request.templateId,
            symbol=request.symbol,
            exchange=request.exchange,
            start_date=request.startDate,
            end_date=end_date,
            initial_capital=request.initialCapital,
            params=request.params,
            result=result,
        )
    except Exception as e:
        logger.warning("保存回测历史失败（不影响回测结果）: %s", e)

    return APIResponse(data=result)


@router.get("/history")
async def get_backtest_history(
    current_user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> APIResponse:
    """
    获取回测历史记录

    返回用户最近的回测历史。
    """
    from app.models.backtest import BacktestResult

    result = await session.execute(
        select(BacktestResult)
        .where(BacktestResult.user_id == current_user.id)
        .order_by(desc(BacktestResult.created_at))
        .limit(limit)
    )
    records = result.scalars().all()

    history = []
    for r in records:
        history.append({
            "id": r.id,
            "templateId": r.template_id,
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
            "createdAt": r.created_at.isoformat() + "Z" if r.created_at else "",
        })

    return APIResponse(data=history)


@router.get("/{backtest_id}")
async def get_backtest_result(
    backtest_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> APIResponse:
    """
    获取回测结果详情
    """
    from app.models.backtest import BacktestResult

    result = await session.execute(
        select(BacktestResult)
        .where(
            BacktestResult.id == backtest_id,
            BacktestResult.user_id == current_user.id,
        )
    )
    record = result.scalar_one_or_none()

    if not record:
        return APIResponse(code=3001, message="回测记录不存在")

    # 解析存储的详细数据
    equity_curve = json.loads(record.equity_curve) if record.equity_curve else []
    trades = json.loads(record.trades) if record.trades else []

    return APIResponse(data={
        "id": record.id,
        "templateId": record.template_id,
        "symbol": record.symbol,
        "exchange": record.exchange,
        "startDate": record.start_date,
        "endDate": record.end_date,
        "initialCapital": float(record.initial_capital),
        "params": json.loads(record.params) if record.params else {},

        # 绩效指标
        "totalReturn": float(record.total_return),
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

        # 详细数据
        "equityCurve": equity_curve,
        "trades": trades,

        # 时间
        "startTime": record.start_time.isoformat() + "Z" if record.start_time else None,
        "endTime": record.end_time.isoformat() + "Z" if record.end_time else None,
        "createdAt": record.created_at.isoformat() + "Z" if record.created_at else "",
    })


# ============ 内部辅助 ============

async def _save_backtest_history(
    session: AsyncSession,
    user_id: int,
    template_id: str,
    symbol: str,
    exchange: str,
    start_date: str,
    end_date: str,
    initial_capital: float,
    params: dict,
    result: dict,
) -> None:
    """保存回测结果到数据库"""
    from app.models.backtest import BacktestResult

    record = BacktestResult(
        user_id=user_id,
        template_id=template_id,
        symbol=symbol,
        exchange=exchange,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        params=json.dumps(params),
        # 绩效指标
        total_return=result.get("totalReturn", 0),
        total_return_pct=result.get("totalReturnPercent", 0),
        annual_return=result.get("annualReturn", 0),
        sharpe_ratio=result.get("sharpeRatio", 0),
        calmar_ratio=result.get("calmarRatio", 0),
        max_drawdown=result.get("maxDrawdown", 0),
        win_rate=result.get("winRate", 0),
        profit_factor=result.get("profitFactor", 0),
        total_trades=result.get("totalTrades", 0),
        profit_trades=result.get("profitTrades", 0),
        loss_trades=result.get("lossTrades", 0),
        avg_profit=result.get("avgProfit", 0),
        avg_loss=result.get("avgLoss", 0),
        # 详细数据
        equity_curve=json.dumps(result.get("equityCurve", [])),
        trades=json.dumps(result.get("trades", [])),
        # 时间
        start_time=datetime.fromisoformat(result["startTime"].rstrip("Z")) if result.get("startTime") else None,
        end_time=datetime.fromisoformat(result["endTime"].rstrip("Z")) if result.get("endTime") else None,
    )

    session.add(record)
    await session.commit()
