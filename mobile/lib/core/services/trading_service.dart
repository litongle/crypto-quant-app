import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../constants/app_constants.dart';
import '../network/api_client.dart';

/// ============ 数据模型 ============

/// 交易所账户
class ExchangeAccount {
  final int id;
  final String exchange;
  final String accountName;
  final bool isActive;
  final String status;

  const ExchangeAccount({
    required this.id,
    required this.exchange,
    required this.accountName,
    required this.isActive,
    required this.status,
  });

  factory ExchangeAccount.fromJson(Map<String, dynamic> json) {
    return ExchangeAccount(
      id: json['id'] as int,
      exchange: json['exchange'] as String,
      accountName: json['account_name'] ?? json['accountName'] ?? '',
      isActive: json['is_active'] ?? json['isActive'] ?? true,
      status: json['status'] as String? ?? 'active',
    );
  }
}

/// 交易持仓
class TradingPosition {
  final int id;
  final String symbol;
  final String side;
  final double quantity;
  final double entryPrice;
  final double currentPrice;
  final double unrealizedPnl;
  final double unrealizedPnlPercent;
  final int leverage;
  final double? stopLossPrice;
  final double? takeProfitPrice;
  final String status;

  const TradingPosition({
    required this.id,
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
    required this.status,
  });

  factory TradingPosition.fromJson(Map<String, dynamic> json) {
    return TradingPosition(
      id: json['id'] as int,
      symbol: json['symbol'] as String,
      side: json['side'] as String,
      quantity: (json['quantity'] as num).toDouble(),
      entryPrice: (json['entryPrice'] as num).toDouble(),
      currentPrice: (json['currentPrice'] as num).toDouble(),
      unrealizedPnl: (json['unrealizedPnl'] as num).toDouble(),
      unrealizedPnlPercent: (json['unrealizedPnlPercent'] as num).toDouble(),
      leverage: json['leverage'] as int? ?? 1,
      stopLossPrice: (json['stopLossPrice'] as num?)?.toDouble(),
      takeProfitPrice: (json['takeProfitPrice'] as num?)?.toDouble(),
      status: json['status'] as String? ?? 'open',
    );
  }
}

/// 订单
class Order {
  final int id;
  final String symbol;
  final String side;
  final String orderType;
  final double quantity;
  final double? price;
  final double filledQuantity;
  final double? avgFillPrice;
  final String status;
  final DateTime createdAt;

  const Order({
    required this.id,
    required this.symbol,
    required this.side,
    required this.orderType,
    required this.quantity,
    this.price,
    required this.filledQuantity,
    this.avgFillPrice,
    required this.status,
    required this.createdAt,
  });

  factory Order.fromJson(Map<String, dynamic> json) {
    return Order(
      id: json['id'] as int,
      symbol: json['symbol'] as String,
      side: json['side'] as String,
      orderType: json['order_type'] ?? json['orderType'] ?? 'market',
      quantity: (json['quantity'] as num).toDouble(),
      price: (json['price'] as num?)?.toDouble(),
      filledQuantity: (json['filledQuantity'] as num?)?.toDouble() ?? 0,
      avgFillPrice: (json['avgFillPrice'] as num?)?.toDouble(),
      status: json['status'] as String? ?? 'pending',
      createdAt: DateTime.parse(json['created_at'] ?? json['createdAt']),
    );
  }
}

/// ============ Service ============

class TradingService {
  final ApiClient _apiClient;

  TradingService(this._apiClient);

  /// 获取交易所账户
  Future<List<ExchangeAccount>> getAccounts() async {
    final response = await _apiClient.get('${ApiConstants.trading}/accounts');
    final data = response.data;
    if (data is List) {
      return data.map((e) => ExchangeAccount.fromJson(e as Map<String, dynamic>)).toList();
    }
    return [];
  }

  /// 获取交易持仓
  Future<List<TradingPosition>> getPositions({int? accountId}) async {
    final response = await _apiClient.get(
      '${ApiConstants.trading}/positions',
      queryParameters: accountId != null ? {'account_id': accountId} : null,
    );
    final data = response.data;
    if (data is List) {
      return data.map((e) => TradingPosition.fromJson(e as Map<String, dynamic>)).toList();
    }
    return [];
  }

  /// 获取订单历史
  Future<List<Order>> getOrders({int? accountId, String? symbol, int limit = 100}) async {
    final response = await _apiClient.get(
      '${ApiConstants.trading}',
      queryParameters: {
        if (accountId != null) 'account_id': accountId,
        if (symbol != null) 'symbol': symbol,
        'limit': limit,
      },
    );
    final data = response.data;
    if (data is List) {
      return data.map((e) => Order.fromJson(e as Map<String, dynamic>)).toList();
    }
    return [];
  }

  /// 创建订单
  Future<Order?> createOrder({
    required int accountId,
    required String symbol,
    required String side,
    required String orderType,
    required double quantity,
    double? price,
    int? strategyInstanceId,
  }) async {
    final response = await _apiClient.post(
      ApiConstants.trading,
      data: {
        'account_id': accountId,
        'symbol': symbol,
        'side': side,
        'order_type': orderType,
        'quantity': quantity,
        if (price != null) 'price': price,
        if (strategyInstanceId != null) 'strategy_instance_id': strategyInstanceId,
      },
    );
    final data = response.data;
    if (data is Map) {
      return Order.fromJson(data as Map<String, dynamic>);
    }
    return null;
  }

  /// 取消订单
  Future<bool> cancelOrder(int orderId) async {
    try {
      await _apiClient.post('${ApiConstants.trading}/$orderId/cancel');
      return true;
    } on DioException {
      return false;
    }
  }

  /// 平仓
  Future<bool> closePosition(int positionId) async {
    try {
      await _apiClient.post('${ApiConstants.trading}/$positionId/close');
      return true;
    } on DioException {
      return false;
    }
  }

  /// 紧急平仓
  Future<int> emergencyCloseAll({int? accountId}) async {
    final response = await _apiClient.post(
      '${ApiConstants.trading}/emergency-close-all',
      queryParameters: accountId != null ? {'account_id': accountId} : null,
    );
    final data = response.data;
    return (data is Map ? (data['closed_count'] as int?) ?? 0 : 0);
  }
}

/// ============ Providers ============

final tradingServiceProvider = Provider<TradingService>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return TradingService(apiClient);
});

/// 交易所账户
final tradingAccountsProvider = FutureProvider<List<ExchangeAccount>>((ref) async {
  final service = ref.watch(tradingServiceProvider);
  return service.getAccounts();
});

/// 交易持仓
final tradingPositionsProvider = FutureProvider<List<TradingPosition>>((ref) async {
  final service = ref.watch(tradingServiceProvider);
  return service.getPositions();
});

/// 订单历史
final ordersProvider = FutureProvider<List<Order>>((ref) async {
  final service = ref.watch(tradingServiceProvider);
  return service.getOrders();
});
