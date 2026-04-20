import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../../../../core/constants/app_constants.dart';
import '../../../../core/network/api_client.dart';
import '../data/models/models.dart';

/// API 客户端 Provider
final _apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(const FlutterSecureStorage());
});

/// 资产数据 Provider（真实 API）
final assetProvider = FutureProvider<Asset>((ref) async {
  final apiClient = ref.watch(_apiClientProvider);
  try {
    final response = await apiClient.get('${ApiConstants.asset}/summary');
    final data = response.data['data'];
    return Asset.fromJson(data);
  } catch (e) {
    // API 失败时返回模拟数据
    return Asset.mock();
  }
});

/// 行情列表 Provider（真实 API）
final marketTickersProvider = FutureProvider<List<MarketTicker>>((ref) async {
  final apiClient = ref.watch(_apiClientProvider);
  try {
    final response = await apiClient.get(
      '${ApiConstants.market}/tickers',
      queryParameters: {'symbols': 'BTC,ETH,SOL,BNB,DOGE'},
    );
    final List<dynamic> data = response.data['data'] ?? [];
    return data.map((e) => MarketTicker.fromJson(e)).toList();
  } catch (e) {
    // API 失败时返回模拟数据
    return MarketTicker.mockList();
  }
});

/// 持仓列表 Provider（真实 API）
final positionsProvider = FutureProvider<List<Position>>((ref) async {
  final apiClient = ref.watch(_apiClientProvider);
  try {
    final response = await apiClient.get('${ApiConstants.asset}/positions');
    final List<dynamic> data = response.data['data'] ?? [];
    return data.map((e) => Position.fromJson(e)).toList();
  } catch (e) {
    // API 失败时返回模拟数据
    return Position.mockList();
  }
});

/// 权益曲线 Provider（真实 API）
final equityCurveProvider = FutureProvider<EquityCurve>((ref) async {
  final apiClient = ref.watch(_apiClientProvider);
  try {
    final response = await apiClient.get(
      '${ApiConstants.asset}/equity-curve',
      queryParameters: {'days': 30},
    );
    final data = response.data['data'];
    return EquityCurve.fromJson(data);
  } catch (e) {
    // API 失败时返回模拟数据
    return EquityCurve.mock();
  }
});

/// 刷新所有数据
final refreshDashboardProvider = FutureProvider((ref) async {
  ref.invalidate(assetProvider);
  ref.invalidate(marketTickersProvider);
  ref.invalidate(positionsProvider);
  ref.invalidate(equityCurveProvider);

  final results = await Future.wait([
    ref.read(assetProvider.future),
    ref.read(marketTickersProvider.future),
    ref.read(positionsProvider.future),
    ref.read(equityCurveProvider.future),
  ]);

  return {
    'asset': results[0],
    'tickers': results[1],
    'positions': results[2],
    'equity': results[3],
  };
});
