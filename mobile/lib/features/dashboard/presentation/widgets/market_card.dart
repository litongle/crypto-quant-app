import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../../data/models/market_ticker.dart';

/// 行情卡片组件
class MarketCard extends StatelessWidget {
  final MarketTicker ticker;
  final VoidCallback? onTap;

  const MarketCard({
    super.key,
    required this.ticker,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isRising = ticker.isRising;
    final changeColor = isRising
        ? const Color(0xFF22C55E)  // Green
        : const Color(0xFFEF4444); // Red

    return Card(
      margin: EdgeInsets.zero,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              // 币种图标
              _buildCoinIcon(),
              const SizedBox(width: 12),

              // 币种信息
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      ticker.baseAsset,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      ticker.symbol,
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ),
              ),

              // 迷你趋势图
              SizedBox(
                width: 50,
                height: 30,
                child: _buildSparkline(isRising),
              ),

              const SizedBox(width: 12),

              // 价格信息
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    _formatPrice(ticker.price, ticker.pricePrecision),
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: changeColor.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      '${isRising ? '+' : ''}${ticker.priceChangePercent24h.toStringAsFixed(ticker.percentPrecision)}%',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: changeColor,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCoinIcon() {
    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        color: _getCoinColor().withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Center(
        child: Text(
          ticker.baseAsset.substring(0, ticker.baseAsset.length > 2 ? 2 : ticker.baseAsset.length),
          style: TextStyle(
            color: _getCoinColor(),
            fontWeight: FontWeight.bold,
            fontSize: 14,
          ),
        ),
      ),
    );
  }

  Color _getCoinColor() {
    switch (ticker.baseAsset.toUpperCase()) {
      case 'BTC':
        return const Color(0xFFF7931A);
      case 'ETH':
        return const Color(0xFF627EEA);
      case 'SOL':
        return const Color(0xFF9945FF);
      case 'BNB':
        return const Color(0xFFF0B90B);
      case 'DOGE':
        return const Color(0xFFC3A634);
      default:
        return const Color(0xFF6366F1);
    }
  }

  Widget _buildSparkline(bool isRising) {
    final color = isRising
        ? const Color(0xFF22C55E)
        : const Color(0xFFEF4444);

    if (ticker.sparkline.isEmpty) {
      return const SizedBox();
    }

    final spots = ticker.sparkline.asMap().entries.map((e) {
      return FlSpot(e.key.toDouble(), e.value);
    }).toList();

    return LineChart(
      LineChartData(
        gridData: const FlGridData(show: false),
        titlesData: const FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        lineTouchData: const LineTouchData(enabled: false),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            curveSmoothness: 0.3,
            color: color,
            barWidth: 1.5,
            isStrokeCapRound: true,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              color: color.withValues(alpha: 0.1),
            ),
          ),
        ],
      ),
    );
  }

  String _formatPrice(double price, int precision) {
    if (price >= 10000) {
      return '\$${price.toStringAsFixed(2)}';
    } else if (price >= 1) {
      return '\$${price.toStringAsFixed(precision)}';
    } else {
      return '\$${price.toStringAsFixed(precision)}';
    }
  }
}
