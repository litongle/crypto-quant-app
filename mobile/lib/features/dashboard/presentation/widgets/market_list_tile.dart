import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../data/models/market_coin.dart';

/// 市场行情列表
class MarketListTile extends StatelessWidget {
  final List<MarketCoin> coins;
  final MarketPeriod period;

  const MarketListTile({
    super.key,
    required this.coins,
    this.period = MarketPeriod.h24,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Theme.of(context).dividerColor,
          width: 1,
        ),
      ),
      child: Column(
        children: coins.asMap().entries.map((entry) {
          final index = entry.key;
          final coin = entry.value;
          return _MarketCoinRow(
            coin: coin,
            period: period,
            isLast: index == coins.length - 1,
          );
        }).toList(),
      ),
    );
  }
}

class _MarketCoinRow extends StatelessWidget {
  final MarketCoin coin;
  final MarketPeriod period;
  final bool isLast;

  const _MarketCoinRow({
    required this.coin,
    required this.period,
    this.isLast = false,
  });

  @override
  Widget build(BuildContext context) {
    final priceFormat = NumberFormat.currency(symbol: '\$', decimalDigits: 2);
    final change = coin.changeForPeriod(period);
    final isPositive = change >= 0;

    return InkWell(
      onTap: () {
        // TODO: 跳转到币种详情
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          border: isLast
              ? null
              : Border(
                  bottom: BorderSide(
                    color: Theme.of(context).dividerColor,
                    width: 0.5,
                  ),
                ),
        ),
        child: Row(
          children: [
            // 币种图标和名称
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: _getCoinColor(coin.symbol).withOpacity(0.1),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Center(
                child: Text(
                  _getCoinSymbol(coin.symbol),
                  style: TextStyle(
                    color: _getCoinColor(coin.symbol),
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),

            // 币种信息
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    coin.symbol,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 15,
                    ),
                  ),
                  Text(
                    coin.name,
                    style: TextStyle(
                      color: Colors.grey[500],
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),

            // 价格
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  priceFormat.format(coin.price),
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 15,
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: isPositive
                        ? Colors.green.withOpacity(0.1)
                        : Colors.red.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    '${isPositive ? '+' : ''}${change.toStringAsFixed(2)}%',
                    style: TextStyle(
                      color: isPositive ? Colors.green : Colors.red,
                      fontWeight: FontWeight.w600,
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
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
