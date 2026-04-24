import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
/// 币钱袋 (CryptoQuant) — 统一设计令牌 v2.0
/// 基于 DESIGN_SYSTEM.md，Web + Mobile 跨平台一致
/// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AppColors {
  // ── 品牌主色 ──
  static const Color primary = Color(0xFF6366F1);       // Indigo 500
  static const Color primaryHover = Color(0xFF818CF8);  // Indigo 400
  static const Color primaryDark = Color(0xFF4F46E5);   // Indigo 600
  static const Color primaryMuted = Color(0x1F6366F1);  // 12% opacity
  static const Color primarySubtle = Color(0x0F6366F1); // 6% opacity

  // ── 语义色 ──
  static const Color profit = Color(0xFF10B981);          // Emerald 500
  static const Color profitMuted = Color(0x1F10B981);     // 12% opacity
  static const Color loss = Color(0xFFEF4444);            // Red 500
  static const Color lossMuted = Color(0x1FEF4444);       // 12% opacity
  static const Color warning = Color(0xFFF59E0B);         // Amber 500
  static const Color warningMuted = Color(0x1FF59E0B);    // 12% opacity
  static const Color info = Color(0xFF3B82F6);            // Blue 500
  static const Color infoMuted = Color(0x1F3B82F6);       // 12% opacity

  // ── 暗色模式表面层级 ──
  static const Color bgL0 = Color(0xFF0B0F1A);  // 页面背景（最深）
  static const Color bgL1 = Color(0xFF111827);  // 卡片、侧栏
  static const Color bgL2 = Color(0xFF1A2235);  // 输入框、深层嵌套
  static const Color bgL3 = Color(0xFF1F2937);  // 悬浮层、边框

  // ── 边框 ──
  static const Color borderDefault = Color(0xFF1F2937);
  static const Color borderHover = Color(0xFF374151);
  static const Color borderActive = Color(0xFF6366F1);

  // ── 文字 ──
  static const Color textPrimary = Color(0xFFF1F5F9);   // Slate 100
  static const Color textSecondary = Color(0xFF94A3B8);  // Slate 400
  static const Color textTertiary = Color(0xFF64748B);   // Slate 500
  static const Color textDisabled = Color(0xFF475569);   // Slate 600

  // ── 交易所品牌色 ──
  static const Color binance = Color(0xFFF0B90B);
  static const Color okx = Color(0xFFFFFFFF);
  static const Color htx = Color(0xFF2A6EDB);

  // ── 图表色 ──
  static const Color chartGreen = Color(0xFF10B981);
  static const Color chartRed = Color(0xFFEF4444);
  static const Color chartLine1 = Color(0xFF6366F1);  // Indigo
  static const Color chartLine2 = Color(0xFF14B8A6);  // Teal

  // ── 兼容旧代码 ──
  @Deprecated('Use primary instead')
  static const Color success = profit;
  @Deprecated('Use loss instead')
  static const Color error = loss;
  static const Color white = Color(0xFFFFFFFF);
  static const Color black = Color(0xFF000000);
  static const Color gray50 = Color(0xFFF8FAFC);
  static const Color gray100 = Color(0xFFF1F5F9);
  static const Color gray200 = Color(0xFFE2E8F0);
  static const Color gray300 = Color(0xFFCBD5E1);
  static const Color gray400 = Color(0xFF94A3B8);
  static const Color gray500 = Color(0xFF64748B);
  static const Color gray600 = Color(0xFF475569);
  static const Color gray700 = Color(0xFF334155);
  static const Color gray800 = Color(0xFF1E293B);
  static const Color gray900 = Color(0xFF0F172A);
  static const Color primaryLight = primaryHover;
  static const Color bitcoin = Color(0xFFF7931A);
  static const Color ethereum = Color(0xFF627EEA);
  static const Color solana = Color(0xFF9945FF);
}

/// ── 间距令牌 ──
class AppSpacing {
  static const double s1 = 4;
  static const double s2 = 8;
  static const double s3 = 12;
  static const double s4 = 16;
  static const double s5 = 20;
  static const double s6 = 24;
  static const double s8 = 32;
  static const double s10 = 40;
  static const double s12 = 48;
  static const double s16 = 64;
}

/// ── 圆角令牌 ──
class AppRadius {
  static const double sm = 4;
  static const double md = 6;
  static const double lg = 8;
  static const double xl = 12;
  static const double full = 9999;
}

/// ── 动效令牌 ──
class AppDuration {
  static const Duration fast = Duration(milliseconds: 150);
  static const Duration normal = Duration(milliseconds: 200);
  static const Duration slow = Duration(milliseconds: 300);
}

class AppTheme {
  // ━━━━━━━━ 亮色主题（暂未启用，预留） ━━━━━━━━
  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: ColorScheme.light(
        primary: AppColors.primary,
        secondary: AppColors.primaryHover,
        error: AppColors.loss,
        surface: AppColors.white,
        onPrimary: AppColors.white,
        onSecondary: AppColors.white,
        onSurface: AppColors.gray900,
        onError: AppColors.white,
      ),
      scaffoldBackgroundColor: AppColors.gray50,
      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.white,
        foregroundColor: AppColors.gray900,
        elevation: 0,
        centerTitle: true,
        systemOverlayStyle: SystemUiOverlayStyle.dark,
      ),
      cardTheme: CardThemeData(
        color: AppColors.white,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.lg),
          side: const BorderSide(color: AppColors.gray200),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: AppColors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.primary,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
          side: const BorderSide(color: AppColors.primary),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.gray100,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          borderSide: const BorderSide(color: AppColors.primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          borderSide: const BorderSide(color: AppColors.loss),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: AppColors.white,
        selectedItemColor: AppColors.primary,
        unselectedItemColor: AppColors.gray400,
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),
      dividerTheme: const DividerThemeData(
        color: AppColors.gray200,
        thickness: 1,
      ),
      textTheme: const TextTheme(
        displayLarge: TextStyle(fontSize: 28, fontWeight: FontWeight.w700, color: AppColors.gray900, letterSpacing: -0.02),
        displayMedium: TextStyle(fontSize: 24, fontWeight: FontWeight.w600, color: AppColors.gray900, letterSpacing: -0.02),
        headlineLarge: TextStyle(fontSize: 22, fontWeight: FontWeight.w600, color: AppColors.gray900, letterSpacing: -0.01),
        headlineMedium: TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: AppColors.gray900, letterSpacing: -0.01),
        titleLarge: TextStyle(fontSize: 16, fontWeight: FontWeight.w500, color: AppColors.gray900),
        titleMedium: TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: AppColors.gray900),
        bodyLarge: TextStyle(fontSize: 16, color: AppColors.gray700),
        bodyMedium: TextStyle(fontSize: 14, color: AppColors.gray600),
        bodySmall: TextStyle(fontSize: 12, color: AppColors.gray500),
        labelLarge: TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: AppColors.gray900),
        labelSmall: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.gray500, letterSpacing: 0.04),
      ),
    );
  }

  // ━━━━━━━━ 暗色主题（实际使用） ━━━━━━━━
  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: ColorScheme.dark(
        primary: AppColors.primary,            // Indigo — 统一主色
        secondary: AppColors.primaryHover,     // Indigo 400
        tertiary: AppColors.primaryDark,       // Indigo 600
        error: AppColors.loss,
        surface: AppColors.bgL1,
        onPrimary: AppColors.white,
        onSecondary: AppColors.white,
        onSurface: AppColors.textPrimary,
        onError: AppColors.white,
      ),
      scaffoldBackgroundColor: AppColors.bgL0,
      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.bgL0,
        foregroundColor: AppColors.textPrimary,
        elevation: 0,
        centerTitle: true,
        systemOverlayStyle: SystemUiOverlayStyle.light,
      ),
      cardTheme: CardThemeData(
        color: AppColors.bgL1,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.lg),  // 8px — 金融克制风
          side: const BorderSide(color: AppColors.borderDefault),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primary,       // Indigo
          foregroundColor: AppColors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.md),  // 6px
          ),
          textStyle: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w500,
            fontFamily: 'Inter',
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.textSecondary,
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.md),
          ),
          side: const BorderSide(color: AppColors.borderHover),
          textStyle: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AppColors.primaryHover,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.bgL2,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),  // 6px
          borderSide: const BorderSide(color: AppColors.borderDefault),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          borderSide: const BorderSide(color: AppColors.borderDefault),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          borderSide: const BorderSide(color: AppColors.primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          borderSide: const BorderSide(color: AppColors.loss),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.md),
          borderSide: const BorderSide(color: AppColors.loss, width: 2),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        labelStyle: const TextStyle(color: AppColors.textTertiary, fontSize: 12),
        hintStyle: const TextStyle(color: AppColors.textDisabled, fontSize: 13),
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: AppColors.bgL1,
        selectedItemColor: AppColors.primaryHover,   // Indigo 400
        unselectedItemColor: AppColors.textTertiary,
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: AppColors.bgL1,
        indicatorColor: AppColors.primaryMuted,
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return const TextStyle(
              color: AppColors.primaryHover,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            );
          }
          return const TextStyle(
            color: AppColors.textTertiary,
            fontSize: 12,
          );
        }),
        iconTheme: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return const IconThemeData(color: AppColors.primaryHover);
          }
          return const IconThemeData(color: AppColors.textTertiary);
        }),
      ),
      dividerTheme: const DividerThemeData(
        color: AppColors.borderDefault,
        thickness: 1,
      ),
      chipTheme: ChipThemeData(
        backgroundColor: AppColors.bgL2,
        selectedColor: AppColors.primaryMuted,
        labelStyle: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.sm),
        ),
      ),
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: AppColors.primary,
        foregroundColor: AppColors.white,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.lg),
        ),
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) return AppColors.primary;
          return AppColors.textTertiary;
        }),
        trackColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) return AppColors.primaryMuted;
          return AppColors.bgL3;
        }),
      ),
      textTheme: const TextTheme(
        // 大数值展示
        displayLarge: TextStyle(fontSize: 28, fontWeight: FontWeight.w700, color: AppColors.textPrimary, letterSpacing: -0.02),
        displayMedium: TextStyle(fontSize: 24, fontWeight: FontWeight.w600, color: AppColors.textPrimary, letterSpacing: -0.02),
        // 页面标题
        headlineLarge: TextStyle(fontSize: 22, fontWeight: FontWeight.w600, color: AppColors.textPrimary, letterSpacing: -0.02),
        headlineMedium: TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: AppColors.textPrimary, letterSpacing: -0.01),
        // 卡片标题
        titleLarge: TextStyle(fontSize: 16, fontWeight: FontWeight.w500, color: AppColors.textPrimary, letterSpacing: -0.01),
        // 导航、按钮
        titleMedium: TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: AppColors.textPrimary),
        // 正文
        bodyLarge: TextStyle(fontSize: 16, color: AppColors.textSecondary),
        bodyMedium: TextStyle(fontSize: 13, color: AppColors.textSecondary),
        // 辅助说明
        bodySmall: TextStyle(fontSize: 12, color: AppColors.textTertiary),
        // 按钮/标签文字
        labelLarge: TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: AppColors.textPrimary),
        // 徽章/标签
        labelSmall: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.textTertiary, letterSpacing: 0.04),
      ),
    );
  }
}
