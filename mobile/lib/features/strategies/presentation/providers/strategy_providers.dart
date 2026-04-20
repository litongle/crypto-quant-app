import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/models/models.dart';

/// 策略模板列表
final strategyTemplatesProvider = FutureProvider<List<StrategyTemplate>>((ref) async {
  await Future.delayed(const Duration(milliseconds: 300));
  return StrategyTemplate.templates;
});

/// 策略实例列表
final strategyInstancesProvider = FutureProvider<List<StrategyInstance>>((ref) async {
  await Future.delayed(const Duration(milliseconds: 400));
  return StrategyInstance.mockList();
});

/// 选中的策略模板
final selectedTemplateProvider = StateProvider<StrategyTemplate?>((ref) => null);

/// 策略配置参数
final strategyParamsProvider = StateProvider<Map<String, dynamic>>((ref) => {});

/// 选中的币种
final selectedSymbolProvider = StateProvider<String>((ref) => 'BTC/USDT');

/// 选中的交易所
final selectedExchangeProvider = StateProvider<String>((ref) => 'Binance');
