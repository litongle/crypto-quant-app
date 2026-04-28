import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../../../core/services/market_service.dart';

/// K 线图 Widget
class CandlestickChart extends StatefulWidget {
  final List<Kline> candles;
  final double height;

  const CandlestickChart({
    super.key,
    required this.candles,
    this.height = 300,
  });

  @override
  State<CandlestickChart> createState() => _CandlestickChartState();
}

class _CandlestickChartState extends State<CandlestickChart> {
  static const _candleW = 7.0;
  static const _gap = 2.5;
  static const _step = _candleW + _gap;
  static const _priceAxisW = 72.0;
  static const _timeAxisH = 22.0;

  double _scrollPx = 0.0;
  int? _selectedIdx;

  double get _maxScroll =>
      math.max(0.0, (widget.candles.length - 1) * _step);

  void _onDrag(double dx) {
    setState(() {
      _scrollPx = (_scrollPx - dx).clamp(0.0, _maxScroll);
      _selectedIdx = null;
    });
  }

  void _onTap(Offset pos, double chartW) {
    for (int i = 0; i < widget.candles.length; i++) {
      final x = _xOf(i, chartW);
      if ((pos.dx - x).abs() < _step / 2) {
        setState(() => _selectedIdx = _selectedIdx == i ? null : i);
        return;
      }
    }
    setState(() => _selectedIdx = null);
  }

  double _xOf(int i, double chartW) =>
      chartW - (widget.candles.length - 1 - i + 0.5) * _step + _scrollPx;

  @override
  Widget build(BuildContext context) {
    if (widget.candles.isEmpty) {
      return SizedBox(
        height: widget.height,
        child: Center(
          child: Text('暂无K线数据', style: TextStyle(color: Colors.grey[500])),
        ),
      );
    }

    final isDark = Theme.of(context).brightness == Brightness.dark;

    return LayoutBuilder(builder: (context, constraints) {
      final chartW = constraints.maxWidth - _priceAxisW;
      final chartH = widget.height - _timeAxisH;

      return GestureDetector(
        onHorizontalDragUpdate: (d) => _onDrag(d.delta.dx),
        onTapDown: (d) => _onTap(d.localPosition, chartW),
        child: SizedBox(
          height: widget.height,
          child: CustomPaint(
            painter: _CandlestickPainter(
              candles: widget.candles,
              scrollPx: _scrollPx,
              selectedIdx: _selectedIdx,
              isDark: isDark,
              chartW: chartW,
              chartH: chartH,
              priceAxisW: _priceAxisW,
              timeAxisH: _timeAxisH,
              candleW: _candleW,
              step: _step,
            ),
            child: const SizedBox.expand(),
          ),
        ),
      );
    });
  }
}

class _CandlestickPainter extends CustomPainter {
  final List<Kline> candles;
  final double scrollPx;
  final int? selectedIdx;
  final bool isDark;
  final double chartW;
  final double chartH;
  final double priceAxisW;
  final double timeAxisH;
  final double candleW;
  final double step;

  const _CandlestickPainter({
    required this.candles,
    required this.scrollPx,
    required this.selectedIdx,
    required this.isDark,
    required this.chartW,
    required this.chartH,
    required this.priceAxisW,
    required this.timeAxisH,
    required this.candleW,
    required this.step,
  });

  double _xOf(int i) =>
      chartW - (candles.length - 1 - i + 0.5) * step + scrollPx;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.clipRect(Rect.fromLTWH(0, 0, size.width, size.height));

    // --- Visible price range ---
    double minP = double.infinity;
    double maxP = double.negativeInfinity;
    for (int i = 0; i < candles.length; i++) {
      final x = _xOf(i);
      if (x + candleW < 0 || x - candleW > chartW) continue;
      if (candles[i].low < minP) minP = candles[i].low;
      if (candles[i].high > maxP) maxP = candles[i].high;
    }
    if (minP == double.infinity) {
      canvas.restore();
      return;
    }
    final pad = (maxP - minP) * 0.12;
    minP -= pad;
    maxP += pad;

    double pToY(double p) =>
        chartH * (1 - (p - minP) / (maxP - minP));

    final gridColor =
        isDark ? const Color(0xFF1F2937) : const Color(0xFFE5E7EB);
    final labelColor =
        isDark ? const Color(0xFF6B7280) : const Color(0xFF9CA3AF);

    // --- Horizontal grid lines & price labels ---
    const gridLines = 4;
    for (int g = 0; g <= gridLines; g++) {
      final y = chartH * g / gridLines;
      canvas.drawLine(
        Offset(0, y),
        Offset(chartW, y),
        Paint()
          ..color = gridColor
          ..strokeWidth = 0.5,
      );
      final price = maxP - (maxP - minP) * g / gridLines;
      _drawText(
        canvas,
        _fmtPrice(price),
        Offset(chartW + 4, y - 7),
        labelColor,
        10,
      );
    }

    // --- Vertical axis separator ---
    canvas.drawLine(
      Offset(chartW, 0),
      Offset(chartW, chartH),
      Paint()
        ..color = gridColor
        ..strokeWidth = 0.5,
    );

    // --- Candles ---
    const bullColor = Color(0xFF22C55E);
    const bearColor = Color(0xFFEF4444);

    for (int i = 0; i < candles.length; i++) {
      final x = _xOf(i);
      if (x + candleW < 0 || x - candleW > chartW) continue;

      final c = candles[i];
      final isSelected = i == selectedIdx;
      final color = c.isBullish ? bullColor : bearColor;

      final openY = pToY(c.open);
      final closeY = pToY(c.close);
      final highY = pToY(c.high);
      final lowY = pToY(c.low);

      // Wick
      canvas.drawLine(
        Offset(x, highY),
        Offset(x, lowY),
        Paint()
          ..color = color
          ..strokeWidth = 1.2,
      );

      // Body
      final bodyTop = math.min(openY, closeY);
      final bodyH = math.max((openY - closeY).abs(), 1.5);
      canvas.drawRect(
        Rect.fromLTWH(x - candleW / 2, bodyTop, candleW, bodyH),
        Paint()
          ..color = isSelected ? color.withOpacity(0.75) : color
          ..style = PaintingStyle.fill,
      );
    }

    // --- Crosshair + tooltip ---
    if (selectedIdx != null &&
        selectedIdx! >= 0 &&
        selectedIdx! < candles.length) {
      final c = candles[selectedIdx!];
      final x = _xOf(selectedIdx!);
      final midY = pToY((c.high + c.low) / 2);

      final xhPaint = Paint()
        ..color = labelColor.withOpacity(0.5)
        ..strokeWidth = 0.5;
      canvas.drawLine(Offset(x, 0), Offset(x, chartH), xhPaint);
      canvas.drawLine(Offset(0, midY), Offset(chartW, midY), xhPaint);

      _drawTooltip(canvas, c, x, midY);
    }

    // --- Time axis ---
    _drawTimeAxis(canvas, chartH, labelColor);

    canvas.restore();
  }

  void _drawTooltip(Canvas canvas, Kline c, double x, double midY) {
    final bgColor = isDark ? const Color(0xFF1F2937) : Colors.white;
    final borderColor =
        isDark ? const Color(0xFF374151) : const Color(0xFFD1D5DB);
    final textColor = isDark ? Colors.white : Colors.black87;
    const dimColor = Color(0xFF9CA3AF);

    const boxW = 136.0;
    const boxH = 100.0;
    const padH = 10.0;
    const padV = 8.0;
    const lineH = 17.0;

    double bx = x + 12;
    if (bx + boxW > chartW) bx = x - 12 - boxW;
    final by = (midY - boxH / 2).clamp(0.0, chartH - boxH);

    final rr = RRect.fromRectAndRadius(
      Rect.fromLTWH(bx, by, boxW, boxH),
      const Radius.circular(6),
    );
    canvas.drawRRect(rr, Paint()..color = bgColor);
    canvas.drawRRect(
      rr,
      Paint()
        ..color = borderColor
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.5,
    );

    final rows = [
      ('时间', DateFormat('MM-dd HH:mm').format(c.openTime)),
      ('开', _fmtPrice(c.open)),
      ('高', _fmtPrice(c.high)),
      ('低', _fmtPrice(c.low)),
      ('收', _fmtPrice(c.close)),
    ];

    for (int i = 0; i < rows.length; i++) {
      final (label, value) = rows[i];
      _drawText(canvas, label, Offset(bx + padH, by + padV + i * lineH),
          dimColor, 10.5);
      _drawText(
          canvas, value, Offset(bx + boxW / 2, by + padV + i * lineH),
          textColor, 10.5,
          bold: true);
    }
  }

  void _drawTimeAxis(Canvas canvas, double baseY, Color labelColor) {
    const minSpacingPx = 72.0;
    final skipEvery = math.max(1, (minSpacingPx / step).round());

    for (int i = 0; i < candles.length; i += skipEvery) {
      final x = _xOf(i);
      if (x < 8 || x > chartW - 8) continue;
      _drawText(
        canvas,
        _fmtTime(candles[i].openTime),
        Offset(x - 18, baseY + 4),
        labelColor,
        9,
      );
    }
  }

  void _drawText(
    Canvas canvas,
    String text,
    Offset offset,
    Color color,
    double fontSize, {
    bool bold = false,
  }) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          color: color,
          fontSize: fontSize,
          fontWeight: bold ? FontWeight.w600 : FontWeight.normal,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, offset);
  }

  String _fmtPrice(double p) {
    if (p >= 10000) return p.toStringAsFixed(0);
    if (p >= 100) return p.toStringAsFixed(1);
    if (p >= 1) return p.toStringAsFixed(2);
    return p.toStringAsFixed(4);
  }

  String _fmtTime(DateTime dt) => DateFormat('HH:mm').format(dt);

  @override
  bool shouldRepaint(_CandlestickPainter old) =>
      old.scrollPx != scrollPx ||
      old.selectedIdx != selectedIdx ||
      old.candles != candles;
}
