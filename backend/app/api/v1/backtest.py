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
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
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

    template_id: str = Field(
        ...,
        alias="templateId",
        description="策略模板ID (ma_cross/rsi/bollinger/grid/martingale)",
    )
    symbol: str = Field(..., description="交易对 (BTCUSDT)")
    exchange: str = Field(default="binance", description="交易所")
    market: Literal["spot", "perp"] = Field(default="spot", description="市场类型")
    start_date: str = Field(..., alias="startDate", description="开始日期 YYYY-MM-DD")
    end_date: str = Field(default="", alias="endDate", description="结束日期 YYYY-MM-DD，默认今天")
    initial_capital: float = Field(
        default=100000.0,
        alias="initialCapital",
        gt=0,
        description="初始资金 USDT，必须大于0",
    )
    params: dict = Field(default_factory=dict, description="策略参数")
    analysis_window: int | None = Field(
        default=None,
        alias="analysisWindow",
        description=(
            "传给策略的K线长度：省略或0=从第1根到当前bar全量前缀；"
            "正整数=仅最近N根（省内存，长周期指标可能失真）。"
            "也可在 params.backtest_analysis_window 中设置，本字段优先。"
        ),
    )


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
    end_date = request.end_date or datetime.now().strftime("%Y-%m-%d")

    # 日期校验 — 返回正确的 HTTP 4xx 状态码
    today = datetime.now().strftime("%Y-%m-%d")
    if request.start_date > today:
        raise HTTPException(status_code=422, detail="开始日期不能是未来日期")
    if end_date > today:
        raise HTTPException(status_code=422, detail="结束日期不能是未来日期")
    if request.start_date > end_date:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")

    # 执行回测
    service = BacktestService()
    result = await service.execute_backtest(
        template_id=request.template_id,
        symbol=request.symbol,
        exchange=request.exchange,
        market=request.market,
        start_date=request.start_date,
        end_date=end_date,
        initial_capital=request.initial_capital,
        params=request.params,
        analysis_window=request.analysis_window,
    )

    # 检查错误
    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result["error"],
        )

    # 存储回测历史（异步，不阻塞返回）
    try:
        await _save_backtest_history(
            session=session,
            user_id=current_user.id,
            template_id=request.template_id,
            symbol=request.symbol,
            exchange=request.exchange,
            start_date=request.start_date,
            end_date=end_date,
            initial_capital=request.initial_capital,
            params=request.params,
            result=result,
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        # 可恢复的临时性错误（网络抖动、数据库连接），记录但不惊慌
        logger.warning("保存回测历史临时失败（网络/数据库连接）: %s", e)
    except ValueError as e:
        # 数据校验错误（如 equityCurve 过长），需要告警
        logger.error("保存回测历史失败（数据格式错误）: %s", e)
    except Exception as e:
        # 未预期错误，保留完整堆栈
        logger.exception("保存回测历史失败（未预期错误）: %s", e)

    return APIResponse(data=result)


@router.get("/history")
async def get_backtest_history(
    current_user: CurrentUser,
    session: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> APIResponse:
    """
    获取回测历史记录 (P2-17: 使用 Service 层)
    """
    from app.services.backtest_service import BacktestService

    service = BacktestService(session)
    history = await service.get_user_history(current_user.id, limit)
    return APIResponse(data=history)


@router.get("/{backtest_id}")
async def get_backtest_result(
    backtest_id: int,
    current_user: CurrentUser,
    session: DbSession,
) -> APIResponse:
    """
    获取回测结果详情 (P2-17: 使用 Service 层)
    """
    from app.services.backtest_service import BacktestService

    service = BacktestService(session)
    result = await service.get_result_by_id(backtest_id, current_user.id)

    if not result:
        raise HTTPException(status_code=404, detail="回测记录不存在")

    return APIResponse(data=result)


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
    """保存回测结果到数据库（单事务，失败自动回滚）"""
    from app.models.backtest import BacktestResult

    # 数据校验：防超限（TEXT 字段上限约 65535）
    max_field_len = 65535
    equity_curve_str = json.dumps(result.get("equityCurve", []))
    trades_str = json.dumps(result.get("trades", []))
    if len(equity_curve_str) > max_field_len:
        equity_curve_str = equity_curve_str[:max_field_len]
        logger.warning("equityCurve 截断至 %d 字符", max_field_len)
    if len(trades_str) > max_field_len:
        trades_str = trades_str[:max_field_len]
        logger.warning("trades 截断至 %d 字符", max_field_len)

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
        # 详细数据（已截断校验）
        equity_curve=equity_curve_str,
        trades=trades_str,
        # 时间
        start_time=datetime.fromisoformat(result["startTime"].rstrip("Z"))
        if result.get("startTime")
        else None,
        end_time=datetime.fromisoformat(result["endTime"].rstrip("Z"))
        if result.get("endTime")
        else None,
    )

    session.add(record)

    # 自动清理：每用户最多保留50条回测记录，超出删最老的（在同一事务内）
    max_backtest_per_user = 50
    count_result = await session.execute(
        select(BacktestResult.id)
        .where(BacktestResult.user_id == user_id)
        .order_by(desc(BacktestResult.created_at))
        .offset(max_backtest_per_user)
    )
    old_ids = [row[0] for row in count_result.all()]
    if old_ids:
        await session.execute(
            BacktestResult.__table__.delete().where(BacktestResult.id.in_(old_ids))
        )

    # 单次 commit：record + 清理要么同时成功，要么同时回滚
    await session.commit()
