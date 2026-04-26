"""
策略 API - 移动端对接版

P1-5: 删除冗余 inst_ 前缀，ID 直接用整数
P1-6: 策略实例创建上限（每用户最多 20 个）
补充: 业务错误统一用 HTTPException
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.user import User
from app.models.order import Order
from app.models.strategy import StrategyInstance
from app.api.deps import get_current_user
from app.services.strategy_service import StrategyService
from app.core.schemas import APIResponse
from app.core.performance import PerformanceCalculator, PerformanceReport
from app.core.rule_engine import validate_rules, describe_rules, RuleValidationError

router = APIRouter()


# ============ 常量 ============

# P1-6: 每用户最多策略实例数
MAX_INSTANCES_PER_USER = 20


# ============ 请求模型 ============

class CreateStrategyRequest(BaseModel):
    """创建策略请求"""
    name: str = Field(..., description="实例名称", min_length=1, max_length=100)
    templateId: str = Field(..., description="策略模板ID")
    exchange: str = Field(..., description="交易所 (binance/okx/htx)")
    symbol: str = Field(..., description="交易对 (如 BTCUSDT)")
    accountId: int | None = Field(None, description="绑定的交易所账户ID，自动下单时使用")
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
    type: Literal["int", "double", "select", "rules"]
    default: int | float | str | None = None
    min: int | float | None = None
    max: int | float | None = None
    step: int | float | None = None
    options: list[dict] | None = None
    description: str | None = None


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
        "rule_custom": "tune",
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
            "strategyType": t.get("strategy_type", ""),
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
    "rule_custom": 6,
}

# 反向映射：数据库 template_id (int) → 前端 code (str)
_TEMPLATE_ID_TO_CODE = {v: k for k, v in _STR_ID_MAP.items()}


# ============ 辅助函数 ============

def _parse_instance_id(instance_id: str | int) -> int:
    """解析策略实例ID — 支持 "123" 和 "inst_123" 两种格式（兼容旧客户端）"""
    if isinstance(instance_id, int):
        return instance_id
    s = str(instance_id)
    # P1-5: 兼容旧客户端的 inst_ 前缀，新客户端直接传数字
    if s.startswith("inst_"):
        s = s[5:]
    try:
        return int(s)
    except ValueError:
        raise HTTPException(status_code=422, detail="策略实例ID格式无效")


def _format_instance(inst: StrategyInstance) -> dict:
    """统一格式化策略实例响应 — P1-5: id 直接用整数，不再加 inst_ 前缀"""
    template_code = _TEMPLATE_ID_TO_CODE.get(inst.template_id, str(inst.template_id))
    template_name = "未知策略"
    for t in PREDEFINED_TEMPLATES:
        if t["id"] == template_code:
            template_name = t["name"]
            break

    return {
        "id": inst.id,  # 直接用整数 ID
        "name": inst.name,
        "templateId": template_code,
        "templateName": template_name,
        "status": inst.status,
        "exchange": inst.exchange,
        "symbol": inst.symbol,
        "accountId": inst.account_id,
        "isLive": inst.account_id is not None,
        "totalPnl": float(inst.total_pnl or 0),
        "totalPnlPercent": float(inst.total_pnl_percent or 0),
        "winRate": float(inst.win_rate or 0),
        "totalTrades": inst.total_trades or 0,
        "createdAt": inst.created_at.isoformat() + "Z" if inst.created_at else "",
        "updatedAt": inst.updated_at.isoformat() + "Z" if inst.updated_at else "",
    }


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

    return APIResponse(data=[_format_instance(i) for i in instances])


@router.post("/instances", status_code=status.HTTP_201_CREATED)
async def create_strategy(
    request: CreateStrategyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """创建策略实例"""
    # P1-6: 检查实例创建上限
    count_result = await session.execute(
        select(func.count(StrategyInstance.id)).where(
            StrategyInstance.user_id == current_user.id
        )
    )
    current_count = count_result.scalar() or 0
    if current_count >= MAX_INSTANCES_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"策略实例数量已达上限 ({MAX_INSTANCES_PER_USER}个)，请删除后再创建",
        )

    # 验证模板存在
    template_exists = any(t["id"] == request.templateId for t in PREDEFINED_TEMPLATES)
    if not template_exists:
        raise HTTPException(status_code=404, detail="策略模板不存在")

    # 映射 string templateId -> int template_id
    template_id = _STR_ID_MAP.get(request.templateId, 1)

    # 创建实例
    service = StrategyService(session)
    instance = await service.create_instance(
        user=current_user,
        template_id=template_id,
        name=request.name,
        symbol=request.symbol.upper(),
        exchange=request.exchange.lower(),
        params=request.params,
        risk_params={},
        direction="both",
        account_id=request.accountId,
    )

    return APIResponse(data={
        "id": instance.id,
        "status": instance.status,
    })


@router.get("/instances/{instance_id}")
async def get_strategy(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """获取策略实例详情"""
    inst_id = _parse_instance_id(instance_id)

    service = StrategyService(session)
    instance = await service.get_instance(inst_id)

    if not instance:
        raise HTTPException(status_code=404, detail="策略不存在")

    if instance.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限访问")

    return APIResponse(data=_format_instance(instance))


@router.put("/instances/{instance_id}")
async def update_strategy(
    instance_id: str,
    request: UpdateStrategyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """更新策略参数"""
    inst_id = _parse_instance_id(instance_id)

    service = StrategyService(session)

    update_data = {}
    if request.name:
        update_data["name"] = request.name
    if request.params:
        update_data["params"] = request.params

    instance = await service.update_instance(
        instance_id=inst_id,
        user_id=current_user.id,
        **update_data,
    )

    if not instance:
        raise HTTPException(status_code=404, detail="策略不存在或无权限")

    return APIResponse(data={
        "id": instance.id,
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
    inst_id = _parse_instance_id(instance_id)

    service = StrategyService(session)
    instance = await service.start_instance(inst_id, current_user.id)

    if not instance:
        raise HTTPException(status_code=404, detail="策略不存在或无权限")

    return APIResponse(data={
        "id": instance.id,
        "status": instance.status,
    })


@router.post("/instances/{instance_id}/stop")
async def stop_strategy(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """停止策略"""
    inst_id = _parse_instance_id(instance_id)

    service = StrategyService(session)
    instance = await service.stop_instance(inst_id, current_user.id)

    if not instance:
        raise HTTPException(status_code=404, detail="策略不存在或无权限")

    return APIResponse(data={
        "id": instance.id,
        "status": instance.status,
    })


@router.delete("/instances/{instance_id}")
async def delete_strategy(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """删除策略"""
    inst_id = _parse_instance_id(instance_id)

    service = StrategyService(session)
    success = await service.delete_instance(inst_id, current_user.id)

    if not success:
        raise HTTPException(status_code=404, detail="策略不存在或无权限")

    return APIResponse(message="删除成功")


@router.get("/instances/{instance_id}/performance")
async def get_strategy_performance(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse:
    """获取策略绩效报告"""
    inst_id = _parse_instance_id(instance_id)

    # 查询策略实例
    service = StrategyService(session)
    instance = await service.get_instance(inst_id)
    if not instance:
        raise HTTPException(status_code=404, detail="策略不存在")
    if instance.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限访问")

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


# ============ 规则引擎 API ============

class ValidateRulesRequest(BaseModel):
    """规则校验请求"""
    rules: dict = Field(..., description="JSON 规则定义，含 buy_rules/sell_rules/risk")


@router.post("/validate-rules")
async def validate_strategy_rules(
    request: ValidateRulesRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> APIResponse:
    """校验规则 DSL 格式，返回校验结果和可读描述"""
    errors = validate_rules(request.rules)

    if errors:
        return APIResponse(data={
            "valid": False,
            "errors": errors,
            "description": "",
        })

    description = describe_rules(request.rules)
    return APIResponse(data={
        "valid": True,
        "errors": [],
        "description": description,
    })
