import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../constants/app_constants.dart';
import '../network/api_client.dart';

/// ============ 数据模型 ============

/// 资产汇总
class AssetSummary {
  final double totalAssets; // 总资产(USDT)
  final double availableBalance; // 可用余额
  final double frozenBalance; // 冻结余额
  final double totalPnl; // 累计盈亏
  final double totalPnlPercent; // 累计盈亏百分比
  final List<dynamic>? byExchange;

  const AssetSummary({
    required this.totalAssets,
    required this.availableBalance,
    required this.frozenBalance,
    required this.totalPnl,
    required this.totalPnlPercent,
    this.byExchange,
  });

  factory AssetSummary.fromJson(Map<String, dynamic> json) {
    return AssetSummary(
      totalAssets: (json['totalAssets'] as num?)?.toDouble() ?? 0,
      availableBalance: (json['availableBalance'] as num?)?.toDouble() ?? 0,
      frozenBalance: (json['frozenBalance'] as num?)?.toDouble() ?? 0,
      totalPnl: (json['totalPnl'] as num?)?.toDouble() ?? 0,
      totalPnlPercent: (json['totalPnlPercent'] as num?)?.toDouble() ?? 0,
      byExchange: json['byExchange'] as List<dynamic>? ?? [],
    );
  }
}

/// 持仓信息
class Position {
  final String symbol;
  final String side; // long / short
  final double quantity;
  final double entryPrice;
  final double currentPrice;
  final double unrealizedPnl;
  final double unrealizedPnlPercent;
  final int leverage;
  final double? stopLossPrice;
  final double? takeProfitPrice;

  const Position({
    required this.symbol,
    required this.side,
    required this.quantity,
    required this.entryPrice,
    required this.currentPrice,
    required this.unrealizedPnl,
    required this.unrealizedPnlPercent,
    required this.leverage,
    this.stopLossPrice,
    this.takeProfitPrice,
  });

  factory Position.fromJson(Map<String, dynamic> json) {
    return Position(
      symbol: json['symbol'] as String,
      side: json['side'] as String? ?? 'long',
      quantity: (json['quantity'] as num?)?.toDouble() ?? 0,
      entryPrice: (json['entryPrice'] as num?)?.toDouble() ?? 0,
      currentPrice: (json['currentPrice'] as num?)?.toDouble() ?? 0,
      unrealizedPnl: (json['unrealizedPnl'] as num?)?.toDouble() ?? 0,
      unrealizedPnlPercent: (json['unrealizedPnlPercent'] as num?)?.toDouble() ?? 0,
      leverage: json['leverage'] as int? ?? 1,
      stopLossPrice: (json['stopLossPrice'] as num?)?.toDouble(),
      takeProfitPrice: (json['takeProfitPrice'] as num?)?.toDouble(),
    );
  }
}

/// 权益曲线数据点
class EquityPoint {
  final DateTime date;
  final double equity;
  final double pnl;

  const EquityPoint({required this.date, required this.equity, required this.pnl});

  factory EquityPoint.fromJson(Map<String, dynamic> json) {
    return EquityPoint(
      date: DateTime.parse(json['date'] as String),
      equity: (json['equity'] as num).toDouble(),
      pnl: (json['pnl'] as num?)?.toDouble() ?? 0,
    );
  }
}

/// 权益曲线完整数据
class EquityCurve {
  final List<EquityPoint> points;
  final double totalReturn;
  final double maxDrawdown;
  final double sharpeRatio;

  const EquityCurve({
    required this.points,
    required this.totalReturn,
    required this.maxDrawdown,
    required this.sharpeRatio,
  });

  factory EquityCurve.fromJson(Map<String, dynamic> json) {
    final pointsData = json['points'] ?? json['data'] ?? [];
    return EquityCurve(
      points: (pointsData as List).map((e) => EquityPoint.fromJson(e as Map<String, dynamic>)).toList(),
      totalReturn: (json['totalReturn'] as num?)?.toDouble() ?? 0,
      maxDrawdown: (json['maxDrawdown'] as num?)?.toDouble() ?? 0,
      sharpeRatio: (json['sharpeRatio'] as num?)?.toDouble() ?? 0,
    );
  }
}

/// ============ Service ============

class AssetService {
  final ApiClient _apiClient;

  AssetService(this._apiClient);

  /// 获取资产汇总
  Future<AssetSummary> getSummary({String exchange = 'all'}) async {
    final response = await _apiClient.get(
      '${ApiConstants.asset}/summary',
      queryParameters: {'exchange': exchange},
    );
    final data = response.data;
    final summaryData = data is Map ? (data['data'] ?? data) : data;
    return AssetSummary.fromJson(summaryData as Map<String, dynamic>);
  }

  /// 获取持仓列表
  Future<List<Position>> getPositions({
    String exchange = 'all',
    String side = 'all',
  }) async {
    final response = await _apiClient.get(
      '${ApiConstants.asset}/positions',
      queryParameters: {'exchange': exchange, 'side': side},
    );
    final data = response.data;
    final positionsData = data is Map ? (data['data'] ?? data) : data;
    if (positionsData is List) {
      return positionsData.map((e) => Position.fromJson(e as Map<String, dynamic>)).toList();
    }
    return [];
  }

  /// 获取权益曲线
  Future<EquityCurve> getEquityCurve({int days = 30, String exchange = 'all'}) async {
    final response = await _apiClient.get(
      '${ApiConstants.asset}/equity-curve',
      queryParameters: {'days': days, 'exchange': exchange},
    );
    final data = response.data;
    final curveData = data is Map ? (data['data'] ?? data) : data;
    return EquityCurve.fromJson(curveData as Map<String, dynamic>);
  }
}

/// ============ Providers ============

final assetServiceProvider = Provider<AssetService>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return AssetService(apiClient);
});

/// 资产汇总
final assetSummaryProvider = FutureProvider<AssetSummary>((ref) async {
  final service = ref.watch(assetServiceProvider);
  return service.getSummary();
});

/// 持仓列表
final positionsProvider = FutureProvider<List<Position>>((ref) async {
  final service = ref.watch(assetServiceProvider);
  return service.getPositions();
});

/// 权益曲线
final equityCurveProvider = FutureProvider.family<EquityCurve, int>(
  (ref, days) async {
    final service = ref.watch(assetServiceProvider);
    return service.getEquityCurve(days: days);
  },
);
