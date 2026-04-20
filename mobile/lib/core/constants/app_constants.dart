class ApiConstants {
  /// 开发环境：改为本地后端地址
  /// 生产环境：改为实际服务器地址
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://api.biqiandai.com', // TODO: 部署后修改为实际服务器地址
  );

  static const String wsUrl = String.fromEnvironment(
    'WS_URL',
    defaultValue: 'ws://localhost:8000', // TODO: 改为你的 WebSocket 地址
  );

  // API 版本前缀
  static const String apiVersion = '/api/v1';

  // ============ 端点路径（与后端 api/v1/__init__.py 对齐）============

  /// 认证: /api/v1/auth
  ///   POST /register  - 注册
  ///   POST /login     - 登录 (OAuth2PasswordRequestForm)
  ///   POST /refresh   - 刷新 Token
  ///   GET  /me        - 获取当前用户
  static const String auth = '$apiVersion/auth';

  /// 用户: /api/v1/users
  static const String users = '$apiVersion/users';

  /// 策略: /api/v1/strategies
  ///   GET  /templates            - 策略模板列表
  ///   GET  /instances            - 策略实例列表
  ///   POST /instances            - 创建策略
  ///   GET  /instances/{id}       - 策略详情
  ///   PUT  /instances/{id}       - 更新策略
  ///   POST /instances/{id}/start - 启动策略
  ///   POST /instances/{id}/stop  - 停止策略
  ///   DELETE /instances/{id}     - 删除策略
  static const String strategies = '$apiVersion/strategies';

  /// 回测: /api/v1/backtest
  static const String backtest = '$apiVersion/backtest';

  /// 行情: /api/v1/market
  ///   GET /ticker/{symbol}       - 单个交易对行情
  ///   GET /kline/{symbol}        - K线数据
  ///   GET /orderbook/{symbol}    - 订单簿
  ///   GET /symbols               - 支持的交易对列表
  ///   GET /tickers               - 批量行情（首页用）
  static const String market = '$apiVersion/market';

  /// 资产: /api/v1/asset
  ///   GET /summary       - 资产汇总
  ///   GET /positions     - 持仓列表
  ///   GET /equity-curve - 权益曲线
  static const String asset = '$apiVersion/asset';

  /// 交易: /api/v1/trading
  ///   GET  /accounts            - 交易所账户
  ///   POST /                    - 创建订单
  ///   GET  /                    - 订单历史
  ///   POST /{id}/cancel         - 取消订单
  ///   GET  /positions           - 交易持仓
  ///   POST /{id}/stop-loss      - 设置止损
  ///   POST /{id}/take-profit    - 设置止盈
  ///   POST /{id}/close          - 平仓
  ///   POST /emergency-close-all - 紧急平仓
  static const String trading = '$apiVersion/trading';

  /// 风险控制: /api/v1/risk
  static const String risk = '$apiVersion/risk';

  // 超时配置
  static const Duration connectTimeout = Duration(seconds: 10);
  static const Duration receiveTimeout = Duration(seconds: 30);
  static const Duration sendTimeout = Duration(seconds: 30);
}

class AppConstants {
  // App Info
  static const String appName = '币钱袋';
  static const String appVersion = '1.0.0';

  // 交易所
  static const List<String> supportedExchanges = ['binance', 'okx', 'huobi'];

  // 交易对
  static const List<String> defaultSymbols = [
    'BTCUSDT',
    'ETHUSDT',
    'SOLUSDT',
    'BNBUSDT',
    'DOGEUSDT',
  ];

  // 时间周期
  static const List<String> chartIntervals = ['1m', '5m', '15m', '1h', '4h', '1d'];

  // 缓存时间
  static const Duration cacheValidDuration = Duration(minutes: 5);
  static const Duration tokenRefreshBuffer = Duration(minutes: 5);
}
