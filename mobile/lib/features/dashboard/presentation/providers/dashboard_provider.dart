import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/providers/auth_provider.dart';
import '../../../../core/services/asset_service.dart' as asset_service;
import '../../../../core/services/market_service.dart' as market_service;
import '../../data/models/market_coin.dart';

/// 是否已登录
final isLoggedInProvider = Provider<bool>((ref) {
  return ref.watch(authProvider).status == AuthStatus.authenticated;
});

/// Dashboard 综合数据 Provider
final dashboardProvider = FutureProvider<DashboardData>((ref) async {
  // 未登录时直接返回占位数据
  if (!ref.read(isLoggedInProvider)) {
    return DashboardData.placeholder();
  }

  try {
    // 并行请求所有数据
    final results = await Future.wait([
      ref.watch(asset_service.assetSummaryProvider.future),
      ref.watch(market_service.marketTickersProvider.future),
      ref.watch(assetPositionsProvider.future),
      ref.watch(asset_service.equityCurveProvider(30).future),
    ]);

    final summary = results[0] as asset_service.AssetSummary;
    final tickers = results[1] as List<market_service.MarketTicker>;
    final positions = results[2] as List<asset_service.Position>;
    final equityCurve = results[3] as asset_service.EquityCurve;

    // 转换行情数据
    final marketCoins = tickers.map((t) => MarketCoin(
      symbol: t.symbol,
      name: t.symbol,
      price: t.price,
      change24h: t.change24h,
      changePercent: t.changePercent24h,
      volume: t.volume24h,
      miniChartData: t.sparkline,
    )).toList();

    // 转换持仓数据
    final viewPositions = positions.map((p) => Position(
      symbol: p.symbol,
      name: p.symbol,
      quantity: p.quantity,
      entryPrice: p.entryPrice,
      currentPrice: p.currentPrice,
      pnl: p.unrealizedPnl,
      pnlPercent: p.unrealizedPnlPercent,
      exchange: p.side,
    )).toList();

    // 转换权益曲线
    final equityData = equityCurve.points.map((e) => e.equity).toList();

    return DashboardData(
      totalAsset: summary.totalAssets,
      todayProfit: summary.totalPnl,
      totalProfitPercent: summary.totalPnlPercent,
      annualYield: 0,
      equityCurve: equityData,
      currentSignal: '暂无信号',
      signalConfidence: 0,
      strategyName: '未配置',
      strategyDays: 0,
      marketCoins: marketCoins,
      positions: viewPositions,
    );
  } catch (e) {
    // API 失败时降级到占位数据
    return DashboardData.placeholder();
  }
});

/// 市场行情 Provider
final marketCoinsProvider = FutureProvider<List<MarketCoin>>((ref) async {
  if (!ref.read(isLoggedInProvider)) {
    return DashboardData.placeholder().marketCoins;
  }
  try {
    final tickers = await ref.watch(market_service.marketTickersProvider.future);
    return tickers.map((t) => MarketCoin(
      symbol: t.symbol,
      name: t.symbol,
      price: t.price,
      change24h: t.change24h,
      changePercent: t.changePercent24h,
      volume: t.volume24h,
      miniChartData: t.sparkline,
    )).toList();
  } catch (_) {
    return DashboardData.placeholder().marketCoins;
  }
});

/// 持仓列表 Provider
final assetPositionsProvider = FutureProvider<List<asset_service.Position>>((ref) async {
  try {
    return await ref.watch(asset_service.assetServiceProvider).getPositions();
  } catch (_) {
    return [];
  }
});

/// 总资产 Provider
final totalAssetProvider = FutureProvider<double>((ref) async {
  if (!ref.read(isLoggedInProvider)) {
    return DashboardData.placeholder().totalAsset;
  }
  try {
    final summary = await ref.watch(asset_service.assetSummaryProvider.future);
    return summary.totalAssets;
  } catch (_) {
    return DashboardData.placeholder().totalAsset;
  }
});

/// 刷新 Dashboard 数据
void refreshDashboard(WidgetRef ref) {
  ref.invalidate(dashboardProvider);
  ref.invalidate(marketCoinsProvider);
  ref.invalidate(assetPositionsProvider);
  ref.invalidate(totalAssetProvider);
  ref.invalidate(asset_service.assetSummaryProvider);
  ref.invalidate(market_service.marketTickersProvider);
  ref.invalidate(asset_service.equityCurveProvider);
}
