import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../data/models/market_coin.dart';

/// 持仓卡片 Widget
class PositionCard extends StatelessWidget {
  final Position position;

  const PositionCard({
    super.key,
    required this.position,
  });

  @override
  Widget build(BuildContext context) {
    final currencyFormat = NumberFormat.currency(symbol: '\$', decimalDigits: 2);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Theme.of(context).dividerColor,
          width: 1,
        ),
      ),
      child: Column(
        children: [
          // 头部：币种信息
          Row(
            children: [
              // 币种图标
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: _getCoinColor(position.symbol).withOpacity(0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Center(
                  child: Text(
                    _getCoinSymbol(position.symbol),
                    style: TextStyle(
                      color: _getCoinColor(position.symbol),
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),

              // 币种名称和数量
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          position.symbol,
                          style: const TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 16,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.blue.withOpacity(0.1),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            position.exchange,
                            style: const TextStyle(
                              color: Colors.blue,
                              fontSize: 10,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${position.quantity} ${position.symbol}',
                      style: TextStyle(
                        color: Colors.grey[500],
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),

              // 盈亏信息
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    currencyFormat.format(position.totalValue),
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 16,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      Icon(
                        position.isProfit
                            ? Icons.arrow_upward
                            : Icons.arrow_downward,
                        size: 12,
                        color: position.isProfit
                            ? Colors.green
                            : Colors.red,
                      ),
                      Text(
                        '${position.isProfit ? '+' : ''}${position.pnl.toStringAsFixed(2)}',
                        style: TextStyle(
                          color: position.isProfit ? Colors.green : Colors.red,
                          fontWeight: FontWeight.w600,
                          fontSize: 13,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),

          const SizedBox(height: 12),
          const Divider(height: 1),
          const SizedBox(height: 12),

          // 详细信息
          Row(
            children: [
              _buildInfoItem(
                context,
                '开仓价',
                currencyFormat.format(position.entryPrice),
              ),
              _buildInfoItem(
                context,
                '当前价',
                currencyFormat.format(position.currentPrice),
              ),
              _buildInfoItem(
                context,
                '收益率',
                '${position.pnlPercent >= 0 ? '+' : ''}${position.pnlPercent.toStringAsFixed(2)}%',
                valueColor: position.isProfit ? Colors.green : Colors.red,
              ),
            ],
          ),

          const SizedBox(height: 14),

          // 操作按钮
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () {
                    // TODO: 设置止盈止损
                  },
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    side: const BorderSide(color: Color(0xFF374151)),
                  ),
                  child: const Text(
                    '止盈止损',
                    style: TextStyle(
                      color: Colors.white70,
                      fontSize: 13,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: ElevatedButton(
                  onPressed: () {
                    // TODO: 平仓
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFFEF4444),
                    padding: const EdgeInsets.symmetric(vertical: 10),
                  ),
                  child: const Text(
                    '平仓',
                    style: TextStyle(
                      fontSize: 13,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildInfoItem(
    BuildContext context,
    String label,
    String value, {
    Color? valueColor,
  }) {
    return Expanded(
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
              color: valueColor ?? Colors.white,
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }

  String _getCoinSymbol(String symbol) {
    switch (symbol.toUpperCase()) {
      case 'BTC':
        return '₿';
      case 'ETH':
        return 'Ξ';
      case 'SOL':
        return '◎';
      case 'BNB':
        return '◈';
      case 'DOGE':
        return 'Ð';
      default:
        return symbol.substring(0, symbol.length > 2 ? 2 : symbol.length);
    }
  }

  Color _getCoinColor(String symbol) {
    switch (symbol.toUpperCase()) {
      case 'BTC':
        return const Color(0xFFF7931A);
      case 'ETH':
        return const Color(0xFF627EEA);
      case 'SOL':
        return const Color(0xFF9945FF);
      case 'BNB':
        return const Color(0xFFF0B90B);
      case 'DOGE':
        return const Color(0xFFC2A633);
      default:
        return Colors.grey;
    }
  }
}
