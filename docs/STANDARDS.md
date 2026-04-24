# 币钱袋 - 代码规范 & 审查标准

> v1.1 | 2026-04-24 | 整合自：CODE_REVIEW_PROCESS.md + CODE_STANDARDS.md + ARCHITECTURE_REVIEW.md

---

## 一、问题严重等级

| 等级 | 定义 | 处理方式 |
|------|------|---------|
| **P0** 🔴 | 安全漏洞、资金风险、数据损坏 | 必须立即修复，阻塞合并 |
| **P1** 🟠 | 功能错误、接口不一致、核心逻辑缺陷 | 必须修复后合并 |
| **P2** 🟡 | 架构不合理、性能隐患、代码重复 | 应修复，可创建 Issue 跟进 |
| **P3** 🔵 | 风格优化、命名改善 | 建议改进，不阻塞合并 |

---

## 二、审查 Checklist（PR 必过）

### 安全性（SEC）

| 检查项 | 等级 |
|--------|------|
| 无硬编码密钥/凭证（安装向导生成，开发模式有占位值） | P0 |
| API Key 加密存储（AES-256 Fernet） | P0 |
| 所有业务端点有认证（除 /login /register /health /setup/*） | P0 |
| Refresh Token 必须验证 token_type="refresh" | P0 |
| 金融数值必须有范围校验（gt=0） | P0 |
| JWT payload.sub 类型安全转换（str→int） | P1 |
| CORS 配置最小化（禁止通配符 + credentials 组合） | P1 |
| 日志不输出敏感信息（token/密码/API Key） | P1 |

### 正确性（COR）

| 检查项 | 等级 |
|--------|------|
| 金融计算使用 Decimal，禁止 float | P0 |
| Model 字段与 Service 层访问一致 | P1 |
| 回测禁止用随机数伪造指标 | P1 |

### 交易所适配器（ARC-EX）

| 检查项 | 等级 |
|--------|------|
| 重试+限流：指数退避（1→2→4s），下单不重试，查询3次 | P1 |
| 异常细分：RateLimitError / NetworkError / OrderRejectedError | P1 |
| 安全 Decimal：`_safe_decimal()` / `_safe_divide()` 防数值异常 | P0 |
| httpx.AsyncClient 单例复用（类级别 `_shared_client`） | P1 |

### 策略引擎（ARC-STRAT）

| 检查项 | 等级 |
|--------|------|
| 策略实现继承 BaseStrategy，必须实现 analyze() | P1 |
| Signal 数据结构完整（action/confidence/entry/stop_loss/take_profit/reason） | P1 |
| StrategyRunner 60s 防抖避免重复信号 | P2 |
| 金融计算使用 Decimal，禁止 float | P0 |
| 交易所 API 字段映射已验证 | P1 |

### 架构（ARC）

| 检查项 | 等级 |
|--------|------|
| 无跨文件重复核心逻辑 | P1 |
| 分层正确：API → Service → Repository → Model | P1 |
| 依赖注入规范（通过 FastAPI Depends） | P2 |
| 禁止模块级缓存 settings（支持运行时热重载） | P1 |

### 可维护性（MNT）

| 检查项 | 等级 |
|--------|------|
| 使用 logging，禁止 print() | P1 |
| 函数签名有完整类型注解 | P2 |
| 无魔法数字（提取命名常量） | P2 |

### 性能（PRF）

| 检查项 | 等级 |
|--------|------|
| httpx.AsyncClient 单例复用，禁止每次请求新建 | P1 |
| Redis 连接池全局初始化需加锁（asyncio.Lock） | P1 |
| 关联查询使用 selectinload，禁止 N+1 | P1 |
| 高频数据有 Redis 缓存（行情 TTL 10s） | P2 |

### 测试（TST）

| 检查项 | 等级 |
|--------|------|
| 认证绕过/越权访问有测试用例 | P0 |
| 核心业务逻辑覆盖率 ≥ 80% | P1 |
| 每个 API 端点至少 1 正向 + 1 异常测试 | P1 |

---

## 三、Python 后端规范

### 命名

```python
# 模块: snake_case | 类: PascalCase | 函数/变量: snake_case | 常量: UPPER_SNAKE
class UserService:
    MAX_RETRY_COUNT = 3
    
    async def get_user_by_id(self, user_id: int) -> User | None:
        ...
```

### 金融计算（强制）

```python
from decimal import Decimal

# ❌ 禁止
price = 0.1 * 100  # 精度丢失

# ✅ 必须
def calculate_pnl(price: Decimal, quantity: Decimal) -> Decimal:
    return price * quantity
```

### 日志

```python
import logging
logger = logging.getLogger(__name__)

# ❌  print("user_id:", user_id)
# ✅
logger.info("user_created", extra={"user_id": user_id, "action": "register"})
```

### FastAPI 端点模板

```python
@router.get("/endpoint", response_model=ResponseModel)
async def endpoint_name(
    current_user: CurrentUser,          # 认证依赖
    session: DbSession,                  # 数据库依赖
    param: str = Query(...),
) -> ResponseModel:
    """端点说明"""
    service = SomeService(session)
    return await service.do_something(current_user.id, param)
```

---

## 四、Dart/Flutter 规范

### 命名

```dart
// 文件: snake_case | 类: PascalCase | 私有: _camelCase | 常量: kCamelCase
class StrategyProvider extends StateNotifier<AsyncValue<Strategy>> {
  static const kMaxRetries = 3;
  final ApiClient _apiClient;
  ...
}
```

### Provider 模板

```dart
// ✅ 推荐结构
final strategyProvider = FutureProvider<List<StrategyTemplate>>((ref) async {
  final service = ref.watch(strategyServiceProvider);
  return service.getTemplates();
});

// StateNotifier 用于需要状态变更的场景
class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier(this._apiClient) : super(const AuthState());
  
  Future<bool> login({required String email, required String password}) async {
    state = state.copyWith(status: AuthStatus.loading);
    // ...
  }
}
```

---

## 五、Git 提交规范

```
<type>(<scope>): <subject>

# 类型
feat     新功能
fix      Bug 修复
docs     文档更新
refactor 重构
test     测试相关
chore    构建/工具

# 示例
feat(auth): 添加 refresh token 刷新机制
fix(strategy): 修复 MA 策略计算错误
```

---

## 六、已知技术债务

| 优先级 | 问题 | 位置 | 状态 |
|--------|------|------|------|
| 🔴 P0 | 零测试覆盖率 | 全项目 | ❌ 未解决 |
| ~~🟠 P1~~ | ~~安装向导未处理 Redis 不可用情况~~ | ~~setup.py~~ | ✅ 已处理 |
| ~~🟠 P1~~ | ~~回测使用模拟价格数据（非真实 K 线）~~ | ~~backtest.py~~ | ✅ 已用 Binance 真实 K 线 |
| ~~🟠 P1~~ | ~~交易所适配器 order/balance 接口未实现~~ | ~~exchange_adapter.py~~ | ✅ 三大交易所(Binance/OKX/Huobi)已实现 |
| 🟡 P2 | 移动端 23/33 端点未对接 | mobile/services | ❌ 未解决 |
| 🟠 P1 | 自动下单未实现（StrategyRunner→OrderService） | strategy_runner.py | ❌ 需 exchange_account 关联 |
| 🟠 P1 | 数据库迁移缺少工具 | 全项目 | ❌ 需 Alembic |
| 🟡 P2 | Web 控制台测试覆盖 | backend/app/web | ❌ 未解决 |

---

## 七、架构简化建议（MVP 阶段）

> 原系统架构设计文档中的 K8s/Istio/NATS 方案为**长期演进目标**，MVP 阶段按以下简化方案执行：

| 原方案 | MVP 简化 |
|--------|---------|
| Kubernetes + Istio | Docker Compose + Nginx |
| 10+ 微服务 | 3-4 个服务（core-api / strategy-worker / market-collector） |
| Go + Python 混合 | 统一 Python（量化生态更丰富） |
| NATS/Kafka | Redis Streams（已有依赖） |

---
*本文档整合自：CODE_REVIEW_PROCESS.md、CODE_STANDARDS.md、ARCHITECTURE_REVIEW.md*
*最后更新：2026-04-24（技术债务清单更新 + 交易所/策略引擎审查标准新增）*
