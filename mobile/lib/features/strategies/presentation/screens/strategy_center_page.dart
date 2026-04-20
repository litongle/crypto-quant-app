import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/services/strategy_service.dart' as api;

/// 策略模板本地视图模型（包装后端数据）
class StrategyTemplateView {
  final String id;
  final String name;
  final String description;
  final String icon;
  final String suitableMarket;
  final List<StrategyParameterView> parameters;

  const StrategyTemplateView({
    required this.id,
    required this.name,
    required this.description,
    required this.icon,
    required this.suitableMarket,
    required this.parameters,
  });

  /// 从后端 StrategyTemplate 转换
  factory StrategyTemplateView.fromApi(api.StrategyTemplate t) {
    final icons = {
      'ma_cross': '📊',
      'rsi': '📉',
      'bollinger': '🎯',
      'grid': '🟦',
      'martingale': '🎰',
    };
    final markets = {
      'ma_cross': '趋势行情',
      'rsi': '震荡行情',
      'bollinger': '波动行情',
      'grid': '横盘行情',
      'martingale': '高波动',
    };
    return StrategyTemplateView(
      id: t.id,
      name: t.name,
      description: t.description,
      icon: icons[t.id] ?? '📈',
      suitableMarket: markets[t.id] ?? '通用',
      parameters: t.params.map((p) => StrategyParameterView(
        name: p.key,
        label: p.name,
        min: (p.min ?? 0).toDouble(),
        max: (p.max ?? 100).toDouble(),
        defaultValue: p.defaultValue.toDouble(),
        step: (p.step ?? 1).toDouble(),
      )).toList(),
    );
  }
}

/// 策略参数
class StrategyParameterView {
  final String name;
  final String label;
  final double min;
  final double max;
  final double defaultValue;
  final double step;

  const StrategyParameterView({
    required this.name,
    required this.label,
    required this.min,
    required this.max,
    required this.defaultValue,
    required this.step,
  });
}

/// 策略实例视图
class StrategyInstanceView {
  final String id;
  final String templateId;
  final String symbol;
  final String status;
  final double totalPnl;
  final DateTime createdAt;

  const StrategyInstanceView({
    required this.id,
    required this.templateId,
    required this.symbol,
    required this.status,
    required this.totalPnl,
    required this.createdAt,
  });

  factory StrategyInstanceView.fromApi(api.StrategyInstance i) {
    return StrategyInstanceView(
      id: i.id,
      templateId: i.templateId,
      symbol: i.templateName,
      status: i.status,
      totalPnl: i.totalPnl,
      createdAt: i.createdAt ?? DateTime.now(),
    );
  }
}

/// 策略模板列表 Provider
final strategyTemplatesViewProvider = FutureProvider<List<StrategyTemplateView>>((ref) async {
  try {
    final templates = await ref.watch(api.strategyTemplatesProvider.future);
    return templates.map((t) => StrategyTemplateView.fromApi(t)).toList();
  } catch (_) {
    // API 不可用时返回占位数据
    return _placeholderTemplates;
  }
});

/// 策略实例列表 Provider
final strategyInstancesViewProvider = FutureProvider<List<StrategyInstanceView>>((ref) async {
  try {
    final instances = await ref.watch(api.strategyInstancesProvider.future);
    return instances.map((i) => StrategyInstanceView.fromApi(i)).toList();
  } catch (_) {
    return _placeholderInstances;
  }
});

/// 占位策略模板
const _placeholderTemplates = <StrategyTemplateView>[
  StrategyTemplateView(
    id: 'ma_cross',
    name: '双均线策略',
    description: '基于快慢均线交叉产生买卖信号',
    icon: '📊',
    suitableMarket: '趋势行情',
    parameters: [
      StrategyParameterView(name: 'fast_period', label: '快线周期', min: 5, max: 30, defaultValue: 10, step: 1),
      StrategyParameterView(name: 'slow_period', label: '慢线周期', min: 20, max: 120, defaultValue: 30, step: 1),
    ],
  ),
  StrategyTemplateView(
    id: 'rsi',
    name: 'RSI 超买超卖',
    description: 'RSI 指标超买超卖反转策略',
    icon: '📉',
    suitableMarket: '震荡行情',
    parameters: [
      StrategyParameterView(name: 'period', label: 'RSI 周期', min: 5, max: 30, defaultValue: 14, step: 1),
      StrategyParameterView(name: 'overbought', label: '超买阈值', min: 60, max: 90, defaultValue: 70, step: 1),
      StrategyParameterView(name: 'oversold', label: '超卖阈值', min: 10, max: 40, defaultValue: 30, step: 1),
    ],
  ),
  StrategyTemplateView(
    id: 'grid',
    name: '网格交易',
    description: '在价格区间内自动低买高卖',
    icon: '🟦',
    suitableMarket: '横盘行情',
    parameters: [
      StrategyParameterView(name: 'grid_num', label: '网格数量', min: 3, max: 50, defaultValue: 10, step: 1),
      StrategyParameterView(name: 'range', label: '价格范围%', min: 1, max: 30, defaultValue: 5, step: 0.5),
    ],
  ),
  StrategyTemplateView(
    id: 'martingale',
    name: '马丁格尔',
    description: '亏损后加倍仓位，回本即止',
    icon: '🎰',
    suitableMarket: '高波动',
    parameters: [
      StrategyParameterView(name: 'max_level', label: '最大倍投层数', min: 1, max: 10, defaultValue: 5, step: 1),
      StrategyParameterView(name: 'multiplier', label: '倍投系数', min: 1, max: 3, defaultValue: 2, step: 0.1),
    ],
  ),
];

/// 占位策略实例
final _placeholderInstances = <StrategyInstanceView>[
  StrategyInstanceView(
    id: '1',
    templateId: 'ma_cross',
    symbol: 'BTC/USDT',
    status: 'running',
    totalPnl: 1084.20,
    createdAt: DateTime.now().subtract(const Duration(days: 42)),
  ),
  StrategyInstanceView(
    id: '2',
    templateId: 'grid',
    symbol: 'ETH/USDT',
    status: 'paused',
    totalPnl: -56.80,
    createdAt: DateTime.now().subtract(const Duration(days: 15)),
  ),
];

/// 当前选中的策略模板
final selectedTemplateProvider = StateProvider<StrategyTemplateView?>((ref) => null);

/// 策略参数状态
final strategyParamsProvider = StateProvider<Map<String, double>>((ref) => {});

class StrategyCenterPage extends ConsumerStatefulWidget {
  const StrategyCenterPage({super.key});

  @override
  ConsumerState<StrategyCenterPage> createState() => _StrategyCenterPageState();
}

class _StrategyCenterPageState extends ConsumerState<StrategyCenterPage> {
  String _selectedSymbol = 'BTC/USDT';

  @override
  Widget build(BuildContext context) {
    final templatesAsync = ref.watch(strategyTemplatesViewProvider);
    final selectedTemplate = ref.watch(selectedTemplateProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('策略中心'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Chip(
              label: const Text('已配置 2 个'),
              backgroundColor: Theme.of(context).cardColor,
              labelStyle: const TextStyle(fontSize: 12),
            ),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 策略模板选择
            Text(
              '选择策略模板',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),

            templatesAsync.when(
              data: (templates) => Column(
                children: templates.map((template) {
                  return _StrategyTemplateCard(
                    template: template,
                    isSelected: selectedTemplate?.id == template.id,
                    onTap: () {
                      ref.read(selectedTemplateProvider.notifier).state = template;
                      ref.read(strategyParamsProvider.notifier).state = {
                        for (var p in template.parameters)
                          p.name: p.defaultValue,
                      };
                    },
                  );
                }).toList(),
              ),
              loading: () => const Center(
                child: CircularProgressIndicator(),
              ),
              error: (error, stack) => Center(
                child: Text('加载失败: $error'),
              ),
            ),

            // 参数配置区
            if (selectedTemplate != null) ...[
              const SizedBox(height: 20),
              _buildConfigSection(context, selectedTemplate),
            ],

            const SizedBox(height: 20),

            // 懒人模式
            _buildLazyModeCard(context),

            const SizedBox(height: 20),

            // 开始回测按钮
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: selectedTemplate != null
                    ? () => _runBacktest(context)
                    : null,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: const Color(0xFF06B6D4),
                ),
                child: const Text(
                  '🚀 开始回测',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),

            const SizedBox(height: 80),
          ],
        ),
      ),
    );
  }

  Widget _buildConfigSection(BuildContext context, StrategyTemplateView template) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Theme.of(context).dividerColor,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                '⚙️',
                style: TextStyle(fontSize: 18),
              ),
              const SizedBox(width: 8),
              Text(
                '参数配置',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),

          // 交易对选择
          Row(
            children: [
              const Text(
                '交易对：',
                style: TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(width: 12),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'BTC/USDT', label: Text('BTC')),
                  ButtonSegment(value: 'ETH/USDT', label: Text('ETH')),
                  ButtonSegment(value: 'SOL/USDT', label: Text('SOL')),
                ],
                selected: {_selectedSymbol},
                onSelectionChanged: (selected) {
                  setState(() {
                    _selectedSymbol = selected.first;
                  });
                },
                style: ButtonStyle(
                  visualDensity: VisualDensity.compact,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),

          // 参数滑块
          ...template.parameters.map((param) {
            return _ParameterSlider(
              parameter: param,
              value: ref.watch(strategyParamsProvider)[param.name] ?? param.defaultValue,
              onChanged: (value) {
                ref.read(strategyParamsProvider.notifier).update((state) {
                  return {...state, param.name: value};
                });
              },
            );
          }),
        ],
      ),
    );
  }

  Widget _buildLazyModeCard(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF0c1525), Color(0xFF111827)],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: const Color(0xFF1e3a5f),
        ),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFF06B6D4), Color(0xFF3B82F6)],
                  ),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Center(
                  child: Text('🎯', style: TextStyle(fontSize: 18)),
                ),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '懒人模式',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 14,
                      ),
                    ),
                    Text(
                      'AI 自动优化参数',
                      style: TextStyle(
                        color: Colors.grey,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(
              onPressed: () => _showAIModal(context),
              style: OutlinedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 12),
                side: const BorderSide(color: Color(0xFF374151)),
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text('🤖 '),
                  Text('AI 一键优化参数'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          const Center(
            child: Text(
              '预计耗时 30 秒',
              style: TextStyle(
                color: Colors.grey,
                fontSize: 11,
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _runBacktest(BuildContext context) {
    final template = ref.read(selectedTemplateProvider);
    final params = ref.read(strategyParamsProvider);
    // TODO: 调用回测 API
    debugPrint('回测配置: $template, $params, $_selectedSymbol');
  }

  void _showAIModal(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('🤖 AI 优化中...'),
        content: const Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('正在分析最近 3 年数据...'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
        ],
      ),
    );
  }
}

class _StrategyTemplateCard extends StatelessWidget {
  final StrategyTemplateView template;
  final bool isSelected;
  final VoidCallback onTap;

  const _StrategyTemplateCard({
    required this.template,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Theme.of(context).cardColor,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isSelected ? const Color(0xFF22D3EE) : Theme.of(context).dividerColor,
            width: isSelected ? 2 : 1,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 50,
              height: 50,
              decoration: BoxDecoration(
                color: const Color(0xFF22D3EE).withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Center(
                child: Text(
                  template.icon,
                  style: const TextStyle(fontSize: 24),
                ),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    template.name,
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 15,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    template.description,
                    style: TextStyle(
                      color: Colors.grey[500],
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: Colors.blue.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      '适合: ${template.suitableMarket}',
                      style: const TextStyle(
                        color: Colors.blue,
                        fontSize: 10,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            if (isSelected)
              const Icon(
                Icons.check_circle,
                color: Color(0xFF22D3EE),
              ),
          ],
        ),
      ),
    );
  }
}

class _ParameterSlider extends StatelessWidget {
  final StrategyParameterView parameter;
  final double value;
  final ValueChanged<double> onChanged;

  const _ParameterSlider({
    required this.parameter,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                parameter.label,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF22D3EE).withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  parameter.step < 1
                      ? value.toStringAsFixed(1)
                      : value.toInt().toString(),
                  style: const TextStyle(
                    color: Color(0xFF22D3EE),
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: const Color(0xFF22D3EE),
              inactiveTrackColor: const Color(0xFF1F2937),
              thumbColor: const Color(0xFF22D3EE),
              overlayColor: const Color(0xFF22D3EE).withOpacity(0.2),
            ),
            child: Slider(
              value: value,
              min: parameter.min,
              max: parameter.max,
              divisions: ((parameter.max - parameter.min) / parameter.step).round(),
              onChanged: onChanged,
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                parameter.step < 1
                    ? parameter.min.toStringAsFixed(1)
                    : parameter.min.toInt().toString(),
                style: TextStyle(
                  color: Colors.grey[500],
                  fontSize: 11,
                ),
              ),
              Text(
                parameter.step < 1
                    ? parameter.max.toStringAsFixed(1)
                    : parameter.max.toInt().toString(),
                style: TextStyle(
                  color: Colors.grey[500],
                  fontSize: 11,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
