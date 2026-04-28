import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../../../core/services/market_service.dart';
import '../widgets/candlestick_chart.dart';

class CoinDetailPage extends ConsumerStatefulWidget {
  final String symbol;

  const CoinDetailPage({super.key, required this.symbol});

  @override
  ConsumerState<CoinDetailPage> createState() => _CoinDetailPageState();
}

class _CoinDetailPageState extends ConsumerState<CoinDetailPage> {
  String _interval = '1h';

  static const _intervals = ['1m', '5m', '15m', '1h', '4h', '1d'];

  static const _basePrices = {
    'BTC': 67000.0,
    'ETH': 3400.0,
    'SOL': 180.0,
    'BNB': 598.0,
    'DOGE': 0.123,
  };

  @override
  Widget build(BuildContext context) {
    final apiSymbol = '${widget.symbol}USDT';
    final params = (symbol: apiSymbol, interval: _interval);
    final klineAsync = ref.watch(klineProvider(params));

    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.symbol} / USDT'),
        centerTitle: false,
      ),
      body: klineAsync.when(
        data: (klines) =>
            klines.isEmpty ? _buildBody(_mockKlines()) : _buildBody(klines),
        loading: () => _buildBody(_mockKlines()),
        error: (_, __) => _buildBody(_mockKlines()),
      ),
    );
  }

  Widget _buildBody(List<Kline> klines) {
    final latest = klines.isNotEmpty ? klines.last : null;
    final oldest = klines.isNotEmpty ? klines.first : null;
    final periodChange = latest != null && oldest != null
        ? (latest.close - oldest.open) / oldest.open * 100
        : 0.0;
    final isUp = periodChange >= 0;

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // --- Price header ---
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  latest != null ? _fmtPriceLarge(latest.close) : '--',
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: (isUp ? Colors.green : Colors.red)
                            .withOpacity(0.12),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        '${isUp ? '+' : ''}${periodChange.toStringAsFixed(2)}%',
                        style: TextStyle(
                          color: isUp ? Colors.green : Colors.red,
                          fontWeight: FontWeight.w600,
                          fontSize: 13,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '周期涨跌',
                      style: TextStyle(color: Colors.grey[500], fontSize: 12),
                    ),
                  ],
                ),
              ],
            ),
          ),

          const SizedBox(height: 12),

          // --- Interval selector ---
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(
              children: _intervals.map((iv) {
                final selected = iv == _interval;
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: GestureDetector(
                    onTap: () => setState(() => _interval = iv),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 180),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 6),
                      decoration: BoxDecoration(
                        color: selected
                            ? const Color(0xFF06B6D4)
                            : Theme.of(context).cardColor,
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: selected
                              ? const Color(0xFF06B6D4)
                              : Theme.of(context).dividerColor,
                        ),
                      ),
                      child: Text(
                        iv.toUpperCase(),
                        style: TextStyle(
                          color: selected ? Colors.white : Colors.grey[500],
                          fontWeight: selected
                              ? FontWeight.w600
                              : FontWeight.normal,
                          fontSize: 12,
                        ),
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
          ),

          const SizedBox(height: 8),

          // --- K-line chart ---
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: CandlestickChart(candles: klines, height: 300),
          ),

          const SizedBox(height: 16),

          // --- OHLCV row ---
          if (latest != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: _buildOhlcvCard(latest),
            ),

          const SizedBox(height: 12),

          // --- High / Low / Volume ---
          if (klines.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: _buildStatsRow(klines),
            ),

          const SizedBox(height: 80),
        ],
      ),
    );
  }

  Widget _buildOhlcvCard(Kline c) {
    final changeColor = c.isBullish ? Colors.green : Colors.red;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Theme.of(context).dividerColor),
      ),
      child: Row(
        children: [
          _ohlcItem('开', c.open),
          _ohlcItem('高', c.high, color: Colors.green),
          _ohlcItem('低', c.low, color: Colors.red),
          _ohlcItem('收', c.close, color: changeColor, bold: true),
        ],
      ),
    );
  }

  Widget _ohlcItem(String label, double price,
      {Color? color, bool bold = false}) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: TextStyle(color: Colors.grey[500], fontSize: 11)),
          const SizedBox(height: 4),
          Text(
            _fmtPriceLarge(price),
            style: TextStyle(
              color: color,
              fontWeight: bold ? FontWeight.w600 : FontWeight.normal,
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatsRow(List<Kline> klines) {
    final highs = klines.map((c) => c.high);
    final lows = klines.map((c) => c.low);
    final vol = klines.fold(0.0, (sum, c) => sum + c.volume);
    final high = highs.reduce(math.max);
    final low = lows.reduce(math.min);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Theme.of(context).dividerColor),
      ),
      child: Row(
        children: [
          _statItem('区间最高', _fmtPriceLarge(high), Colors.green),
          _statItem('区间最低', _fmtPriceLarge(low), Colors.red),
          _statItem('区间成交量', _fmtVolume(vol), null),
        ],
      ),
    );
  }

  Widget _statItem(String label, String value, Color? color) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: TextStyle(color: Colors.grey[500], fontSize: 11)),
          const SizedBox(height: 4),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }

  // --- Helpers ---

  String _fmtPriceLarge(double p) {
    if (p >= 10000) return NumberFormat('#,##0.00').format(p);
    if (p >= 100) return p.toStringAsFixed(2);
    if (p >= 1) return p.toStringAsFixed(3);
    return p.toStringAsFixed(5);
  }

  String _fmtVolume(double v) {
    if (v >= 1e9) return '${(v / 1e9).toStringAsFixed(2)}B';
    if (v >= 1e6) return '${(v / 1e6).toStringAsFixed(2)}M';
    if (v >= 1e3) return '${(v / 1e3).toStringAsFixed(1)}K';
    return v.toStringAsFixed(0);
  }

  // --- Mock data (fallback when API unavailable) ---

  List<Kline> _mockKlines() {
    final base = _basePrices[widget.symbol] ?? 100.0;
    final intervalMins = const {
      '1m': 1,
      '5m': 5,
      '15m': 15,
      '1h': 60,
      '4h': 240,
      '1d': 1440,
    }[_interval] ?? 60;

    const count = 120;
    final now = DateTime.now();
    final rng = math.Random(widget.symbol.hashCode ^ intervalMins);
    final klines = <Kline>[];
    double price = base * 0.90;

    for (int i = count - 1; i >= 0; i--) {
      final t = now.subtract(Duration(minutes: i * intervalMins));
      final change = price * 0.022 * (rng.nextDouble() - 0.47);
      final open = price;
      final close = price + change;
      final wH = math.max(open, close) * (1 + rng.nextDouble() * 0.008);
      final wL = math.min(open, close) * (1 - rng.nextDouble() * 0.008);
      klines.add(Kline(
        openTime: t,
        open: open,
        high: wH,
        low: wL,
        close: close,
        volume: base * 80 * (0.4 + rng.nextDouble()),
        isBullish: close >= open,
      ));
      price = close;
    }
    return klines;
  }
}
