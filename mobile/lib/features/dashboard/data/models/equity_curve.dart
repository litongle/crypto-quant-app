import 'package:equatable/equatable.dart';

/// 权益曲线数据点（日收益）
class EquityPoint extends Equatable {
  final String date;      // 日期 2024-04-01
  final double equity;    // 当日权益
  final double dailyPnL;  // 当日收益
  final double dailyReturn; // 当日收益率 (%)

  const EquityPoint({
    required this.date,
    required this.equity,
    required this.dailyPnL,
    required this.dailyReturn,
  });

  bool get isProfit => dailyPnL >= 0;

  @override
  List<Object?> get props => [date, equity, dailyPnL, dailyReturn];
}

/// 权益曲线数据模型
class EquityCurve extends Equatable {
  final List<EquityPoint> points;
  final double totalReturn;      // 总收益率
  final double maxDrawdown;      // 最大回撤
  final double sharpeRatio;      // 夏普比率
  final double winRate;          // 胜率

  const EquityCurve({
    required this.points,
    required this.totalReturn,
    required this.maxDrawdown,
    required this.sharpeRatio,
    required this.winRate,
  });

  /// 获取趋势线数据（归一化到0-100）
  List<double> get normalizedPoints {
    if (points.isEmpty) return [];
    final firstEquity = points.first.equity;
    return points.map((p) => (p.equity / firstEquity - 1) * 100).toList();
  }

  /// 从 API 响应解析
  factory EquityCurve.fromJson(Map<String, dynamic> json) {
    final pointsData = json['points'] as List<dynamic>? ?? [];
    final points = pointsData.map((p) => EquityPoint.fromJson(p)).toList();
    
    return EquityCurve(
      points: points,
      totalReturn: (json['total_return'] ?? 0).toDouble(),
      maxDrawdown: (json['max_drawdown'] ?? 0).toDouble(),
      sharpeRatio: (json['sharpe_ratio'] ?? 0).toDouble(),
      winRate: (json['win_rate'] ?? 0).toDouble(),
    );
  }

  /// 从 API 点数据解析
  static EquityPoint pointFromJson(Map<String, dynamic> json) {
    return EquityPoint(
      date: json['date'] ?? '',
      equity: (json['equity'] ?? 0).toDouble(),
      dailyPnL: (json['daily_pnl'] ?? 0).toDouble(),
      dailyReturn: (json['daily_return'] ?? 0).toDouble(),
    );
  }

  /// 模拟数据
  static EquityCurve mock() {
    final now = DateTime.now();
    final points = <EquityPoint>[];
    double equity = 100000;

    for (int i = 30; i >= 0; i--) {
      final date = now.subtract(Duration(days: i));
      final dailyReturn = (i % 3 == 0) ? 0.5 + i * 0.1 : -(0.3 + i * 0.05);
      final pnl = equity * dailyReturn / 100;
      equity = equity + pnl;

      points.add(EquityPoint(
        date: '${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}',
        equity: equity,
        dailyPnL: pnl,
        dailyReturn: dailyReturn,
      ));
    }

    return EquityCurve(
      points: points,
      totalReturn: 25.84,
      maxDrawdown: 3.21,
      sharpeRatio: 2.15,
      winRate: 68.5,
    );
  }

  @override
  List<Object?> get props => [points, totalReturn, maxDrawdown, sharpeRatio, winRate];
}
