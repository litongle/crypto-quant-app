import 'package:equatable/equatable.dart';

/// 市场行情数据模型
class MarketTicker extends Equatable {
  final String symbol;           // 交易对 BTC/USDT
  final String baseAsset;        // 基础资产 BTC
  final String quoteAsset;       // 报价资产 USDT
  final double price;            // 当前价格
  final double priceChange24h;   // 24h涨跌
  final double priceChangePercent24h; // 24h涨跌幅 (%)
  final double high24h;          // 24h最高
  final double low24h;          // 24h最低
  final double volume24h;       // 24h成交量
  final List<double> sparkline;  // 迷你趋势线数据

  const MarketTicker({
    required this.symbol,
    required this.baseAsset,
    required this.quoteAsset,
    required this.price,
    required this.priceChange24h,
    required this.priceChangePercent24h,
    required this.high24h,
    required this.low24h,
    required this.volume24h,
    required this.sparkline,
  });

  bool get isRising => priceChangePercent24h >= 0;

  /// 从 API 响应解析
  factory MarketTicker.fromJson(Map<String, dynamic> json) {
    final symbol = json['symbol'] as String;
    final parts = symbol.split('USDT');
    return MarketTicker(
      symbol: '${parts[0]}/USDT',
      baseAsset: parts.isNotEmpty ? parts[0] : symbol,
      quoteAsset: 'USDT',
      price: (json['price'] ?? 0).toDouble(),
      priceChange24h: (json['change24h'] ?? 0).toDouble(),
      priceChangePercent24h: (json['changePercent24h'] ?? 0).toDouble(),
      high24h: (json['high24h'] ?? 0).toDouble(),
      low24h: (json['low24h'] ?? 0).toDouble(),
      volume24h: (json['volume24h'] ?? 0).toDouble(),
      sparkline: (json['sparkline'] as List<dynamic>?)
              ?.map((e) => (e as num).toDouble())
              .toList() ??
          [],
    );
  }

  /// 获取显示用的价格精度
  int get pricePrecision {
    if (price >= 10000) return 2;
    if (price >= 100) return 2;
    if (price >= 1) return 4;
    return 6;
  }

  /// 获取显示用的涨跌幅精度
  int get percentPrecision => 2;

  @override
  List<Object?> get props => [
        symbol,
        baseAsset,
        quoteAsset,
        price,
        priceChange24h,
        priceChangePercent24h,
        high24h,
        low24h,
        volume24h,
        sparkline,
      ];

  /// 模拟数据列表
  static List<MarketTicker> mockList() {
    return [
      MarketTicker(
        symbol: 'BTC/USDT',
        baseAsset: 'BTC',
        quoteAsset: 'USDT',
        price: 67432.50,
        priceChange24h: 1245.80,
        priceChangePercent24h: 1.88,
        high24h: 68150.00,
        low24h: 65890.25,
        volume24h: 28450000000,
        sparkline: _generateSparkline(67432.50, 24),
      ),
      MarketTicker(
        symbol: 'ETH/USDT',
        baseAsset: 'ETH',
        quoteAsset: 'USDT',
        price: 3521.45,
        priceChange24h: -45.23,
        priceChangePercent24h: -1.27,
        high24h: 3580.00,
        low24h: 3490.15,
        volume24h: 15200000000,
        sparkline: _generateSparkline(3521.45, 24),
      ),
      MarketTicker(
        symbol: 'SOL/USDT',
        baseAsset: 'SOL',
        quoteAsset: 'USDT',
        price: 178.92,
        priceChange24h: 8.45,
        priceChangePercent24h: 4.96,
        high24h: 182.30,
        low24h: 168.50,
        volume24h: 3800000000,
        sparkline: _generateSparkline(178.92, 24),
      ),
      MarketTicker(
        symbol: 'BNB/USDT',
        baseAsset: 'BNB',
        quoteAsset: 'USDT',
        price: 598.30,
        priceChange24h: -12.70,
        priceChangePercent24h: -2.08,
        high24h: 612.00,
        low24h: 595.50,
        volume24h: 890000000,
        sparkline: _generateSparkline(598.30, 24),
      ),
      MarketTicker(
        symbol: 'DOGE/USDT',
        baseAsset: 'DOGE',
        quoteAsset: 'USDT',
        price: 0.1582,
        priceChange24h: 0.0123,
        priceChangePercent24h: 8.43,
        high24h: 0.1620,
        low24h: 0.1450,
        volume24h: 1250000000,
        sparkline: _generateSparkline(0.1582, 24),
      ),
    ];
  }

  /// 生成模拟趋势线
  static List<double> _generateSparkline(double basePrice, int points) {
    final List<double> result = [];
    double price = basePrice * 0.98;
    for (int i = 0; i < points; i++) {
      price = price + (basePrice * 0.002) * (i % 2 == 0 ? 1 : -1);
      if (price < basePrice * 0.95) price = basePrice * 0.95;
      if (price > basePrice * 1.02) price = basePrice * 1.02;
      result.add(price);
    }
    result.add(basePrice);
    return result;
  }
}
