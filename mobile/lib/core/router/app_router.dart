import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/presentation/screens/login_page.dart';
import '../../features/auth/presentation/screens/register_page.dart';
import '../../features/dashboard/presentation/screens/dashboard_page.dart';
import '../../features/market/presentation/screens/coin_detail_page.dart';
import '../../features/settings/presentation/screens/settings_page.dart';
import '../../features/strategies/presentation/screens/strategy_center_page.dart';
import '../../features/backtest/presentation/screens/backtest_page.dart';
import '../providers/auth_provider.dart';

/// 全局导航 Key
final rootNavigatorKey = GlobalKey<NavigatorState>();
final shellNavigatorKey = GlobalKey<NavigatorState>();

/// 路由 Provider
final routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);

  return GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: '/dashboard',
    debugLogDiagnostics: true,
    routes: [
      // 币种详情（全屏，覆盖底部导航）
      GoRoute(
        path: '/market/:symbol',
        name: 'coinDetail',
        builder: (context, state) {
          final symbol = state.pathParameters['symbol']!;
          return CoinDetailPage(symbol: symbol);
        },
      ),

      // 认证相关（无需登录）
      GoRoute(
        path: '/login',
        name: 'login',
        builder: (context, state) => const LoginPage(),
      ),
      GoRoute(
        path: '/register',
        name: 'register',
        builder: (context, state) => const RegisterPage(),
      ),

      // 主 Shell（底部导航 - 需要登录）
      ShellRoute(
        navigatorKey: shellNavigatorKey,
        builder: (context, state, child) => MainShell(child: child),
        routes: [
          GoRoute(
            path: '/dashboard',
            name: 'dashboard',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: DashboardPage(),
            ),
          ),
          GoRoute(
            path: '/strategies',
            name: 'strategies',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: StrategyCenterPage(),
            ),
          ),
          GoRoute(
            path: '/backtest',
            name: 'backtest',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: BacktestPage(),
            ),
          ),
          GoRoute(
            path: '/settings',
            name: 'settings',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: SettingsPage(),
            ),
          ),
        ],
      ),
    ],
    redirect: (context, state) {
      final isAuthRoute = state.matchedLocation == '/login' ||
          state.matchedLocation == '/register';

      // 还在 loading，不做重定向
      if (authState.status == AuthStatus.loading) {
        return null;
      }

      // 已登录在登录页 -> 跳首页
      if (authState.status == AuthStatus.authenticated && isAuthRoute) {
        return '/dashboard';
      }

      // 未登录也不强制跳登录页，让用户自由浏览
      return null;
    },
  );
});

/// 主 Shell - 底部导航
class MainShell extends StatelessWidget {
  final Widget child;

  const MainShell({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _calculateSelectedIndex(context),
        onDestinationSelected: (index) => _onItemTapped(index, context),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: '首页',
          ),
          NavigationDestination(
            icon: Icon(Icons.analytics_outlined),
            selectedIcon: Icon(Icons.analytics),
            label: '策略',
          ),
          NavigationDestination(
            icon: Icon(Icons.history_outlined),
            selectedIcon: Icon(Icons.history),
            label: '回测',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: '我的',
          ),
        ],
      ),
    );
  }

  int _calculateSelectedIndex(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;
    if (location.startsWith('/dashboard')) return 0;
    if (location.startsWith('/strategies')) return 1;
    if (location.startsWith('/backtest')) return 2;
    if (location.startsWith('/settings')) return 3;
    return 0;
  }

  void _onItemTapped(int index, BuildContext context) {
    switch (index) {
      case 0:
        context.goNamed('dashboard');
        break;
      case 1:
        context.goNamed('strategies');
        break;
      case 2:
        context.goNamed('backtest');
        break;
      case 3:
        context.goNamed('settings');
        break;
    }
  }
}
