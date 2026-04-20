import 'package:flutter/material.dart';

/// 快捷信号/策略卡片
class QuickSignalCard extends StatelessWidget {
  final String signal;
  final double confidence;
  final bool isStrategy;

  const QuickSignalCard({
    super.key,
    required this.signal,
    required this.confidence,
    this.isStrategy = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: isStrategy
              ? [
                  const Color(0xFF0a0f1a),
                  const Color(0xFF111827),
                ]
              : [
                  const Color(0xFF001a0a),
                  const Color(0xFF111827),
                ],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isStrategy
              ? const Color(0xFF1e40af)
              : const Color(0xFF166534),
          width: 1,
        ),
      ),
      child: Column(
        children: [
          // 标签
          Text(
            isStrategy ? '策略运行' : '当前信号',
            style: TextStyle(
              color: Colors.grey[500],
              fontSize: 10,
            ),
          ),
          const SizedBox(height: 6),

          // 图标
          Text(
            isStrategy ? '⚡' : '📈',
            style: const TextStyle(fontSize: 28),
          ),
          const SizedBox(height: 4),

          // 信号/策略名称
          Text(
            signal,
            style: TextStyle(
              color: isStrategy
                  ? const Color(0xFF22D3EE)
                  : const Color(0xFF22C55E),
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 2),

          // 置信度或运行天数
          Text(
            isStrategy
                ? '已运行 $confidence 天'
                : '置信度 ${confidence.toInt()}%',
            style: TextStyle(
              color: Colors.grey[500],
              fontSize: 10,
            ),
          ),
        ],
      ),
    );
  }
}
