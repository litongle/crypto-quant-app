import 'package:equatable/equatable.dart';

/// 持仓数据模型
class Position extends Equatable {
  final String id;
  final String symbol;           // 交易对
  final String side;            // 持仓方向 long/short
  final double quantity;         // 持仓数量
  final double entryPrice;       // 开仓价格
  final double currentPrice;     // 当前价格
  final double unrealizedPnL;    // 未实现盈亏
  final double unrealizedPnLPercent; // 未实现收益率 (%)
  final double leverage;        // 杠杆倍数
  final String exchange;        // 交易所

  const Position({
    required this.id,
    required this.symbol,
    required this.side,
    required this.quantity,
    required this.entryPrice,
    required this.currentPrice,
    required this.unrealizedPnL,
    required this.unrealizedPnLPercent,
    required this.leverage,
    required this.exchange,
  });

  bool get isProfit => unrealizedPnL >= 0;
  bool get isLong => side == 'long';

  /// 从 API 响应解析
  factory Position.fromJson(Map<String, dynamic> json) {
    final symbol = json['symbol'] as String? ?? '';
    final displaySymbol = symbol.contains('/') ? symbol : '${symbol.substring(0, symbol.length - 4)}/${symbol.substring(symbol.length - 4)}';
    return Position(
      id: json['id']?.toString() ?? '',
      symbol: displaySymbol,
      side: json['side'] ?? 'long',
      quantity: (json['quantity'] ?? 0).toDouble(),
      entryPrice: (json['entry_price'] ?? 0).toDouble(),
      currentPrice: (json['current_price'] ?? 0).toDouble(),
      unrealizedPnL: (json['unrealized_pnl'] ?? 0).toDouble(),
      unrealizedPnLPercent: (json['unrealized_pnl_percent'] ?? 0).toDouble(),
      leverage: (json['leverage'] ?? 1).toDouble(),
      exchange: json['exchange'] ?? 'binance',
    );
  }

  /// 格式化数量显示
  String get formattedQuantity {
    if (quantity >= 1) {
      return quantity.toStringAsFixed(4);
    }
    return quantity.toStringAsFixed(6);
  }

  @override
  List<Object?> get props => [
        id,
        symbol,
        side,
        quantity,
        entryPrice,
        currentPrice,
        unrealizedPnL,
        unrealizedPnLPercent,
        leverage,
        exchange,
      ];

  /// 模拟数据列表
  static List<Position> mockList() {
    return [
      const Position(
        id: '1',
        symbol: 'BTC/USDT',
        side: 'long',
        quantity: 0.15,
        entryPrice: 65000.00,
        currentPrice: 67432.50,
        unrealizedPnL: 364.88,
        unrealizedPnLPercent: 3.74,
        leverage: 5,
        exchange: 'Binance',
      ),
      const Position(
        id: '2',
        symbol: 'ETH/USDT',
        side: 'long',
        quantity: 2.5,
        entryPrice: 3400.00,
        currentPrice: 3521.45,
        unrealizedPnL: 303.63,
        unrealizedPnLPercent: 3.57,
        leverage: 3,
        exchange: 'OKX',
      ),
      const Position(
        id: '3',
        symbol: 'SOL/USDT',
        side: 'short',
        quantity: 50,
        entryPrice: 185.00,
        currentPrice: 178.92,
        unrealizedPnL: 304.00,
        unrealizedPnLPercent: 3.29,
        leverage: 2,
        exchange: 'Binance',
      ),
    ];
  }
}
