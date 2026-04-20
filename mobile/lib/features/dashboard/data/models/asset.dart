import 'package:equatable/equatable.dart';

/// 账户资产数据模型
class Asset extends Equatable {
  final double totalAsset;       // 总资产 (USDT)
  final double totalPnL;         // 总收益
  final double totalPnLPercent; // 总收益率 (%)
  final double availableBalance; // 可用余额
  final double lockedBalance;    // 冻结金额
  final String updateTime;      // 更新时间

  const Asset({
    required this.totalAsset,
    required this.totalPnL,
    required this.totalPnLPercent,
    required this.availableBalance,
    required this.lockedBalance,
    required this.updateTime,
  });

  bool get isProfit => totalPnL >= 0;

  /// 从 API 响应解析
  factory Asset.fromJson(Map<String, dynamic> json) {
    return Asset(
      totalAsset: (json['total_asset'] ?? 0).toDouble(),
      totalPnL: (json['total_pnl'] ?? 0).toDouble(),
      totalPnLPercent: (json['total_pnl_percent'] ?? 0).toDouble(),
      availableBalance: (json['available_balance'] ?? 0).toDouble(),
      lockedBalance: (json['locked_balance'] ?? 0).toDouble(),
      updateTime: json['update_time'] ?? '',
    );
  }

  /// 模拟数据
  static Asset mock() {
    return const Asset(
      totalAsset: 125840.52,
      totalPnL: 12540.52,
      totalPnLPercent: 11.06,
      availableBalance: 98500.00,
      lockedBalance: 27340.52,
      updateTime: '02:01:30',
    );
  }

  @override
  List<Object?> get props => [
        totalAsset,
        totalPnL,
        totalPnLPercent,
        availableBalance,
        lockedBalance,
        updateTime,
      ];
}
