import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../constants/app_constants.dart';
import '../network/api_client.dart';

/// ============ 数据模型 ============

/// 单个交易对行情
class MarketTicker {
  final String symbol;
  final double price;
  final double change24h;
  final double changePercent24h;
  final double volume24h;
  final double high24h;
  final double low24h;
  final List<double>? sparkline;

  const MarketTicker({
    required this.symbol,
    required this.price,
    required this.change24h,
    required this.changePercent24h,
    required this.volume24h,
    required this.high24h,
    required this.low24h,
    this.sparkline,
  });

  factory MarketTicker.fromJson(Map<String, dynamic> json) {
    return MarketTicker(
      symbol: json['symbol'] as String,
      price: (json['price'] as num).toDouble(),
      change24h: (json['change24h'] as num?)?.toDouble() ?? 0,
      changePercent24h: (json['changePercent24h'] as num?)?.toDouble() ?? 0,
      volume24h: (json['volume24h'] as num?)?.toDouble() ?? 0,
      high24h: (json['high24h'] as num?)?.toDouble() ?? 0,
      low24h: (json['low24h'] as num?)?.toDouble() ?? 0,
      sparkline: (json['sparkline'] as List<dynamic>?)
          ?.map((e) => (e as num).toDouble())
          .toList(),
    );
  }
}

/// K线数据
class Kline {
  final DateTime openTime;
  final double open;
  final double high;
  final double low;
  final double close;
  final double volume;
  final bool isBullish;

  const Kline({
    required this.openTime,
    required this.open,
    required this.high,
    required this.low,
    required this.close,
    required this.volume,
    required this.isBullish,
  });

  factory Kline.fromList(List<dynamic> arr) {
    final close = (arr[4] as num).toDouble();
    final open = (arr[1] as num).toDouble();
    return Kline(
      openTime: DateTime.fromMillisecondsSinceEpoch(arr[0] as int),
      open: open,
      high: (arr[2] as num).toDouble(),
      low: (arr[3] as num).toDouble(),
      close: close,
      volume: (arr[5] as num).toDouble(),
      isBullish: close >= open,
    );
  }
}

/// 交易对信息
class Symbol {
  final String symbol;
  final String baseAsset;
  final String quoteAsset;

  const Symbol({required this.symbol, required this.baseAsset, required this.quoteAsset});

  factory Symbol.fromJson(Map<String, dynamic> json) {
    return Symbol(
      symbol: json['symbol'] as String,
      baseAsset: json['baseAsset'] as String? ?? json['symbol'].toString().replaceAll('USDT', ''),
      quoteAsset: json['quoteAsset'] as String? ?? 'USDT',
    );
  }
}

/// ============ Service ============

/// 市场数据 Service
class MarketService {
  final ApiClient _apiClient;

  MarketService(this._apiClient);

  /// 批量获取行情（首页用）
  Future<List<MarketTicker>> getTickers({
    List<String>? symbols,
  }) async {
    final params = {
      'symbols': (symbols ?? ['BTC', 'ETH', 'SOL', 'BNB', 'DOGE']).join(','),
    };
    final response = await _apiClient.get(
      '${ApiConstants.market}/tickers',
      queryParameters: params,
    );
    final data = response.data;
    final list = data is Map ? (data['data'] ?? data) : data;
    if (list is List) {
      return list.map((e) => MarketTicker.fromJson(e as Map<String, dynamic>)).toList();
    }
    return [];
  }

  /// 获取单个交易对行情
  Future<MarketTicker?> getTicker(String symbol) async {
    try {
      final response = await _apiClient.get(
        '${ApiConstants.market}/ticker/$symbol',
      );
      final data = response.data;
      final tickerData = data is Map ? (data['data'] ?? data) : data;
      if (tickerData is Map) {
        return MarketTicker.fromJson(tickerData as Map<String, dynamic>);
      }
      return null;
    } on DioException {
      return null;
    }
  }

  /// 获取K线数据
  Future<List<Kline>> getKline({
    required String symbol,
    String interval = '1h',
    int limit = 100,
  }) async {
    final response = await _apiClient.get(
      '${ApiConstants.market}/kline/$symbol',
      queryParameters: {
        'interval': interval,
        'limit': limit,
      },
    );
    final data = response.data;
    final klines = data is Map ? (data['klines'] ?? data['data'] ?? []) : data;
    if (klines is List) {
      return klines.map((e) {
        if (e is List) return Kline.fromList(e);
        return Kline.fromList((e as Map<String, dynamic>)['kline'] as List);
      }).toList();
    }
    return [];
  }

  /// 获取支持的交易对列表
  Future<List<String>> getSupportedSymbols() async {
    final response = await _apiClient.get('${ApiConstants.market}/symbols');
    final data = response.data;
    final symbols = data is Map ? (data['symbols'] ?? data['data'] ?? []) : data;
    if (symbols is List) {
      return symbols.map((e) => e.toString()).toList();
    }
    return AppConstants.defaultSymbols;
  }
}

/// ============ Providers ============

final marketServiceProvider = Provider<MarketService>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return MarketService(apiClient);
});

/// 首页批量行情
final marketTickersProvider = FutureProvider<List<MarketTicker>>((ref) async {
  final service = ref.watch(marketServiceProvider);
  return service.getTickers();
});

/// 单个K线数据
final klineProvider = FutureProvider.family<List<Kline>, ({String symbol, String interval})>(
  (ref, params) async {
    final service = ref.watch(marketServiceProvider);
    return service.getKline(
      symbol: params.symbol,
      interval: params.interval,
    );
  },
);
