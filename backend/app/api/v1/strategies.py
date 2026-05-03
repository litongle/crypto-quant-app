"""
策略 API - 移动端对接版

P1-5: 删除冗余 inst_ 前缀，ID 直接用整数
P1-6: 策略实例创建上限（每用户最多 20 个）
补充: 业务错误统一用 HTTPException
"""

from datetime import UTC
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.constants import STR_ID_MAP, TEMPLATE_ID_TO_CODE
from app.core.performance import PerformanceCalculator
from app.core.rule_engine import describe_rules, validate_rules
from app.core.schemas import APIResponse
from app.database import get_session
from app.models.order import Order
from app.models.strategy import StrategyInstance
from app.models.user import User
from app.seed_data import STRATEGY_TEMPLATES as _SEED_TEMPLATES
from app.services.strategy_service import StrategyService

router = APIRouter()


# ============ 常量 ============

# P1-6: 每用户最多策略实例数
MAX_INSTANCES_PER_USER = 20


# ============ 请求模型 ============


class CreateStrategyRequest(BaseModel):
    """创建策略请求"""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="实例名称", min_length=1, max_length=100)
    template_id: str = Field(..., alias="templateId", description="策略模板ID")
    exchange: str = Field(..., description="交易所 (binance/okx/htx)")
    symbol: str = Field(..., description="交易对 (如 BTCUSDT)")
    account_id: int | None = Field(
        None,
        alias="accountId",
        description="绑定的交易所账户ID，自动下单时使用",
    )
    params: dict = Field(default_factory=dict, description="策略参数")


class UpdateStrategyRequest(BaseModel):
    """更新策略请求"""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    exchange: str | None = None
    symbol: str | None = None
    account_id: int | None = Field(default=None, alias="accountId")
    params: dict | None = None
    workspace_state: Literal["draft", "library", "running"] | None = Field(
        default=None,
        alias="workspaceState",
    )


# ============ 响应模型 ============


class ParamSchema(BaseModel):
    """参数定义

    type 取值与前端 strategy.js renderer 对齐:
      int / double      -> range slider
      select            -> dropdown(需 options)
      rules             -> 规则构建器(rule_custom 专用)
      bool              -> checkbox
      array_int         -> 逗号分隔文本,解析为 int 列表
      array_double      -> 逗号分隔文本,解析为 float 列表
      json              -> textarea + JSON.parse
    """

    key: str
    name: str
    type: Literal[
        "int",
        "double",
        "select",
        "rules",
        "bool",
        "array_int",
        "array_double",
        "json",
    ]
    # default 容纳标量 / 列表 / 嵌套(json/array_*) / bool
    default: int | float | str | bool | list | dict | None = None
    min: int | float | None = None
    max: int | float | None = None
    step: int | float | None = None
    options: list[dict] | None = None
    description: str | None = None


class StrategyTemplateResponse(BaseModel):
    """策略模板响应"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str
    icon: str
    is_active: bool = Field(default=True, alias="isActive")
    # 策略类型(对应工厂里的 strategy_type 注册键),前端据此分发渲染:
    #   "rule" → 规则构建器(rule_custom 专用)
    #   其他   → 通用参数表单
    # 缺失会让 backtest.js / strategy.js 都把 rules 类型 param 当 slider 渲染。
    strategy_type: str = Field(default="", alias="strategyType")
    params: list[ParamSchema] = Field(default_factory=list)


class StrategyInstanceResponse(BaseModel):
    """策略实例响应"""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    template_id: str = Field(alias="templateId")
    template_name: str = Field(alias="templateName")
    status: Literal["draft", "running", "stopped", "paused"]
    workspace_state: Literal["draft", "library", "running"] = Field(alias="workspaceState")
    source_instance_id: int | None = Field(default=None, alias="sourceInstanceId")
    exchange: str = ""
    symbol: str = ""
    account_id: int | None = Field(default=None, alias="accountId")
    is_live: bool = Field(default=False, alias="isLive")
    params: dict = Field(default_factory=dict)
    total_pnl: float = Field(default=0, alias="totalPnl")
    total_pnl_percent: float = Field(default=0, alias="totalPnlPercent")
    win_rate: float = Field(default=0, alias="winRate")
    total_trades: int = Field(default=0, alias="totalTrades")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    last_started_at: str | None = Field(default=None, alias="lastStartedAt")
    last_stopped_at: str | None = Field(default=None, alias="lastStoppedAt")


class CreateInstanceResponse(BaseModel):
    """创建策略响应"""

    id: int
    status: str


# ============ 策略模板定义 ============

# 策略模板展示顺序：突出平台的“自定义运行”定位，其次展示用户自研策略，再给基础模板示例。
TEMPLATE_DISPLAY_ORDER = [
    "rule_custom",
    "rsi_layered",
    "ma_cross",
    "rsi",
    "bollinger",
    "grid",
    "martingale",
]

_TEMPLATE_DISPLAY_RANK = {code: index for index, code in enumerate(TEMPLATE_DISPLAY_ORDER)}
PUBLIC_TEMPLATE_CODES = set(TEMPLATE_DISPLAY_ORDER)


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
        "rsi_layered": "show_chart",
        "dca": "savings",
        "multi_symbol": "hub",
    }
    ordered_seed_templates = sorted(
        enumerate(_SEED_TEMPLATES),
        key=lambda item: (
            _TEMPLATE_DISPLAY_RANK.get(item[1]["code"], len(_TEMPLATE_DISPLAY_RANK) + item[0]),
            item[0],
        ),
    )
    for _, t in ordered_seed_templates:
        params = []
        for p in t["params_schema"].get("params", []):
            params.append(
                ParamSchema(
                    key=p["key"],
                    name=p["name"],
                    type=p.get("type", "int"),
                    default=p.get("default", 0),
                    min=p.get("min"),
                    max=p.get("max"),
                    step=p.get("step"),
                    options=p.get("options"),
                    description=p.get("description"),
                ).model_dump()
            )
        templates.append(
            {
                "id": t["code"],
                "name": t["name"],
                "description": t["description"],
                "icon": icon_map.get(t["code"], "info"),
                "isActive": True,
                "strategyType": t.get("strategy_type") or t.get("code", ""),
                "params": params,
            }
        )
    return templates

ALL_PREDEFINED_TEMPLATES = _build_predefined_templates()
PREDEFINED_TEMPLATES = [
    template for template in ALL_PREDEFINED_TEMPLATES if template["id"] in PUBLIC_TEMPLATE_CODES
]
_TEMPLATE_NAME_BY_ID = {template["id"]: template["name"] for template in ALL_PREDEFINED_TEMPLATES}


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
        raise HTTPException(status_code=422, detail="策略实例ID格式无效") from None


def _format_instance(inst: StrategyInstance) -> dict:
    """统一格式化策略实例响应 — P1-5: id 直接用整数，不再加 inst_ 前缀"""
    template_code = TEMPLATE_ID_TO_CODE.get(inst.template_id, str(inst.template_id))
    template_name = _TEMPLATE_NAME_BY_ID.get(template_code, "未知策略")

    def _format_datetime(value):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat().replace("+00:00", "Z")

    return {
        "id": inst.id,  # 直接用整数 ID
        "name": inst.name,
        "templateId": template_code,
        "templateName": template_name,
        "status": inst.status,
        "workspaceState": inst.workspace_state,
        "sourceInstanceId": inst.source_instance_id,
        "exchange": inst.exchange,
        "symbol": inst.symbol,
        "accountId": inst.account_id,
        "isLive": inst.account_id is not None,
        "params": inst.params or {},  # 返回完整参数(含rules)
        "totalPnl": float(inst.total_pnl or 0),
        "totalPnlPercent": float(inst.total_pnl_percent or 0),
        "winRate": float(inst.win_rate or 0),
        "totalTrades": inst.total_trades or 0,
        "createdAt": _format_datetime(inst.created_at) or "",
        "updatedAt": _format_datetime(inst.updated_at) or "",
        "lastStartedAt": _format_datetime(inst.last_started_at),
        "lastStoppedAt": _format_datetime(inst.last_stopped_at),
    }


# ============ 路由 ============


@router.get("/templates")
async def get_strategy_templates() -> APIResponse[list[StrategyTemplateResponse]]:
    """获取策略模板列表 (P2-13: 类型化响应)"""
    # 通过 Schema 校验确保格式一致
    validated = [
        StrategyTemplateResponse(**t).model_dump(by_alias=True) for t in PREDEFINED_TEMPLATES
    ]
    return APIResponse(data=validated)


@router.get("/instances")
async def get_user_strategies(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str = Query("all", description="状态筛选 (running/stopped/all)"),
) -> APIResponse[list[StrategyInstanceResponse]]:
    """获取用户的策略实例列表 (P2-13: 类型化响应)"""
    service = StrategyService(session)
    instances = await service.get_user_instances(current_user.id, active_only=False)

    # 过滤状态
    if status == "running":
        instances = [i for i in instances if i.workspace_state == "running"]
    elif status == "stopped":
        instances = [i for i in instances if i.workspace_state == "library"]
    elif status != "all":
        raise HTTPException(status_code=422, detail="状态筛选仅支持 running/stopped/all")

    return APIResponse(data=[_format_instance(i) for i in instances])


@router.post("/instances", status_code=status.HTTP_201_CREATED)
async def create_strategy(
    request: CreateStrategyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse[CreateInstanceResponse]:
    """创建策略实例 (P2-13: 类型化响应)"""
    # P1-6: 检查实例创建上限
    count_result = await session.execute(
        select(func.count(StrategyInstance.id)).where(StrategyInstance.user_id == current_user.id)
    )
    current_count = count_result.scalar() or 0
    if current_count >= MAX_INSTANCES_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"策略实例数量已达上限 ({MAX_INSTANCES_PER_USER}个)，请删除后再创建",
        )

    # 验证模板存在
    template_exists = any(t["id"] == request.template_id for t in ALL_PREDEFINED_TEMPLATES)
    if not template_exists:
        raise HTTPException(status_code=404, detail="策略模板不存在")

    # 映射 string templateId -> int template_id
    template_id = STR_ID_MAP.get(request.template_id, 1)

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
        account_id=request.account_id,
    )
    await session.commit()

    return APIResponse(
        data=CreateInstanceResponse(id=str(instance.id), status=instance.status).model_dump()
    )


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

    update_data = request.model_dump(by_alias=False, exclude_unset=True)

    instance = await service.update_instance(
        instance_id=inst_id,
        user_id=current_user.id,
        **update_data,
    )

    if not instance:
        raise HTTPException(status_code=404, detail="策略不存在或无权限")
    await session.commit()

    return APIResponse(
        data={
            "id": instance.id,
            "name": instance.name,
            "status": instance.status,
            "updatedAt": instance.updated_at.isoformat() + "Z" if instance.updated_at else "",
        }
    )


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
    await session.commit()

    return APIResponse(
        data={
            "id": instance.id,
            "status": instance.status,
        }
    )


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
    await session.commit()

    return APIResponse(
        data={
            "id": instance.id,
            "status": instance.status,
        }
    )


@router.post("/instances/{instance_id}/clone-draft")
async def clone_strategy_to_draft(
    instance_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session),
) -> APIResponse[StrategyInstanceResponse]:
    """复制策略为工作台草案"""
    inst_id = _parse_instance_id(instance_id)

    service = StrategyService(session)
    instance = await service.clone_to_draft(inst_id, current_user.id)
    await session.commit()

    return APIResponse(data=_format_instance(instance))


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
    await session.commit()

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
        return APIResponse(
            data={
                "valid": False,
                "errors": errors,
                "description": "",
            }
        )

    description = describe_rules(request.rules)
    return APIResponse(
        data={
            "valid": True,
            "errors": [],
            "description": description,
        }
    )
