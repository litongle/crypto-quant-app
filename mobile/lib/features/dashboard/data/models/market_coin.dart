import 'package:equatable/equatable.dart';

/// 行情币种模型
class MarketCoin extends Equatable {
  final String symbol;
  final String name;
  final double price;
  final double change24h;
  final double changePercent;
  final double volume;
  final List<double>? miniChartData;

  const MarketCoin({
    required this.symbol,
    required this.name,
    required this.price,
    required this.change24h,
    required this.changePercent,
    required this.volume,
    this.miniChartData,
  });

  bool get isPositive => changePercent >= 0;

  @override
  List<Object?> get props => [symbol, price, change24h, changePercent, volume];

  factory MarketCoin.fromJson(Map<String, dynamic> json) {
    return MarketCoin(
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      price: (json['price'] as num).toDouble(),
      change24h: (json['change_24h'] as num).toDouble(),
      changePercent: (json['change_percent'] as num).toDouble(),
      volume: (json['volume'] as num).toDouble(),
      miniChartData: json['mini_chart'] != null
          ? (json['mini_chart'] as List).map((e) => (e as num).toDouble()).toList()
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'symbol': symbol,
      'name': name,
      'price': price,
      'change_24h': change24h,
      'change_percent': changePercent,
      'volume': volume,
      'mini_chart': miniChartData,
    };
  }
}

/// 持仓模型
class Position extends Equatable {
  final String symbol;
  final String name;
  final double quantity;
  final double entryPrice;
  final double currentPrice;
  final double pnl;
  final double pnlPercent;
  final String exchange;

  const Position({
    required this.symbol,
    required this.name,
    required this.quantity,
    required this.entryPrice,
    required this.currentPrice,
    required this.pnl,
    required this.pnlPercent,
    required this.exchange,
  });

  bool get isProfit => pnl >= 0;

  double get totalValue => quantity * currentPrice;

  @override
  List<Object> get props => [symbol, quantity, entryPrice, currentPrice, pnl];

  factory Position.fromJson(Map<String, dynamic> json) {
    return Position(
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      quantity: (json['quantity'] as num).toDouble(),
      entryPrice: (json['entry_price'] as num).toDouble(),
      currentPrice: (json['current_price'] as num).toDouble(),
      pnl: (json['pnl'] as num).toDouble(),
      pnlPercent: (json['pnl_percent'] as num).toDouble(),
      exchange: json['exchange'] as String,
    );
  }
}

/// Dashboard 数据模型
class DashboardData extends Equatable {
  final double totalAsset;
  final double todayProfit;
  final double totalProfitPercent;
  final double annualYield;
  final List<double> equityCurve;
  final String currentSignal;
  final double signalConfidence;
  final String strategyName;
  final int strategyDays;
  final List<MarketCoin> marketCoins;
  final List<Position> positions;

  const DashboardData({
    required this.totalAsset,
    required this.todayProfit,
    required this.totalProfitPercent,
    required this.annualYield,
    required this.equityCurve,
    required this.currentSignal,
    required this.signalConfidence,
    required this.strategyName,
    required this.strategyDays,
    required this.marketCoins,
    required this.positions,
  });

  @override
  List<Object> get props => [
    totalAsset,
    todayProfit,
    totalProfitPercent,
    annualYield,
    currentSignal,
    strategyName,
    marketCoins,
    positions,
  ];

  factory DashboardData.fromJson(Map<String, dynamic> json) {
    return DashboardData(
      totalAsset: (json['total_asset'] as num).toDouble(),
      todayProfit: (json['today_profit'] as num).toDouble(),
      totalProfitPercent: (json['total_profit_percent'] as num).toDouble(),
      annualYield: (json['annual_yield'] as num).toDouble(),
      equityCurve: (json['equity_curve'] as List)
          .map((e) => (e as num).toDouble())
          .toList(),
      currentSignal: json['current_signal'] as String,
      signalConfidence: (json['signal_confidence'] as num).toDouble(),
      strategyName: json['strategy_name'] as String,
      strategyDays: json['strategy_days'] as int,
      marketCoins: (json['market_coins'] as List)
          .map((e) => MarketCoin.fromJson(e as Map<String, dynamic>))
          .toList(),
      positions: (json['positions'] as List)
          .map((e) => Position.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  /// 占位数据（未登录或 API 不可用时使用）
  factory DashboardData.placeholder() {
    return DashboardData(
      totalAsset: 12847.32,
      todayProfit: 1084.20,
      totalProfitPercent: 8.42,
      annualYield: 142.6,
      equityCurve: _generatePlaceholderEquityCurve(),
      currentSignal: '看多 BTC',
      signalConfidence: 87,
      strategyName: '双均线策略',
      strategyDays: 42,
      marketCoins: _placeholderMarketCoins,
      positions: _placeholderPositions,
    );
  }

  static List<double> _generatePlaceholderEquityCurve() {
    final List<double> curve = [];
    double value = 10000;
    for (int i = 0; i < 30; i++) {
      value += (value * 0.02 * (0.5 - (i % 2).toDouble())) + (value * 0.01 * (i % 3 - 1).toDouble());
      curve.add(value);
    }
    return curve;
  }

  static final List<MarketCoin> _placeholderMarketCoins = [
    const MarketCoin(
      symbol: 'BTC',
      name: 'Bitcoin',
      price: 67543.21,
      change24h: 1234.56,
      changePercent: 1.86,
      volume: 28500000000,
    ),
    const MarketCoin(
      symbol: 'ETH',
      name: 'Ethereum',
      price: 3456.78,
      change24h: -45.32,
      changePercent: -1.29,
      volume: 15200000000,
    ),
    const MarketCoin(
      symbol: 'SOL',
      name: 'Solana',
      price: 178.90,
      change24h: 8.45,
      changePercent: 4.96,
      volume: 3200000000,
    ),
    const MarketCoin(
      symbol: 'BNB',
      name: 'BNB',
      price: 598.12,
      change24h: 12.34,
      changePercent: 2.11,
      volume: 1800000000,
    ),
    const MarketCoin(
      symbol: 'DOGE',
      name: 'Dogecoin',
      price: 0.1234,
      change24h: 0.0089,
      changePercent: 7.78,
      volume: 890000000,
    ),
  ];

  static final List<Position> _placeholderPositions = [
    const Position(
      symbol: 'BTC',
      name: 'Bitcoin',
      quantity: 0.15,
      entryPrice: 65000,
      currentPrice: 67543.21,
      pnl: 381.48,
      pnlPercent: 3.91,
      exchange: 'Binance',
    ),
    const Position(
      symbol: 'ETH',
      name: 'Ethereum',
      quantity: 2.5,
      entryPrice: 3500,
      currentPrice: 3456.78,
      pnl: -108.05,
      pnlPercent: -1.24,
      exchange: 'Binance',
    ),
  ];
}
