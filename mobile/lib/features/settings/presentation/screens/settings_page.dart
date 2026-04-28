import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/providers/auth_provider.dart';

/// 交易所连接模型
class ExchangeConnection {
  final String id;
  final String name;
  final String status;
  final String? apiKey;
  final DateTime? lastSync;

  const ExchangeConnection({
    required this.id,
    required this.name,
    required this.status,
    this.apiKey,
    this.lastSync,
  });
}

/// 设置项 Provider
final notificationsEnabledProvider = StateProvider<bool>((ref) => true);
final autoFollowEnabledProvider = StateProvider<bool>((ref) => false);
final riskLimitProvider = StateProvider<double>((ref) => 5000);

/// 交易所连接列表 StateNotifier
class ExchangeConnectionsNotifier extends StateNotifier<List<ExchangeConnection>> {
  ExchangeConnectionsNotifier()
      : super(const [
          ExchangeConnection(id: 'Binance', name: 'Binance', status: 'disconnected'),
          ExchangeConnection(id: 'OKX', name: 'OKX', status: 'disconnected'),
        ]);

  void connect(String id, String name, String apiKey) {
    final maskedKey = apiKey.length >= 4
        ? '****${apiKey.substring(apiKey.length - 4)}'
        : '****';
    final updated = ExchangeConnection(
      id: id,
      name: name,
      status: 'connected',
      apiKey: maskedKey,
      lastSync: DateTime.now(),
    );
    if (state.any((c) => c.id == id)) {
      state = [for (final c in state) if (c.id == id) updated else c];
    } else {
      state = [...state, updated];
    }
  }

  void disconnect(String id) {
    state = [
      for (final c in state)
        if (c.id == id)
          ExchangeConnection(id: c.id, name: c.name, status: 'disconnected')
        else
          c,
    ];
  }
}

/// 交易所连接列表 Provider
final exchangeConnectionsProvider =
    StateNotifierProvider<ExchangeConnectionsNotifier, List<ExchangeConnection>>(
  (ref) => ExchangeConnectionsNotifier(),
);

void _showApiKeyInputDialog(
  BuildContext context,
  WidgetRef ref,
  String exchangeId,
  String exchangeName,
) {
  final apiKeyController = TextEditingController();
  final apiSecretController = TextEditingController();

  showDialog<void>(
    context: context,
    builder: (dialogContext) {
      return AlertDialog(
        title: Text('连接 $exchangeName'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: apiKeyController,
              decoration: const InputDecoration(
                labelText: 'API Key',
                hintText: '请输入 API Key',
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: apiSecretController,
              decoration: const InputDecoration(
                labelText: 'API Secret',
                hintText: '请输入 API Secret',
              ),
              obscureText: true,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('取消'),
          ),
          ElevatedButton(
            onPressed: () {
              final apiKey = apiKeyController.text.trim();
              final apiSecret = apiSecretController.text.trim();
              if (apiKey.isEmpty || apiSecret.isEmpty) return;
              ref.read(exchangeConnectionsProvider.notifier).connect(
                    exchangeId,
                    exchangeName,
                    apiKey,
                  );
              Navigator.pop(dialogContext);
            },
            child: const Text('连接'),
          ),
        ],
      );
    },
  ).then((_) {
    apiKeyController.dispose();
    apiSecretController.dispose();
  });
}



class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notificationsEnabled = ref.watch(notificationsEnabledProvider);
    final autoFollowEnabled = ref.watch(autoFollowEnabledProvider);
    final riskLimit = ref.watch(riskLimitProvider);
    final connections = ref.watch(exchangeConnectionsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('我的'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // 用户信息卡片
          _buildUserCard(context),
          const SizedBox(height: 24),

          // 交易所连接
          _buildSectionTitle(context, '交易所连接'),
          const SizedBox(height: 12),
          Column(
            children: connections
                .map((conn) => _ExchangeCard(connection: conn))
                .toList(),
          ),
          const SizedBox(height: 8),
          _buildAddExchangeButton(context),

          const SizedBox(height: 24),

          // 通知设置
          _buildSectionTitle(context, '通知设置'),
          const SizedBox(height: 12),
          _SettingsTile(
            icon: Icons.notifications_outlined,
            title: '信号推送通知',
            subtitle: '收到买卖信号时推送提醒',
            trailing: Switch(
              value: notificationsEnabled,
              onChanged: (value) {
                ref.read(notificationsEnabledProvider.notifier).state = value;
              },
              activeColor: const Color(0xFF22D3EE),
            ),
          ),
          _SettingsTile(
            icon: Icons.auto_awesome,
            title: 'AI 自动跟单',
            subtitle: '收到信号后自动跟随下单',
            trailing: Switch(
              value: autoFollowEnabled,
              onChanged: (value) {
                ref.read(autoFollowEnabledProvider.notifier).state = value;
              },
              activeColor: const Color(0xFF22D3EE),
            ),
          ),

          const SizedBox(height: 24),

          // 风险控制
          _buildSectionTitle(context, '风险控制'),
          const SizedBox(height: 12),
          _buildRiskLimitCard(context, ref, riskLimit),

          const SizedBox(height: 24),

          // 其他设置
          _buildSectionTitle(context, '其他'),
          const SizedBox(height: 12),
          _SettingsTile(
            icon: Icons.history,
            title: '交易记录',
            subtitle: '查看历史交易明细',
            onTap: () {},
          ),
          _SettingsTile(
            icon: Icons.analytics_outlined,
            title: '账户分析',
            subtitle: '收益统计与报告',
            onTap: () {},
          ),
          _SettingsTile(
            icon: Icons.help_outline,
            title: '帮助与反馈',
            subtitle: '常见问题与联系客服',
            onTap: () {},
          ),
          _SettingsTile(
            icon: Icons.info_outline,
            title: '关于币钱袋',
            subtitle: '版本 1.0.0',
            onTap: () {},
          ),

          const SizedBox(height: 24),

          // 登录/退出按钮
          if (ref.watch(authProvider).status == AuthStatus.authenticated)
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () => _showLogoutDialog(context),
                icon: const Icon(Icons.logout, color: Colors.red),
                label: const Text('退出登录', style: TextStyle(color: Colors.red)),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  side: const BorderSide(color: Colors.red),
                ),
              ),
            )
          else
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: () => context.goNamed('login'),
                icon: const Icon(Icons.login),
                label: const Text('登录 / 注册'),
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  backgroundColor: const Color(0xFF06B6D4),
                ),
              ),
            ),

          const SizedBox(height: 100),
        ],
      ),
    );
  }

  Widget _buildUserCard(BuildContext context) {
    final authState = ref.watch(authProvider);
    final isLoggedIn = authState.status == AuthStatus.authenticated;
    final user = authState.user;

    return GestureDetector(
      onTap: () {
        if (!isLoggedIn) {
          context.goNamed('login');
        }
      },
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF0f1a2e), Color(0xFF111827)],
          ),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: const Color(0xFF1f2937)),
        ),
        child: Row(
          children: [
            Container(
              width: 60,
              height: 60,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: isLoggedIn
                      ? [const Color(0xFF06B6D4), const Color(0xFF3B82F6)]
                      : [Colors.grey[700]!, Colors.grey[600]!],
                ),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Icon(
                isLoggedIn ? Icons.person : Icons.login,
                color: Colors.white,
                size: 32,
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isLoggedIn ? (user?.name ?? '用户') : '点击登录',
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    isLoggedIn ? (user?.email ?? '') : '登录后解锁完整功能',
                    style: const TextStyle(
                      color: Colors.grey,
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
            if (isLoggedIn)
              IconButton(
                onPressed: () {},
                icon: const Icon(Icons.edit_outlined),
                color: Colors.grey,
              )
            else
              const Icon(Icons.chevron_right, color: Colors.grey),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionTitle(BuildContext context, String title) {
    return Text(
      title,
      style: Theme.of(context).textTheme.titleMedium?.copyWith(
        fontWeight: FontWeight.bold,
      ),
    );
  }

  Widget _buildAddExchangeButton(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: () => _showAddExchangeSheet(context),
      icon: const Icon(Icons.add),
      label: const Text('添加交易所'),
      style: OutlinedButton.styleFrom(
        padding: const EdgeInsets.symmetric(vertical: 12),
        side: BorderSide(color: Colors.grey[700]!),
      ),
    );
  }

  Widget _buildRiskLimitCard(BuildContext context, WidgetRef ref, double riskLimit) {
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
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Row(
                children: [
                  Icon(Icons.shield_outlined, color: Color(0xFFEF4444)),
                  SizedBox(width: 10),
                  Text(
                    '单日最大亏损',
                    style: TextStyle(fontWeight: FontWeight.w600),
                  ),
                ],
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: const Color(0xFFEF4444).withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  '\$${riskLimit.toInt()}',
                  style: const TextStyle(
                    color: Color(0xFFEF4444),
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: const Color(0xFFEF4444),
              inactiveTrackColor: const Color(0xFF1F2937),
              thumbColor: const Color(0xFFEF4444),
              overlayColor: const Color(0xFFEF4444).withOpacity(0.2),
            ),
            child: Slider(
              value: riskLimit,
              min: 100,
              max: 10000,
              divisions: 99,
              onChanged: (value) {
                ref.read(riskLimitProvider.notifier).state = value;
              },
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '\$100',
                style: TextStyle(color: Colors.grey[500], fontSize: 11),
              ),
              Text(
                '\$10,000',
                style: TextStyle(color: Colors.grey[500], fontSize: 11),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '当单日亏损达到此金额时，系统将自动暂停所有策略',
            style: TextStyle(color: Colors.grey[500], fontSize: 11),
          ),
        ],
      ),
    );
  }

  void _showAddExchangeSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) {
        return Container(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '添加交易所',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 18,
                ),
              ),
              const SizedBox(height: 20),
              _buildExchangeOption(context, 'Binance', '币安', Icons.currency_exchange),
              const SizedBox(height: 12),
              _buildExchangeOption(context, 'OKX', '欧易', Icons.currency_exchange),
              const SizedBox(height: 12),
              _buildExchangeOption(context, 'Huobi', '火币', Icons.currency_exchange),
              const SizedBox(height: 24),
            ],
          ),
        );
      },
    );
  }

  Widget _buildExchangeOption(
    BuildContext context,
    String id,
    String name,
    IconData icon,
  ) {
    return InkWell(
      onTap: () {
        Navigator.pop(context);
        _showApiKeyInputDialog(context, ref, id, name);
      },
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Theme.of(context).cardColor,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Theme.of(context).dividerColor),
        ),
        child: Row(
          children: [
            Icon(icon, color: const Color(0xFFF0B90B)),
            const SizedBox(width: 12),
            Text(
              name,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            const Spacer(),
            const Icon(Icons.chevron_right, color: Colors.grey),
          ],
        ),
      ),
    );
  }

  void _showLogoutDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('退出登录'),
          content: const Text('确定要退出当前账号吗？'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('取消'),
            ),
            ElevatedButton(
              onPressed: () async {
                Navigator.pop(context);
                await ref.read(authProvider.notifier).logout();
                if (context.mounted) {
                  context.goNamed('login');
                }
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.red,
              ),
              child: const Text('确定'),
            ),
          ],
        );
      },
    );
  }
}

class _ExchangeCard extends ConsumerWidget {
  final ExchangeConnection connection;

  const _ExchangeCard({required this.connection});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isConnected = connection.status == 'connected';

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Theme.of(context).dividerColor),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: const Color(0xFFF0B90B).withOpacity(0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Center(
              child: Text(
                '₿',
                style: TextStyle(
                  color: Color(0xFFF0B90B),
                  fontWeight: FontWeight.bold,
                  fontSize: 20,
                ),
              ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  connection.name,
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                  ),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: isConnected
                            ? Colors.green.withOpacity(0.1)
                            : Colors.grey.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        isConnected ? '已连接' : '未连接',
                        style: TextStyle(
                          color: isConnected ? Colors.green : Colors.grey,
                          fontSize: 11,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                    if (connection.apiKey != null) ...[
                      const SizedBox(width: 8),
                      Text(
                        connection.apiKey!,
                        style: TextStyle(
                          color: Colors.grey[500],
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
          if (isConnected)
            IconButton(
              onPressed: () {
                ref
                    .read(exchangeConnectionsProvider.notifier)
                    .disconnect(connection.id);
              },
              icon: const Icon(Icons.link_off, color: Colors.red),
            )
          else
            IconButton(
              onPressed: () {
                _showApiKeyInputDialog(
                    context, ref, connection.id, connection.name);
              },
              icon: const Icon(Icons.add_link, color: Colors.green),
            ),
        ],
      ),
    );
  }
}

class _SettingsTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final Widget? trailing;
  final VoidCallback? onTap;

  const _SettingsTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.trailing,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      onTap: onTap,
      contentPadding: const EdgeInsets.symmetric(horizontal: 0, vertical: 4),
      leading: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: const Color(0xFF22D3EE).withOpacity(0.1),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Icon(icon, color: const Color(0xFF22D3EE)),
      ),
      title: Text(
        title,
        style: const TextStyle(fontWeight: FontWeight.w600),
      ),
      subtitle: Text(
        subtitle,
        style: TextStyle(
          color: Colors.grey[500],
          fontSize: 12,
        ),
      ),
      trailing: trailing ??
          const Icon(Icons.chevron_right, color: Colors.grey),
    );
  }
}
