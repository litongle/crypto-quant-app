import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/market_coin.dart';
import '../providers/dashboard_provider.dart';
import '../widgets/asset_summary_card.dart';
import '../widgets/equity_chart.dart';
import '../widgets/quick_signal_card.dart';
import '../widgets/market_list_tile.dart';
import '../widgets/position_card.dart';

class DashboardPage extends ConsumerWidget {
  const DashboardPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dashboardAsync = ref.watch(dashboardProvider);

    return Scaffold(
      body: SafeArea(
        child: dashboardAsync.when(
          data: (dashboard) => RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(dashboardProvider);
            },
            child: CustomScrollView(
              slivers: [
                // 顶部状态栏
                SliverToBoxAdapter(
                  child: _buildHeader(context, dashboard.totalAsset, dashboard.totalProfitPercent),
                ),

                // 内容区
                SliverPadding(
                  padding: const EdgeInsets.all(16),
                  sliver: SliverList(
                    delegate: SliverChildListDelegate([
                      // 资产概览卡片
                      AssetSummaryCard(
                        todayProfit: dashboard.todayProfit,
                        annualYield: dashboard.annualYield,
                        equityCurve: dashboard.equityCurve,
                      ),
                      const SizedBox(height: 12),

                      // 快捷信号和策略状态
                      Row(
                        children: [
                          Expanded(
                            child: QuickSignalCard(
                              signal: dashboard.currentSignal,
                              confidence: dashboard.signalConfidence,
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: QuickSignalCard(
                              signal: dashboard.strategyName,
                              confidence: dashboard.strategyDays.toDouble(),
                              isStrategy: true,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),

                      // 市场行情标题
                      _buildSectionTitle(
                        context,
                        '市场行情',
                        onSeeAll: () => _navigateToMarket(context),
                      ),
                      const SizedBox(height: 10),

                      // 市场行情列表
                      MarketListTile(coins: dashboard.marketCoins),
                      const SizedBox(height: 16),

                      // 持仓概览标题
                      _buildSectionTitle(
                        context,
                        '我的持仓',
                        onSeeAll: () => _navigateToPositions(context),
                      ),
                      const SizedBox(height: 10),

                      // 持仓列表
                      ...dashboard.positions.map(
                        (position) => Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: PositionCard(position: position),
                        ),
                      ),

                      const SizedBox(height: 80),
                    ]),
                  ),
                ),
              ],
            ),
          ),
          loading: () => const Center(
            child: CircularProgressIndicator(),
          ),
          error: (error, stack) => Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.cloud_off,
                    size: 64,
                    color: Colors.grey[600],
                  ),
                  const SizedBox(height: 16),
                  Text(
                    '暂无法连接服务器',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '已为您展示示例数据',
                    style: TextStyle(color: Colors.grey[500], fontSize: 13),
                  ),
                  const SizedBox(height: 24),
                  ElevatedButton.icon(
                    onPressed: () => ref.invalidate(dashboardProvider),
                    icon: const Icon(Icons.refresh),
                    label: const Text('重试'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF06B6D4),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context, double totalAsset, double profitPercent) {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
      decoration: BoxDecoration(
        color: Theme.of(context).scaffoldBackgroundColor,
        border: Border(
          bottom: BorderSide(
            color: Theme.of(context).dividerColor,
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '总资产 (USD)',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Colors.grey[600],
                  ),
                ),
                const SizedBox(height: 4),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      '\$${_formatNumber(totalAsset)}',
                      style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: profitPercent >= 0
                            ? Colors.green.withOpacity(0.1)
                            : Colors.red.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        '${profitPercent >= 0 ? '+' : ''}${profitPercent.toStringAsFixed(2)}%',
                        style: TextStyle(
                          color: profitPercent >= 0 ? Colors.green : Colors.red,
                          fontWeight: FontWeight.w600,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          // 实时指示器
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.green.withOpacity(0.1),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: const BoxDecoration(
                    color: Colors.green,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 6),
                const Text(
                  '实时',
                  style: TextStyle(
                    color: Colors.green,
                    fontWeight: FontWeight.w600,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionTitle(
    BuildContext context,
    String title, {
    VoidCallback? onSeeAll,
  }) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          title,
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        if (onSeeAll != null)
          GestureDetector(
            onTap: onSeeAll,
            child: Text(
              '查看全部 →',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Colors.grey[600],
              ),
            ),
          ),
      ],
    );
  }

  String _formatNumber(double value) {
    if (value >= 1000000) {
      return '${(value / 1000000).toStringAsFixed(2)}M';
    } else if (value >= 1000) {
      return '${(value / 1000).toStringAsFixed(2)}K';
    }
    return value.toStringAsFixed(2);
  }

  void _navigateToMarket(BuildContext context) {
    // TODO: 跳转到市场行情页
  }

  void _navigateToPositions(BuildContext context) {
    // TODO: 跳转到持仓管理页
  }
}
