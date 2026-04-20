import 'package:equatable/equatable.dart';

/// 策略模板模型
class StrategyTemplate extends Equatable {
  final String id;
  final String name;
  final String description;
  final String category;      // 趋势/震荡/网格/马丁
  final String suitableMarket; // 适用行情
  final String icon;
  final List<String> supportedSymbols;
  final Map<String, dynamic> defaultParams;
  final Map<String, dynamic> paramSchema; // 参数说明

  const StrategyTemplate({
    required this.id,
    required this.name,
    required this.description,
    required this.category,
    required this.suitableMarket,
    required this.icon,
    required this.supportedSymbols,
    required this.defaultParams,
    required this.paramSchema,
  });

  @override
  List<Object?> get props => [
        id, name, description, category, suitableMarket, icon,
        supportedSymbols, defaultParams, paramSchema,
      ];

  /// 策略模板列表
  static List<StrategyTemplate> get templates => [
    const StrategyTemplate(
      id: 'ma_cross',
      name: '双均线策略',
      description: '使用快速和慢速均线的交叉来识别趋势方向',
      category: '趋势',
      suitableMarket: '趋势行情',
      icon: '📊',
      supportedSymbols: ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
      defaultParams: {
        'fast_period': 10,
        'slow_period': 30,
        'position_size': 0.1,
      },
      paramSchema: {
        'fast_period': {'label': '快线周期', 'min': 5, 'max': 50},
        'slow_period': {'label': '慢线周期', 'min': 20, 'max': 200},
        'position_size': {'label': '仓位比例', 'min': 0.01, 'max': 1.0},
      },
    ),
    const StrategyTemplate(
      id: 'rsi',
      name: 'RSI 策略',
      description: '基于相对强弱指数的超买超卖信号',
      category: '震荡',
      suitableMarket: '震荡行情',
      icon: '📉',
      supportedSymbols: ['BTC/USDT', 'ETH/USDT', 'BNB/USDT'],
      defaultParams: {
        'period': 14,
        'oversold': 30,
        'overbought': 70,
        'position_size': 0.1,
      },
      paramSchema: {
        'period': {'label': 'RSI 周期', 'min': 5, 'max': 30},
        'oversold': {'label': '超卖阈值', 'min': 10, 'max': 40},
        'overbought': {'label': '超买阈值', 'min': 60, 'max': 90},
        'position_size': {'label': '仓位比例', 'min': 0.01, 'max': 1.0},
      },
    ),
    const StrategyTemplate(
      id: 'bollinger',
      name: '布林带策略',
      description: '利用布林带通道识别价格波动区间',
      category: '波动',
      suitableMarket: '波动行情',
      icon: '🎯',
      supportedSymbols: ['BTC/USDT', 'ETH/USDT', 'DOGE/USDT'],
      defaultParams: {
        'period': 20,
        'std_dev': 2.0,
        'position_size': 0.1,
      },
      paramSchema: {
        'period': {'label': '周期', 'min': 10, 'max': 50},
        'std_dev': {'label': '标准差倍数', 'min': 1.5, 'max': 3.0},
        'position_size': {'label': '仓位比例', 'min': 0.01, 'max': 1.0},
      },
    ),
    const StrategyTemplate(
      id: 'grid',
      name: '网格策略',
      description: '在价格区间内设置等间距网格，低买高卖',
      category: '网格',
      suitableMarket: '横盘行情',
      icon: '🟦',
      supportedSymbols: ['BTC/USDT', 'ETH/USDT', 'BNB/USDT'],
      defaultParams: {
        'grid_count': 10,
        'price_range_pct': 10.0,
        'investment_per_grid': 100.0,
      },
      paramSchema: {
        'grid_count': {'label': '网格数量', 'min': 5, 'max': 50},
        'price_range_pct': {'label': '价格区间%', 'min': 5, 'max': 30},
        'investment_per_grid': {'label': '每格投资(USDT)', 'min': 10, 'max': 1000},
      },
    ),
    const StrategyTemplate(
      id: 'martingale',
      name: '马丁格尔',
      description: '亏损后加倍下单，盈利后回归初始仓位',
      category: '马丁',
      suitableMarket: '高波动行情',
      icon: '🎰',
      supportedSymbols: ['BTC/USDT', 'ETH/USDT'],
      defaultParams: {
        'initial_position': 0.01,
        'multiplier': 2.0,
        'max_position': 0.16,
        'profit_target_pct': 1.0,
      },
      paramSchema: {
        'initial_position': {'label': '初始仓位', 'min': 0.001, 'max': 0.1},
        'multiplier': {'label': '加倍系数', 'min': 1.5, 'max': 3.0},
        'max_position': {'label': '最大仓位', 'min': 0.05, 'max': 1.0},
        'profit_target_pct': {'label': '盈利目标%', 'min': 0.5, 'max': 5.0},
      },
    ),
  ];
}

/// 策略实例
class StrategyInstance extends Equatable {
  final String id;
  final String templateId;
  final String templateName;
  final String symbol;
  final String exchange;
  final String status;  // running/paused/stopped
  final Map<String, dynamic> params;
  final double totalPnL;
  final double winRate;
  final int totalTrades;
  final String createdAt;

  const StrategyInstance({
    required this.id,
    required this.templateId,
    required this.templateName,
    required this.symbol,
    required this.exchange,
    required this.status,
    required this.params,
    required this.totalPnL,
    required this.winRate,
    required this.totalTrades,
    required this.createdAt,
  });

  bool get isRunning => status == 'running';
  bool get isProfit => totalPnL >= 0;

  @override
  List<Object?> get props => [
        id, templateId, templateName, symbol, exchange,
        status, params, totalPnL, winRate, totalTrades, createdAt,
      ];

  /// 模拟数据
  static List<StrategyInstance> mockList() {
    return [
      StrategyInstance(
        id: '1',
        templateId: 'ma_cross',
        templateName: '双均线策略',
        symbol: 'BTC/USDT',
        exchange: 'Binance',
        status: 'running',
        params: {'fast_period': 10, 'slow_period': 30},
        totalPnL: 1250.50,
        winRate: 65.5,
        totalTrades: 48,
        createdAt: '2024-04-01',
      ),
      StrategyInstance(
        id: '2',
        templateId: 'rsi',
        templateName: 'RSI 策略',
        symbol: 'ETH/USDT',
        exchange: 'OKX',
        status: 'running',
        params: {'period': 14, 'oversold': 30, 'overbought': 70},
        totalPnL: -320.80,
        winRate: 52.3,
        totalTrades: 35,
        createdAt: '2024-04-10',
      ),
      StrategyInstance(
        id: '3',
        templateId: 'grid',
        templateName: '网格策略',
        symbol: 'BNB/USDT',
        exchange: 'Binance',
        status: 'paused',
        params: {'grid_count': 10, 'price_range_pct': 10},
        totalPnL: 580.25,
        winRate: 89.0,
        totalTrades: 156,
        createdAt: '2024-03-20',
      ),
    ];
  }
}
