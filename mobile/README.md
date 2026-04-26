# 币钱袋 — Flutter 移动端

数字货币量化交易 App 的移动端，基于 Flutter + Riverpod + GoRouter。

## 技术栈

| 技术 | 用途 |
|------|------|
| Flutter 3.16+ | 跨平台 UI 框架 |
| Dart | 编程语言 |
| Riverpod | 状态管理（类型安全、编译时检查） |
| GoRouter | 声明式路由 |
| http | API 客户端 |
| fl_chart | K线图 & 权益曲线 |

## 项目结构

```
mobile/lib/
├── core/
│   ├── constants/         # API 地址、常量定义
│   ├── network/           # API 客户端（http + token 管理）
│   ├── providers/         # 全局 Riverpod Provider
│   ├── router/            # GoRouter 路由定义
│   ├── services/          # API 服务层（auth/dashboard/market/strategy）
│   └── theme/             # app_theme.dart（统一 Indigo 主色 + 令牌类）
└── features/
    ├── auth/              # 登录/注册
    ├── dashboard/         # 仪表盘（资产/持仓/权益曲线）
    ├── strategies/        # 策略中心
    ├── backtest/          # 回测
    └── settings/          # 设置（含登录入口）
```

## 快速开始

```bash
# 安装依赖
flutter pub get

# 运行（无需后端，未登录时展示占位数据）
flutter run

# 构建
flutter build apk --release    # Android
flutter build ios --release    # iOS
```

## 功能状态

| 模块 | UI | API 对接 |
|------|----|---------|
| Dashboard | ✅ | ✅ 资产/行情/持仓/权益曲线 |
| 认证（登录/注册） | ✅ | ✅ |
| 策略中心 | ✅ | ❌ 待对接 |
| 回测 | ✅ | ❌ 待对接 |
| 设置 | ✅ | ❌ 待对接 |

## 设计要点

- **可选登录**：未登录可浏览，API 失败时自动展示占位数据
- **统一主题**：Indigo #6366F1 主色 + 6-8px 圆角，与网页控制台一致
- **占位数据**：`DashboardData.placeholder()` 用于离线/未登录状态
