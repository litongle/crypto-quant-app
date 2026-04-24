"""
策略 API - 移动端对接版
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.user import User
from app.models.order import Order
from app.api.deps import get_current_user
from app.services.strategy_service import StrategyService
from app.core.schemas import APIResponse
from app.core.performance import PerformanceCalculator, PerformanceReport

router = APIRouter()


# ============ 请求模型 ============

class CreateStrategyRequest(BaseModel):
    """创建策略请求"""
    name: str = Field(..., description="实例名称", min_length=1, max_length=100)
    templateId: str = Field(..., description="策略模板ID")
    exchange: str = Field(..., description="交易所 (binance/okx/htx)")
    symbol: str = Field(..., description="交易对 (如 BTCUSDT)")
    params: dict = Field(default_factory=dict, description="策略参数")


class UpdateStrategyRequest(BaseModel):
    """更新策略请求"""
    name: str | None = None
    params: dict | None = None


# ============ 响应模型 ============

class ParamSchema(BaseModel):
    """参数定义"""
    key: str
    name: str
    type: Literal["int", "double", "select"]
    default: int | float | str
    min: int | float | None = None
    max: int | float | None = None
    step: int | float | None = None
    options: list[dict] | None = None


class StrategyTemplateResponse(BaseModel):
    """策略模板响应"""
    id: str
    name: str
    description: str
    icon: str
    isActive: bool = True
    params: list[ParamSchema] = []


class StrategyInstanceResponse(BaseModel):
    """策略实例响应"""
    id: str
    name: str
    templateId: str
    templateName: str
    status: Literal["running", "stopped", "paused"]
    totalPnL: float = 0
    totalPnLPercent: float = 0
    winRate: float = 0
    totalTrades: int = 0
    createdAt: str
    updatedAt: str


class CreateInstanceResponse(BaseModel):
    """创建策略响应"""
    id: str
    status: str


# ============ 策略模板定义 ============

# 从 seed_data 统一加载模板定义，避免硬编码重复
from app.seed_data import STRATEGY_TEMPLATES as _SEED_TEMPLATES


def _build_predefined_templates() -> list[dict]:
    """从 seed_data 构建移动端响应格式的模板列表"""
    templates = []
    # 模板ID到图标映射
    icon_map = {
        "ma_cross": "trending_up",
        "grid": "grid_view",
        "rsi": "show_chart",
        "bollinger": "bandcamp",
        "martingale": "casino",
    }
    for t in _SEED_TEMPLATES:
        params = []
        for p in t["params_schema"].get("params", []):
            params.append(ParamSchema(
                key=p["key"],
                name=p["name"],
                type=p.get("type", "int"),
                default=p.get("default", 0),
                min=p.get("min"),
                max=p.get("max"),
                step=p.get("step"),
                options=None,
            ).model_dump())
        templates.append({
            "id": t["code"],
            "name": t["name"],
            "description": t["description"],
            "icon": icon_map.get(t["code"], "info"),
            "isActive": True,
            "params": params,
        })
    return templates


PREDEFINED_TEMPLATES = _build_predefined_templates()

# 字符串 code → 数据库整数 template_id 映射
_STR_ID_MAP = {
    "ma_cross": 1,
    "rsi": 2,
    "bollinger": 3,
    "grid": 4,
    "martingale": 5,
}

# 反向映射：数据库 template_id (int) → 前端 code (str)
_TEMPLATE_ID_TO_CODE = {v: k for k, v in _STR_ID_MAP.items()}


# ============ 路由 ============

@router.get("/templates")
async def get_strategy_templates() -> APIResponse:
    """获取策略模板列表"""
    return APIResponse(data=PREDEFINED_TEMPLATES)


@router.get("/instances")
async def get_user_strategies(
    current_user: Annotated[User, Depends(get_current_user)],
    status: str = Query("all", description="状态筛选 (running/stopped/all)"),
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """获取用户的策略实例列表"""
    service = StrategyService(session)
    instances = await service.get_user_instances(current_user.id, active_only=False)

    # 过滤状态
    if status != "all":
        instances = [i for i in instances if i.status == status]

    # 格式化为移动端响应
    result = []
    for inst in instances:
        # 获取模板 code 和名称
        template_code = _TEMPLATE_ID_TO_CODE.get(inst.template_id, str(inst.template_id))
        template_name = "未知策略"
        for t in PREDEFINED_TEMPLATES:
            if t["id"] == template_code:
                template_name = t["name"]
                break

        result.append({
            "id": f"inst_{inst.id}",
            "name": inst.name,
            "templateId": template_code,
            "templateName": template_name,
            "status": inst.status,
            "totalPnl": float(inst.total_pnl or 0),
            "totalPnlPercent": float(inst.total_pnl_percent or 0),
            "winRate": float(inst.win_rate or 0),
            "totalTrades": inst.total_trades or 0,
            "createdAt": inst.created_at.isoformat() + "Z" if inst.created_at else "",
            "updatedAt": inst.updated_at.isoformat() + "Z" if inst.updated_at else "",
        })

    return APIResponse(data=result)


@router.post("/instances")
async def create_strategy(
    request: CreateStrategyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """创建策略实例"""
    service = StrategyService(session)

    # 验证模板存在
    template_exists = any(t["id"] == request.templateId for t in PREDEFINED_TEMPLATES)
    if not template_exists:
        return APIResponse(code=3001, message="策略模板不存在")

    # 映射 string templateId -> int template_id
    template_id = _STR_ID_MAP.get(request.templateId, 1)

    # 创建实例
    instance = await service.create_instance(
        user=current_user,
        template_id=template_id,
        name=request.name,
        symbol=request.symbol.upper(),
        exchange=request.exchange.lower(),
        params=request.params,
        risk_params={},
        direction="both",
    )

    return APIResponse(data={
        "id": f"inst_{instance.id}",
        "status": instance.status,
    })


@router.get("/instances/{instance_id}")
async def get_strategy(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """获取策略实例详情"""
    # 解析 instance_id (格式: inst_123)
    try:
        if instance_id.startswith("inst_"):
            instance_id = int(instance_id.replace("inst_", ""))
        else:
            instance_id = int(instance_id)
    except ValueError:
        return APIResponse(code=3001, message="策略实例ID无效")

    service = StrategyService(session)
    instance = await service.get_instance(instance_id)

    if not instance:
        return APIResponse(code=3001, message="策略不存在")

    if instance.user_id != current_user.id:
        return APIResponse(code=1002, message="无权限访问")

    # 获取模板 code 和名称
    template_code = _TEMPLATE_ID_TO_CODE.get(instance.template_id, str(instance.template_id))
    template_name = "未知策略"
    for t in PREDEFINED_TEMPLATES:
        if t["id"] == template_code:
            template_name = t["name"]
            break

    return APIResponse(data={
        "id": f"inst_{instance.id}",
        "name": instance.name,
        "templateId": template_code,
        "templateName": template_name,
        "status": instance.status,
        "totalPnl": float(instance.total_pnl or 0),
        "totalPnlPercent": float(instance.total_pnl_percent or 0),
        "winRate": float(instance.win_rate or 0),
        "totalTrades": instance.total_trades or 0,
        "createdAt": instance.created_at.isoformat() + "Z" if instance.created_at else "",
        "updatedAt": instance.updated_at.isoformat() + "Z" if instance.updated_at else "",
    })


@router.put("/instances/{instance_id}")
async def update_strategy(
    instance_id: str,
    request: UpdateStrategyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """更新策略参数"""
    try:
        if instance_id.startswith("inst_"):
            instance_id = int(instance_id.replace("inst_", ""))
        else:
            instance_id = int(instance_id)
    except ValueError:
        return APIResponse(code=3001, message="策略实例ID无效")

    service = StrategyService(session)

    update_data = {}
    if request.name:
        update_data["name"] = request.name
    if request.params:
        update_data["params"] = request.params

    instance = await service.update_instance(
        instance_id=instance_id,
        user_id=current_user.id,
        **update_data,
    )

    if not instance:
        return APIResponse(code=3001, message="策略不存在")

    return APIResponse(data={
        "id": f"inst_{instance.id}",
        "name": instance.name,
        "status": instance.status,
        "updatedAt": instance.updated_at.isoformat() + "Z" if instance.updated_at else "",
    })


@router.post("/instances/{instance_id}/start")
async def start_strategy(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """启动策略"""
    try:
        if instance_id.startswith("inst_"):
            instance_id = int(instance_id.replace("inst_", ""))
        else:
            instance_id = int(instance_id)
    except ValueError:
        return APIResponse(code=3001, message="策略实例ID无效")

    service = StrategyService(session)
    instance = await service.start_instance(instance_id, current_user.id)

    if not instance:
        return APIResponse(code=3001, message="策略不存在或无权限")

    return APIResponse(data={
        "id": f"inst_{instance.id}",
        "status": instance.status,
    })


@router.post("/instances/{instance_id}/stop")
async def stop_strategy(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """停止策略"""
    try:
        if instance_id.startswith("inst_"):
            instance_id = int(instance_id.replace("inst_", ""))
        else:
            instance_id = int(instance_id)
    except ValueError:
        return APIResponse(code=3001, message="策略实例ID无效")

    service = StrategyService(session)
    instance = await service.stop_instance(instance_id, current_user.id)

    if not instance:
        return APIResponse(code=3001, message="策略不存在或无权限")

    return APIResponse(data={
        "id": f"inst_{instance.id}",
        "status": instance.status,
    })


@router.delete("/instances/{instance_id}")
async def delete_strategy(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """删除策略"""
    try:
        if instance_id.startswith("inst_"):
            instance_id = int(instance_id.replace("inst_", ""))
        else:
            instance_id = int(instance_id)
    except ValueError:
        return APIResponse(code=3001, message="策略实例ID无效")

    service = StrategyService(session)
    success = await service.delete_instance(instance_id, current_user.id)

    if not success:
        return APIResponse(code=3001, message="策略不存在或无权限")

    return APIResponse(message="删除成功")


@router.get("/instances/{instance_id}/performance")
async def get_strategy_performance(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """获取策略绩效报告"""
    try:
        if instance_id.startswith("inst_"):
            inst_id = int(instance_id.replace("inst_", ""))
        else:
            inst_id = int(instance_id)
    except ValueError:
        return APIResponse(code=3001, message="策略实例ID无效")

    # 查询策略实例
    service = StrategyService(session)
    instance = await service.get_instance(inst_id)
    if not instance or instance.user_id != current_user.id:
        return APIResponse(code=3001, message="策略不存在或无权限")

    # 查询该策略的所有已成交订单
    result = await session.execute(
        select(Order)
        .where(
            Order.strategy_instance_id == inst_id,
            Order.status.in_(["filled", "partial"]),
        )
        .order_by(Order.created_at)
    )
    orders = result.scalars().all()

    # 计算绩效
    initial_capital = Decimal(str(instance.params.get("initial_capital", 100000)))
    report = PerformanceCalculator.from_order_models(orders, initial_capital)

    return APIResponse(data=report.to_dict())
