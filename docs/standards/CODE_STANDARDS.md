# 币钱袋 - 编码规范标准

> 版本：v1.0.0
> 日期：2026-04-21
> 状态：✅ 生效

---

## 目录

1. [通用原则](#1-通用原则)
2. [Python 后端规范](#2-python-后端规范)
3. [Dart/Flutter 前端规范](#3-dartflutter-前端规范)
4. [Git 协作规范](#4-git-协作规范)
5. [API 设计规范](#5-api-设计规范)
6. [数据库规范](#6-数据库规范)
7. [测试规范](#7-测试规范)
8. [安全规范](#8-安全规范)

---

## 1. 通用原则

### 1.1 核心价值观

```
📌 写代码是给人类阅读的，顺便让机器执行
📌 简单 > 聪明 > 复杂
📌 清晰优于巧妙
📌 命名即文档
```

### 1.2 代码审查 checklist

每次 Code Review 必须检查：

- [ ] **功能正确性** - 代码是否实现了需求？
- [ ] **边界处理** - 空值、异常值是否处理？
- [ ] **命名清晰** - 变量/函数名是否自解释？
- [ ] **无重复代码** - DRY 原则？
- [ ] **测试覆盖** - 核心逻辑有测试吗？
- [ ] **无硬编码** - 配置是否外置？
- [ ] **安全检查** - SQL注入、XSS、敏感信息？

---

## 2. Python 后端规范

### 2.1 项目结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── api/                 # API 路由
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── users.py
│   │   │   ├── strategies.py
│   │   │   └── market.py
│   │   └── deps.py          # 依赖注入
│   ├── core/                # 核心模块
│   │   ├── __init__.py
│   │   ├── security.py      # 认证/加密
│   │   └── exceptions.py     # 异常定义
│   ├── models/              # SQLAlchemy 模型
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── strategy.py
│   ├── schemas/             # Pydantic 模型
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── strategy.py
│   ├── services/             # 业务逻辑
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   └── strategy_service.py
│   ├── repositories/         # 数据访问
│   │   ├── __init__.py
│   │   ├── user_repo.py
│   │   └── strategy_repo.py
│   └── utils/                # 工具函数
│       ├── __init__.py
│       └── helpers.py
├── tests/                    # 测试
│   ├── __init__.py
│   ├── conftest.py
│   ├── api/
│   ├── services/
│   └── factories/
├── alembic/                  # 数据库迁移
│   └── versions/
├── alembic.ini
├── pyproject.toml
├── ruff.toml                # Linter 配置
└── .env.example
```

### 2.2 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块名 | snake_case | `user_service.py` |
| 类名 | PascalCase | `UserService` |
| 函数名 | snake_case | `get_user_by_id()` |
| 变量名 | snake_case | `user_id`, `access_token` |
| 常量 | UPPER_SNAKE | `MAX_RETRY_COUNT` |
| 私有属性 | `_leading_underscore` | `_internal_cache` |
| 类型别名 | PascalCase + Type 后缀 | `UserIdType` |

### 2.3 函数设计原则

```python
# ❌ 错误：函数过长、职责不清
def process_user(data):
    # 100+ 行代码，验证、转换、保存、发送通知...

# ✅ 正确：单一职责、清晰命名
def validate_user_input(data: UserInputSchema) -> UserInputModel:
    """验证用户输入数据"""
    pass

def create_user(data: UserInputModel) -> User:
    """创建用户（不包含业务逻辑）"""
    pass

def register_user(data: UserInputSchema) -> User:
    """注册用户完整流程"""
    validated = validate_user_input(data)
    user = create_user(validated)
    send_welcome_email(user)
    return user
```

### 2.4 类型注解（必须）

```python
# ❌ 禁止：无类型注解
def calculate_pnl(price, quantity):
    return price * quantity

# ✅ 必须：完整的类型注解
from decimal import Decimal
from typing import Optional

def calculate_pnl(price: Decimal, quantity: Decimal) -> Decimal:
    """计算盈亏金额"""
    if price <= 0:
        raise ValueError("价格必须为正数")
    if quantity <= 0:
        raise ValueError("数量必须为正数")
    return price * quantity

def get_user_by_id(user_id: int) -> Optional[User]:
    """根据ID获取用户"""
    pass
```

### 2.5 错误处理

```python
# ✅ 统一使用自定义异常
class AppException(Exception):
    """应用基础异常"""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(message)

class UserNotFoundError(AppException):
    """用户不存在"""
    def __init__(self, user_id: int):
        super().__init__(
            message=f"用户 {user_id} 不存在",
            code="USER_NOT_FOUND"
        )

class InsufficientBalanceError(AppException):
    """余额不足"""
    def __init__(self, required: Decimal, available: Decimal):
        super().__init__(
            message=f"余额不足：需要 {required}，可用 {available}",
            code="INSUFFICIENT_BALANCE"
        )
```

### 2.6 日志规范

```python
import logging
from structlog import get_logger

log = get_logger(__name__)

# ❌ 禁止：print 调试
print("user_id:", user_id)

# ✅ 使用结构化日志
log.info(
    "user_created",
    user_id=user_id,
    email=email,
    action="register"
)

log.warning(
    "risk_limit_exceeded",
    user_id=user_id,
    position_value=position_value,
    max_limit=max_limit
)

log.error(
    "order_failed",
    order_id=order_id,
    error=str(e),
    exchange="binance"
)
```

### 2.7 金融计算规范（关键）

```python
from decimal import Decimal, ROUND_DOWN

# ❌ 禁止：使用 float 进行金融计算
price = 0.1 * 100  # 精度丢失

# ✅ 必须：使用 Decimal
from decimal import getcontext
getcontext().prec = 28  # 设置足够精度

def calculate_order_value(
    price: Decimal,
    quantity: Decimal,
    fee_rate: Decimal = Decimal("0.001")
) -> dict[str, Decimal]:
    """计算订单金额和手续费"""
    gross_value = price * quantity
    fee = gross_value * fee_rate
    net_value = gross_value - fee

    return {
        "gross_value": gross_value.quantize(Decimal("0.01"), rounding=ROUND_DOWN),
        "fee": fee.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN),
        "net_value": net_value.quantize(Decimal("0.01"), rounding=ROUND_DOWN),
    }
```

### 2.8 FastAPI 最佳实践

```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/users", tags=["用户"])


class UserCreateRequest(BaseModel):
    """创建用户请求"""
    email: str = Field(..., format="email")
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=1, max_length=50)


class UserResponse(BaseModel):
    """用户响应（脱敏）"""
    id: int
    email: str
    name: str
    is_active: bool

    class Config:
        from_attributes = True


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreateRequest,
    user_service: UserService = Depends(get_user_service)
) -> UserResponse:
    """创建新用户"""
    try:
        user = await user_service.create(data)
        return UserResponse.model_validate(user)
    except EmailAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": e.code, "message": e.message}
        )
```

---

## 3. Dart/Flutter 前端规范

### 3.1 项目结构（Clean Architecture）

```
lib/
├── main.dart
├── app.dart                    # App widget
├── core/
│   ├── constants/              # 常量
│   │   ├── app_constants.dart
│   │   └── api_constants.dart
│   ├── errors/                 # 错误处理
│   │   ├── exceptions.dart
│   │   └── failures.dart
│   ├── network/                # 网络层
│   │   ├── api_client.dart
│   │   ├── api_endpoints.dart
│   │   └── interceptors.dart
│   ├── theme/                  # 主题
│   │   ├── app_theme.dart
│   │   ├── colors.dart
│   │   └── text_styles.dart
│   └── utils/                  # 工具
│       ├── extensions.dart
│       ├── formatters.dart
│       └── validators.dart
├── features/
│   ├── auth/
│   │   ├── data/
│   │   │   ├── datasources/
│   │   │   ├── models/
│   │   │   └── repositories/
│   │   ├── domain/
│   │   │   ├── entities/
│   │   │   ├── repositories/
│   │   │   └── usecases/
│   │   └── presentation/
│   │       ├── providers/
│   │       ├── screens/
│   │       └── widgets/
│   ├── dashboard/
│   │   └── ...
│   ├── strategies/
│   │   └── ...
│   └── settings/
│       └── ...
└── shared/
    ├── widgets/                # 通用组件
    │   ├── buttons/
    │   ├── cards/
    │   ├── charts/
    │   └── inputs/
    └── providers/              # 全局 providers
        ├── auth_provider.dart
        └── theme_provider.dart
```

### 3.2 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件名 | snake_case | `user_repository.dart` |
| 类名 | PascalCase | `UserRepository` |
| 私有属性 | `_camelCase` | `_userCache` |
| 常量 | kCamelCase | `kMaxRetryCount` |
| 枚举 | PascalCase + Enum 后缀 | `OrderStatusEnum` |
| Provider | PascalCase + Provider 后缀 | `AuthProvider` |
| Widget | PascalCase + Widget/Page 后缀 | `HomePage`, `UserCard` |

### 3.3 Riverpod 最佳实践

```dart
// ✅ 推荐的 Provider 结构
import 'package:flutter_riverpod/flutter_riverpod.dart';

// 1. 数据模型
class User {
  final int id;
  final String email;
  final String name;

  const User({
    required this.id,
    required this.email,
    required this.name,
  });

  User copyWith({
    int? id,
    String? email,
    String? name,
  }) {
    return User(
      id: id ?? this.id,
      email: email ?? this.email,
      name: name ?? this.name,
    );
  }
}

// 2. Repository 接口
abstract class UserRepository {
  Future<User> getCurrentUser();
  Future<User> updateProfile(User user);
}

// 3. Repository 实现
class UserRepositoryImpl implements UserRepository {
  final ApiClient _apiClient;

  UserRepositoryImpl(this._apiClient);

  @override
  Future<User> getCurrentUser() async {
    final response = await _apiClient.get('/api/v1/users/me');
    return UserModel.fromJson(response.data);
  }

  @override
  Future<User> updateProfile(User user) async {
    final response = await _apiClient.put(
      '/api/v1/users/me',
      data: {
        'name': user.name,
      },
    );
    return UserModel.fromJson(response.data);
  }
}

// 4. Provider 定义
final userRepositoryProvider = Provider<UserRepository>((ref) {
  return UserRepositoryImpl(ref.read(apiClientProvider));
});

final currentUserProvider = FutureProvider<User>((ref) async {
  return ref.watch(userRepositoryProvider).getCurrentUser();
});

// 5. Notifier 用于需要状态管理的场景
class StrategyNotifier extends StateNotifier<AsyncValue<Strategy>> {
  final StrategyRepository _repository;

  StrategyNotifier(this._repository) : super(const AsyncValue.loading());

  Future<void> loadStrategy(String id) async {
    state = const AsyncValue.loading();
    try {
      final strategy = await _repository.getStrategy(id);
      state = AsyncValue.data(strategy);
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  Future<void> updateParams(Map<String, dynamic> params) async {
    final current = state.value;
    if (current == null) return;

    state = AsyncValue.data(current.copyWith(params: params));
  }
}

final strategyProvider = StateNotifierProvider<StrategyNotifier, AsyncValue<Strategy>>((ref) {
  return StrategyNotifier(ref.watch(strategyRepositoryProvider));
});
```

### 3.4 Widget 规范

```dart
// ✅ Widget 应该简洁，复杂逻辑放到 Notifier/UseCase
class StrategyCard extends ConsumerWidget {
  const StrategyCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strategyAsync = ref.watch(strategyProvider);

    return strategyAsync.when(
      loading: () => const StrategyCardSkeleton(),
      error: (e, _) => StrategyErrorWidget(message: e.toString()),
      data: (strategy) => _buildContent(context, strategy),
    );
  }

  Widget _buildContent(BuildContext context, Strategy strategy) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(strategy.name, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            StrategyStatusBadge(status: strategy.status),
            // ...
          ],
        ),
      ),
    );
  }
}
```

### 3.5 API 客户端封装

```dart
class ApiClient {
  final Dio _dio;
  final Ref _ref;

  ApiClient(this._ref) : _dio = Dio() {
    _dio.options = BaseOptions(
      baseUrl: ApiConstants.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    );

    _dio.interceptors.addAll([
      AuthInterceptor(_ref),
      LogInterceptor(requestBody: true, responseBody: true),
    ]);
  }

  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) async {
    return _dio.get<T>(path, queryParameters: queryParameters);
  }

  Future<Response<T>> post<T>(
    String path, {
    dynamic data,
  }) async {
    return _dio.post<T>(path, data: data);
  }
}

class AuthInterceptor extends Interceptor {
  final Ref _ref;

  AuthInterceptor(this._ref);

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    // 从 provider 获取 token
    final token = _ref.read(authTokenProvider);
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }
}
```

---

## 4. Git 协作规范

### 4.1 分支命名

```
main                    # 主分支，永远可部署
├── develop             # 开发分支
│   ├── feature/       # 功能分支
│   │   └── feature/user-auth
│   │   └── feature/strategy-engine
│   ├── fix/           # 修复分支
│   │   └── fix/login-crash
│   └── release/       # 发布分支
│       └── release/v1.0.0
```

### 4.2 Commit Message 规范

使用 **Conventional Commits**：

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

**类型 (type)**：
| 类型 | 说明 |
|------|------|
| feat | 新功能 |
| fix | Bug 修复 |
| docs | 文档更新 |
| style | 代码格式（不影响功能） |
| refactor | 重构（不是修复也不是新功能） |
| test | 测试相关 |
| chore | 构建/工具相关 |

**示例**：
```bash
# ✅ 正确
feat(auth): add JWT refresh token support
fix(strategy): handle zero division in RSI calculation
docs(api): update order endpoint documentation
refactor(market): extract exchange adapter interface

# ❌ 错误
更新代码
fix bug
WIP
aaa
```

### 4.3 Pull Request 流程

```
1. 从 develop 创建 feature 分支
   git checkout develop
   git pull origin develop
   git checkout -b feature/user-auth

2. 开发 + Commit
   git add .
   git commit -m "feat(auth): implement login with email"

3. Push + 创建 PR
   git push -u origin feature/user-auth
   # 在 GitHub/GitLab 创建 PR

4. PR 必须包含
   - 描述：做了什么，为什么
   - 关联 Issue
   - 测试截图/记录
   - 任何需要 reviewer 注意的

5. 至少 1 人 Review 通过后才能合并
```

---

## 5. API 设计规范

### 5.1 RESTful 约定

| 方法 | 路径 | 说明 | 示例 |
|------|------|------|------|
| GET | /users | 获取用户列表 | `GET /api/v1/users` |
| GET | /users/{id} | 获取单个用户 | `GET /api/v1/users/123` |
| POST | /users | 创建用户 | `POST /api/v1/users` |
| PUT | /users/{id} | 更新用户 | `PUT /api/v1/users/123` |
| DELETE | /users/{id} | 删除用户 | `DELETE /api/v1/users/123` |

### 5.2 请求/响应格式

**请求格式**：
```json
POST /api/v1/strategies
{
  "name": "双均线策略",
  "symbol": "BTCUSDT",
  "exchange": "binance",
  "params": {
    "fast_period": 10,
    "slow_period": 30
  }
}
```

**成功响应**：
```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "双均线策略",
    "status": "draft",
    "created_at": "2026-04-21T10:00:00Z"
  }
}
```

**错误响应**：
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "参数验证失败",
    "details": [
      {
        "field": "params.fast_period",
        "message": "必须大于 0"
      }
    ]
  }
}
```

### 5.3 状态码

| 状态码 | 说明 | 使用场景 |
|--------|------|----------|
| 200 | OK | 成功获取/更新 |
| 201 | Created | 成功创建 |
| 204 | No Content | 成功删除 |
| 400 | Bad Request | 参数错误 |
| 401 | Unauthorized | 未认证 |
| 403 | Forbidden | 无权限 |
| 404 | Not Found | 资源不存在 |
| 409 | Conflict | 冲突（如重复） |
| 422 | Unprocessable | 业务逻辑拒绝 |
| 429 | Too Many Requests | 限流 |
| 500 | Internal Error | 服务器错误 |

---

## 6. 数据库规范

### 6.1 表命名

- 使用 snake_case：`user_accounts`, `strategy_instances`
- 单数形式：`user` 不是 `users`
- 时间戳字段：`created_at`, `updated_at`

### 6.2 索引规范

```sql
-- 必须有 created_at 索引（很多查询依赖）
CREATE INDEX ix_users_created_at ON users(created_at);

-- 外键必须加索引
CREATE INDEX ix_strategy_instances_user_id ON strategy_instances(user_id);

-- 频繁查询的字段
CREATE INDEX ix_orders_status ON orders(status);
CREATE INDEX ix_orders_created_at ON orders(created_at);

-- 复合索引（按查询频率排序）
CREATE INDEX ix_positions_user_symbol ON positions(user_id, symbol);
```

### 6.3 敏感数据

```sql
-- API Key 必须加密存储
ALTER TABLE exchange_api_keys ADD COLUMN encrypted_secret BYTEA;

-- 永远不要在日志中打印密码或密钥
-- 永远不要在响应中返回完整密钥（只返回 ***abc123）
```

---

## 7. 测试规范

### 7.1 测试覆盖率目标

| 模块 | 最低覆盖率 |
|------|-----------|
| 核心业务逻辑（services） | 80% |
| API 端点 | 70% |
| 量化策略计算 | 90% |
| 工具函数 | 90% |
| UI Widget | 50% |

### 7.2 测试命名

```python
# Python: 使用 pytest
class TestStrategyService:
    """策略服务测试"""

    def test_calculate_signal_returns_buy_when_fast_ma_crosses_above_slow_ma(self):
        """当快速均线从下穿越慢速均线时，应返回买入信号"""
        pass

    def test_calculate_signal_returns_sell_when_fast_ma_crosses_below_slow_ma(self):
        """当快速均线从上穿越慢速均线时，应返回卖出信号"""
        pass

    def test_calculate_signal_ignores_sideways_market(self):
        """横盘市场不应产生信号"""
        pass
```

```dart
// Dart: 使用 flutter_test
void main() {
  group('StrategyService', () {
    test('should return BUY signal when fast MA crosses above slow MA', () {
      // given
      final service = StrategyService();
      final prices = [100, 101, 102, 103, 104];

      // when
      final signal = service.calculateSignal(prices, fastPeriod: 2, slowPeriod: 3);

      // then
      expect(signal.action, SignalAction.buy);
      expect(signal.confidence, greaterThan(0.5));
    });
  });
}
```

### 7.3 Mock 规范

```python
# 使用 pytest-mock
def test_create_order_calls_exchange_api(mocker):
    # given
    mock_exchange = mocker.patch('app.services.order_service.ExchangeAdapter')
    mock_exchange.return_value.place_order.return_value = {"order_id": "123"}

    service = OrderService(exchange_adapter=mock_exchange)

    # when
    result = service.create_order(symbol="BTCUSDT", side="buy", quantity=0.01)

    # then
    assert result.order_id == "123"
    mock_exchange.return_value.place_order.assert_called_once_with(
        symbol="BTCUSDT",
        side="buy",
        quantity=Decimal("0.01")
    )
```

---

## 8. 安全规范

### 8.1 输入验证

```python
# 所有用户输入必须验证
class OrderCreateSchema(BaseModel):
    symbol: str = Field(..., min_length=6, max_length=12)
    quantity: Decimal = Field(..., gt=0, le=1000000)
    price: Optional[Decimal] = Field(None, gt=0)

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v):
        # 只允许字母和数字（大写）
        v = v.upper()
        if not re.match(r'^[A-Z0-9]+$', v):
            raise ValueError('无效的交易对格式')
        return v
```

### 8.2 SQL 注入防护

```python
# ❌ 危险：字符串拼接
query = f"SELECT * FROM users WHERE id = {user_id}"
cursor.execute(query)

# ✅ 安全：参数化查询
query = "SELECT * FROM users WHERE id = %s"
cursor.execute(query, (user_id,))
```

### 8.3 认证与授权

```python
# JWT 验证
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user_by_id(db, user_id=user_id)
    if user is None:
        raise credentials_exception
    return user
```

---

## 附录：Linter 配置

### Python (ruff)

```toml
# ruff.toml
line-length = 100
target-version = "py311"

[lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "C4", "PT"]
ignore = ["E501"]  # line-length

[lint.isort]
known-first-party = ["app"]
```

### Dart (analysis_options)

```yaml
# analysis_options.yaml
include: package:flutter_lints/flutter.yaml

linter:
  rules:
    - avoid_print
    - prefer_const_constructors
    - prefer_const_literals_to_create_immutables
    - prefer_final_fields
    - prefer_final_locals
    - unnecessary_this
    - avoid_redundant_argument_values
    - sort_pub_dependencies
```

---

*文档版本：v1.0.0 | 最后更新：2026-04-21*
