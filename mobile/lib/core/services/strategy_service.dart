import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../constants/app_constants.dart';
import '../network/api_client.dart';

/// ============ 数据模型 ============

/// 策略模板参数
class StrategyParam {
  final String key;
  final String name;
  final String type; // int / double / select
  final num defaultValue;
  final num? min;
  final num? max;
  final num? step;
  final List<Map<String, String>>? options;

  const StrategyParam({
    required this.key,
    required this.name,
    required this.type,
    required this.defaultValue,
    this.min,
    this.max,
    this.step,
    this.options,
  });

  factory StrategyParam.fromJson(Map<String, dynamic> json) {
    return StrategyParam(
      key: json['key'] as String,
      name: json['name'] as String,
      type: json['type'] as String,
      defaultValue: json['default'] as num,
      min: json['min'] as num?,
      max: json['max'] as num?,
      step: json['step'] as num?,
      options: (json['options'] as List<dynamic>?)
          ?.map((e) => Map<String, String>.from(e as Map))
          .toList(),
    );
  }
}

/// 策略模板
class StrategyTemplate {
  final String id;
  final String name;
  final String description;
  final String icon;
  final bool isActive;
  final List<StrategyParam> params;

  const StrategyTemplate({
    required this.id,
    required this.name,
    required this.description,
    required this.icon,
    required this.isActive,
    required this.params,
  });

  factory StrategyTemplate.fromJson(Map<String, dynamic> json) {
    return StrategyTemplate(
      id: json['id'] as String,
      name: json['name'] as String,
      description: json['description'] as String? ?? '',
      icon: json['icon'] as String? ?? 'analytics',
      isActive: json['isActive'] as bool? ?? true,
      params: (json['params'] as List<dynamic>?)
              ?.map((e) => StrategyParam.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
    );
  }
}

/// 策略实例
class StrategyInstance {
  final String id;
  final String name;
  final String templateId;
  final String templateName;
  final String status; // running / stopped / paused
  final double totalPnl;
  final double totalPnlPercent;
  final double winRate;
  final int totalTrades;
  final DateTime? createdAt;

  const StrategyInstance({
    required this.id,
    required this.name,
    required this.templateId,
    required this.templateName,
    required this.status,
    required this.totalPnl,
    required this.totalPnlPercent,
    required this.winRate,
    required this.totalTrades,
    this.createdAt,
  });

  factory StrategyInstance.fromJson(Map<String, dynamic> json) {
    return StrategyInstance(
      id: json['id'] as String,
      name: json['name'] as String,
      templateId: json['templateId'] as String? ?? '',
      templateName: json['templateName'] as String? ?? '',
      status: json['status'] as String? ?? 'stopped',
      totalPnl: (json['totalPnl'] as num?)?.toDouble() ?? 0,
      totalPnlPercent: (json['totalPnlPercent'] as num?)?.toDouble() ?? 0,
      winRate: (json['winRate'] as num?)?.toDouble() ?? 0,
      totalTrades: json['totalTrades'] as int? ?? 0,
      createdAt: json['createdAt'] != null
          ? DateTime.tryParse(json['createdAt'].toString())
          : null,
    );
  }
}

/// ============ Service ============

class StrategyService {
  final ApiClient _apiClient;

  StrategyService(this._apiClient);

  /// 获取策略模板列表
  Future<List<StrategyTemplate>> getTemplates() async {
    final response = await _apiClient.get('${ApiConstants.strategies}/templates');
    final data = response.data;
    final templatesData = data is Map ? (data['data'] ?? data) : data;
    if (templatesData is List) {
      return templatesData.map((e) => StrategyTemplate.fromJson(e as Map<String, dynamic>)).toList();
    }
    return [];
  }

  /// 获取用户策略实例
  Future<List<StrategyInstance>> getInstances({String status = 'all'}) async {
    final response = await _apiClient.get(
      '${ApiConstants.strategies}/instances',
      queryParameters: {'status': status},
    );
    final data = response.data;
    final instancesData = data is Map ? (data['data'] ?? data) : data;
    if (instancesData is List) {
      return instancesData.map((e) => StrategyInstance.fromJson(e as Map<String, dynamic>)).toList();
    }
    return [];
  }

  /// 创建策略实例
  Future<StrategyInstance?> createInstance({
    required String name,
    required String templateId,
    required String exchange,
    required String symbol,
    Map<String, dynamic>? params,
  }) async {
    final response = await _apiClient.post(
      '${ApiConstants.strategies}/instances',
      data: {
        'name': name,
        'templateId': templateId,
        'exchange': exchange,
        'symbol': symbol,
        'params': params ?? {},
      },
    );
    final data = response.data;
    final instanceData = data is Map ? (data['data'] ?? data) : data;
    if (instanceData is Map) {
      return StrategyInstance.fromJson(instanceData as Map<String, dynamic>);
    }
    return null;
  }

  /// 启动策略
  Future<bool> startInstance(String instanceId) async {
    try {
      await _apiClient.post('${ApiConstants.strategies}/instances/$instanceId/start');
      return true;
    } on DioException {
      return false;
    }
  }

  /// 停止策略
  Future<bool> stopInstance(String instanceId) async {
    try {
      await _apiClient.post('${ApiConstants.strategies}/instances/$instanceId/stop');
      return true;
    } on DioException {
      return false;
    }
  }

  /// 更新策略参数
  Future<bool> updateInstance(String instanceId, {String? name, Map<String, dynamic>? params}) async {
    try {
      await _apiClient.put(
        '${ApiConstants.strategies}/instances/$instanceId',
        data: {
          if (name != null) 'name': name,
          if (params != null) 'params': params,
        },
      );
      return true;
    } on DioException {
      return false;
    }
  }

  /// 删除策略
  Future<bool> deleteInstance(String instanceId) async {
    try {
      await _apiClient.delete('${ApiConstants.strategies}/instances/$instanceId');
      return true;
    } on DioException {
      return false;
    }
  }
}

/// ============ Providers ============

final strategyServiceProvider = Provider<StrategyService>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return StrategyService(apiClient);
});

/// 策略模板
final strategyTemplatesProvider = FutureProvider<List<StrategyTemplate>>((ref) async {
  final service = ref.watch(strategyServiceProvider);
  return service.getTemplates();
});

/// 策略实例列表
final strategyInstancesProvider = FutureProvider<List<StrategyInstance>>((ref) async {
  final service = ref.watch(strategyServiceProvider);
  return service.getInstances();
});
