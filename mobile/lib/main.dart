import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme/app_theme.dart';
import 'core/router/app_router.dart';
import 'core/providers/auth_provider.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProviderScope(child: CryptoQuantApp()));
}

class CryptoQuantApp extends ConsumerStatefulWidget {
  const CryptoQuantApp({super.key});

  @override
  ConsumerState<CryptoQuantApp> createState() => _CryptoQuantAppState();
}

class _CryptoQuantAppState extends ConsumerState<CryptoQuantApp> {
  @override
  void initState() {
    super.initState();
    // 启动时检查登录状态
    Future.microtask(() {
      ref.read(authProvider.notifier).checkAuthStatus();
    });
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);

    return MaterialApp.router(
      title: '币钱袋',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.darkTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.dark, // 交易 App 强制深色模式
      routerConfig: router,
    );
  }
}
