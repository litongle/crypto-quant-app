import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:intl/intl.dart';

/// 回测结果模型
class BacktestResult {
  final String symbol;
  final String strategy;
  final DateTime startDate;
  final DateTime endDate;
  final double totalReturn;
  final double annualReturn;
  final double sharpeRatio;
  final double maxDrawdown;
  final double winRate;
  final double profitLossRatio;
  final int totalTrades;
  final List<BacktestTrade> trades;
  final List<double> equityCurve;
  final List<double> benchmarkCurve;

  const BacktestResult({
    required this.symbol,
    required this.strategy,
    required this.startDate,
    required this.endDate,
    required this.totalReturn,
    required this.annualReturn,
    required this.sharpeRatio,
    required this.maxDrawdown,
    required this.winRate,
    required this.profitLossRatio,
    required this.totalTrades,
    required this.trades,
    required this.equityCurve,
    required this.benchmarkCurve,
  });
}

class BacktestTrade {
  final DateTime date;
  final String action;
  final double price;
  final double quantity;
  final double pnl;

  const BacktestTrade({
    required this.date,
    required this.action,
    required this.price,
    required this.quantity,
    required this.pnl,
  });
}

/// 回测历史 Provider
final backtestHistoryProvider = FutureProvider<List<BacktestResult>>((ref) async {
  await Future.delayed(const Duration(milliseconds: 500));
  return _placeholderResults;
});

final _placeholderResults = [
  BacktestResult(
    symbol: 'BTC/USDT',
    strategy: '双均线策略',
    startDate: DateTime(2023, 1, 1),
    endDate: DateTime(2025, 12, 31),
    totalReturn: 186.4,
    annualReturn: 58.2,
    sharpeRatio: 2.34,
    maxDrawdown: -12.8,
    winRate: 68.5,
    profitLossRatio: 1.82,
    totalTrades: 156,
    trades: [],
    equityCurve: _generateEquityCurve(186.4),
    benchmarkCurve: _generateEquityCurve(120.5),
  ),
  BacktestResult(
    symbol: 'ETH/USDT',
    strategy: 'RSI 超买超卖',
    startDate: DateTime(2024, 1, 1),
    endDate: DateTime(2025, 12, 31),
    totalReturn: 85.3,
    annualReturn: 42.6,
    sharpeRatio: 1.95,
    maxDrawdown: -18.5,
    winRate: 62.3,
    profitLossRatio: 1.45,
    totalTrades: 89,
    trades: [],
    equityCurve: _generateEquityCurve(85.3),
    benchmarkCurve: _generateEquityCurve(75.2),
  ),
];

List<double> _generateEquityCurve(double targetReturn) {
  final List<double> curve = [];
  double value = 100;
  for (int i = 0; i < 100; i++) {
    final progress = i / 100;
    final noise = (value * 0.02 * (0.5 - (i % 3) / 6));
    value = 100 * (1 + (targetReturn / 100) * progress) + noise * (1 - progress);
    curve.add(value);
  }
  return curve;
}

class BacktestPage extends ConsumerStatefulWidget {
  const BacktestPage({super.key});

  @override
  ConsumerState<BacktestPage> createState() => _BacktestPageState();
}

class _BacktestPageState extends ConsumerState<BacktestPage> {
  BacktestResult? _selectedResult;

  @override
  Widget build(BuildContext context) {
    final historyAsync = ref.watch(backtestHistoryProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('回测历史'),
      ),
      body: historyAsync.when(
        data: (results) {
          if (results.isEmpty) {
            return _buildEmptyState(context);
          }

          return CustomScrollView(
            slivers: [
              // 历史记录列表
              SliverPadding(
                padding: const EdgeInsets.all(16),
                sliver: SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (context, index) {
                      final result = results[index];
                      return _BacktestResultCard(
                        result: result,
                        isSelected: _selectedResult?.symbol == result.symbol,
                        onTap: () {
                          setState(() {
                            _selectedResult = result;
                          });
                        },
                      );
                    },
                    childCount: results.length,
                  ),
                ),
              ),

              // 详细结果展示
              if (_selectedResult != null)
                SliverPadding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  sliver: SliverToBoxAdapter(
                    child: _buildDetailSection(context, _selectedResult!),
                  ),
                ),

              const SliverPadding(padding: EdgeInsets.only(bottom: 100)),
            ],
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, stack) => Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.error_outline, size: 64),
              const SizedBox(height: 16),
              Text('加载失败: $error'),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: () => ref.invalidate(backtestHistoryProvider),
                child: const Text('重试'),
              ),
            ],
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          // TODO: 跳转到新回测页面
        },
        backgroundColor: const Color(0xFF06B6D4),
        icon: const Icon(Icons.add),
        label: const Text('新建回测'),
      ),
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.history,
            size: 80,
            color: Colors.grey[600],
          ),
          const SizedBox(height: 20),
          Text(
            '暂无回测记录',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
              color: Colors.grey[500],
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '去策略中心创建你的第一个回测',
            style: TextStyle(color: Colors.grey[600]),
          ),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: () {
              // TODO: 跳转到策略中心
            },
            icon: const Icon(Icons.analytics),
            label: const Text('前往策略中心'),
          ),
        ],
      ),
    );
  }

  Widget _buildDetailSection(BuildContext context, BacktestResult result) {
    final dateFormat = DateFormat('yyyy-MM-dd');

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Theme.of(context).dividerColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 标题
          Row(
            children: [
              Text(
                result.symbol,
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 18,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF22D3EE).withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  result.strategy,
                  style: const TextStyle(
                    color: Color(0xFF22D3EE),
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '${dateFormat.format(result.startDate)} ~ ${dateFormat.format(result.endDate)}',
            style: TextStyle(
              color: Colors.grey[500],
              fontSize: 12,
            ),
          ),

          const SizedBox(height: 20),

          // 核心指标
          Row(
            children: [
              _MetricCard(
                label: '总收益率',
                value: '+${result.totalReturn.toStringAsFixed(1)}%',
                color: const Color(0xFF22C55E),
              ),
              const SizedBox(width: 10),
              _MetricCard(
                label: '年化收益',
                value: '+${result.annualReturn.toStringAsFixed(1)}%',
                color: const Color(0xFF22C55E),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              _MetricCard(
                label: '夏普比率',
                value: result.sharpeRatio.toStringAsFixed(2),
                color: const Color(0xFF22D3EE),
              ),
              const SizedBox(width: 10),
              _MetricCard(
                label: '最大回撤',
                value: '${result.maxDrawdown.toStringAsFixed(1)}%',
                color: const Color(0xFFEF4444),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              _MetricCard(
                label: '胜率',
                value: '${result.winRate.toStringAsFixed(1)}%',
                color: Colors.white,
              ),
              const SizedBox(width: 10),
              _MetricCard(
                label: '盈亏比',
                value: result.profitLossRatio.toStringAsFixed(2),
                color: Colors.white,
              ),
            ],
          ),

          const SizedBox(height: 24),

          // 收益曲线图
          const Text(
            '收益曲线',
            style: TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 200,
            child: _buildEquityChart(result),
          ),

          const SizedBox(height: 20),

          // 操作按钮
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () {
                    // TODO: 导出报告
                  },
                  icon: const Icon(Icons.download),
                  label: const Text('导出报告'),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    side: const BorderSide(color: Color(0xFF374151)),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: () {
                    // TODO: 启动策略
                  },
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('启动策略'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF22C55E),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildEquityChart(BacktestResult result) {
    final strategySpots = result.equityCurve.asMap().entries.map((e) {
      return FlSpot(e.key.toDouble(), e.value);
    }).toList();

    final benchmarkSpots = result.benchmarkCurve.asMap().entries.map((e) {
      return FlSpot(e.key.toDouble(), e.value);
    }).toList();

    return LineChart(
      LineChartData(
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          horizontalInterval: 50,
          getDrawingHorizontalLine: (value) {
            return FlLine(
              color: Colors.grey[800]!,
              strokeWidth: 0.5,
            );
          },
        ),
        titlesData: const FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        lineTouchData: LineTouchData(
          enabled: true,
          touchTooltipData: LineTouchTooltipData(
            tooltipBgColor: const Color(0xFF1F2937),
            tooltipRoundedRadius: 8,
          ),
        ),
        lineBarsData: [
          LineChartBarData(
            spots: strategySpots,
            isCurved: true,
            color: const Color(0xFF22C55E),
            barWidth: 2,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              color: const Color(0xFF22C55E).withOpacity(0.1),
            ),
          ),
          LineChartBarData(
            spots: benchmarkSpots,
            isCurved: true,
            color: Colors.grey[500],
            barWidth: 1,
            dotData: const FlDotData(show: false),
            dashArray: [5, 5],
          ),
        ],
      ),
    );
  }
}

class _BacktestResultCard extends StatelessWidget {
  final BacktestResult result;
  final bool isSelected;
  final VoidCallback onTap;

  const _BacktestResultCard({
    required this.result,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Theme.of(context).cardColor,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isSelected
                ? const Color(0xFF22D3EE)
                : Theme.of(context).dividerColor,
            width: isSelected ? 2 : 1,
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        result.symbol,
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 16,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        result.strategy,
                        style: TextStyle(
                          color: Colors.grey[500],
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      _buildMiniMetric('总收益', '+${result.totalReturn.toStringAsFixed(1)}%',
                          result.totalReturn >= 0),
                      const SizedBox(width: 16),
                      _buildMiniMetric('夏普', result.sharpeRatio.toStringAsFixed(2), true),
                      const SizedBox(width: 16),
                      _buildMiniMetric('胜率', '${result.winRate.toStringAsFixed(0)}%',
                          result.winRate >= 50),
                    ],
                  ),
                ],
              ),
            ),
            Icon(
              isSelected ? Icons.check_circle : Icons.chevron_right,
              color: isSelected ? const Color(0xFF22D3EE) : Colors.grey,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMiniMetric(String label, String value, bool isPositive) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: Colors.grey[500],
            fontSize: 10,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(
            color: isPositive ? const Color(0xFF22C55E) : const Color(0xFFEF4444),
            fontWeight: FontWeight.bold,
            fontSize: 13,
          ),
        ),
      ],
    );
  }
}

class _MetricCard extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _MetricCard({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 14),
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          children: [
            Text(
              label,
              style: TextStyle(
                color: Colors.grey[500],
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              value,
              style: TextStyle(
                color: color,
                fontSize: 18,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
