import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/services/asset_service.dart';
import '../../../../core/services/market_service.dart';
import '../../data/models/market_coin.dart';

/// Dashboard 综合数据
class DashboardData {
  final double totalAsset;
  final double totalPnl;
  final double totalPnlPercent;
  final List<MarketCoin> marketCoins;
  final List<Position> positions;
  final List<EquityPoint> equityCurve;

  const DashboardData({
    required this.totalAsset,
    required this.totalPnl,
    required this.totalPnlPercent,
    required this.marketCoins,
    required this.positions,
    required this.equityCurve,
  });
}

/// Dashboard 综合数据 Provider（聚合多个 API）
final dashboardProvider = FutureProvider<DashboardData>((ref) async {
  // 并行请求所有数据
  final results = await Future.wait([
    ref.watch(assetSummaryProvider.future),
    ref.watch(marketTickersProvider.future),
    ref.watch(positionsProvider.future),
    ref.watch(equityCurveProvider(30).future),
  ]);

  final summary = results[0] as AssetSummary;
  final tickers = results[1] as List<MarketTicker>;
  final positions = results[2] as List<Position>;
  final equityCurve = results[3] as EquityCurve;

  // 转换行情数据
  final marketCoins = tickers.map((t) => MarketCoin.fromTicker(t)).toList();

  return DashboardData(
    totalAsset: summary.totalAssets,
    totalPnl: summary.totalPnl,
    totalPnlPercent: summary.totalPnlPercent,
    marketCoins: marketCoins,
    positions: positions,
    equityCurve: equityCurve.points,
  );
});

/// 市场行情 Provider（直接来自后端）
final marketCoinsProvider = FutureProvider<List<MarketCoin>>((ref) async {
  final tickers = await ref.watch(marketTickersProvider.future);
  return tickers.map((t) => MarketCoin.fromTicker(t)).toList();
});

/// 持仓列表 Provider（直接来自后端）
final positionsProvider = FutureProvider<List<Position>>((ref) async {
  // 优先用 asset 服务的持仓，如果为空再尝试 trading 服务
  try {
    return await ref.watch(assetServiceProvider).getPositions();
  } catch (_) {
    return [];
  }
});

/// 总资产 Provider
final totalAssetProvider = FutureProvider<double>((ref) async {
  final summary = await ref.watch(assetSummaryProvider.future);
  return summary.totalAssets;
});

/// 刷新 Dashboard 数据
void refreshDashboard(WidgetRef ref) {
  ref.invalidate(dashboardProvider);
  ref.invalidate(marketCoinsProvider);
  ref.invalidate(positionsProvider);
  ref.invalidate(totalAssetProvider);
  ref.invalidate(assetSummaryProvider);
  ref.invalidate(marketTickersProvider);
  ref.invalidate(equityCurveProvider);
}
