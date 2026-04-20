import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../constants/app_constants.dart';
import '../network/api_client.dart';

/// 认证状态
enum AuthStatus { initial, authenticated, unauthenticated, loading }

/// 是否已登录（便捷 getter 扩展）
extension AuthStatusX on AuthStatus {
  bool get isAuthenticated => this == AuthStatus.authenticated;
  bool get isUnauthenticated => this == AuthStatus.unauthenticated;
}

/// 用户信息
class User {
  final int id;
  final String email;
  final String name;
  final String riskLevel;
  final String status;

  const User({
    required this.id,
    required this.email,
    required this.name,
    required this.riskLevel,
    required this.status,
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] as int,
      email: json['email'] as String,
      name: json['name'] as String,
      riskLevel: json['risk_level'] ?? 'medium',
      status: json['status'] ?? 'active',
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'email': email,
        'name': name,
        'risk_level': riskLevel,
        'status': status,
      };
}

/// 认证状态模型
class AuthState {
  final AuthStatus status;
  final User? user;
  final String? error;

  const AuthState({
    this.status = AuthStatus.initial,
    this.user,
    this.error,
  });

  AuthState copyWith({
    AuthStatus? status,
    User? user,
    String? error,
  }) {
    return AuthState(
      status: status ?? this.status,
      user: user ?? this.user,
      error: error,
    );
  }
}

/// 认证 Provider
final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return AuthNotifier(apiClient);
});

class AuthNotifier extends StateNotifier<AuthState> {
  final ApiClient _apiClient;

  AuthNotifier(this._apiClient) : super(const AuthState());

  /// 检查登录状态（启动时调用）
  Future<void> checkAuthStatus() async {
    state = state.copyWith(status: AuthStatus.loading);
    try {
      final isLoggedIn = await _apiClient.isLoggedIn();
      if (isLoggedIn) {
        await _fetchCurrentUser();
      } else {
        // 未登录是正常状态，不要阻塞页面
        state = state.copyWith(status: AuthStatus.unauthenticated);
      }
    } catch (e) {
      // 检查失败也不阻塞，当作未登录处理
      state = state.copyWith(status: AuthStatus.unauthenticated);
    }
  }

  /// 登录
  Future<bool> login({
    required String email,
    required String password,
  }) async {
    state = state.copyWith(status: AuthStatus.loading, error: null);
    try {
      // 后端使用 OAuth2PasswordRequestForm，需要 form-data
      final response = await _apiClient.post(
        '${ApiConstants.auth}/login',
        data: FormData.fromMap({
          'username': email, // OAuth2 规范用 username 存 email
          'password': password,
        }),
        options: Options(
          contentType: 'application/x-www-form-urlencoded',
        ),
      );

      final data = response.data;
      if (data['access_token'] != null) {
        await _apiClient.saveTokens(
          accessToken: data['access_token'],
          refreshToken: data['refresh_token'],
        );
        final user = User(
          id: data['user']['id'],
          email: data['user']['email'],
          name: data['user']['name'],
          riskLevel: data['user']['risk_level'] ?? 'medium',
          status: data['user']['status'] ?? 'active',
        );
        state = state.copyWith(status: AuthStatus.authenticated, user: user);
        return true;
      } else {
        state = state.copyWith(
          status: AuthStatus.unauthenticated,
          error: '登录失败',
        );
        return false;
      }
    } on DioException catch (e) {
      String msg = '网络错误';
      if (e.response?.data != null) {
        final detail = e.response!.data['detail'] ?? e.response!.data['message'];
        if (detail != null) msg = detail.toString();
      }
      state = state.copyWith(
        status: AuthStatus.unauthenticated,
        error: msg,
      );
      return false;
    } catch (e) {
      state = state.copyWith(
        status: AuthStatus.unauthenticated,
        error: '登录失败: $e',
      );
      return false;
    }
  }

  /// 注册
  Future<bool> register({
    required String email,
    required String password,
    required String name,
  }) async {
    state = state.copyWith(status: AuthStatus.loading, error: null);
    try {
      final response = await _apiClient.post(
        '${ApiConstants.auth}/register',
        data: {
          'email': email,
          'password': password,
          'name': name,
        },
      );

      final data = response.data;
      if (data['access_token'] != null) {
        await _apiClient.saveTokens(
          accessToken: data['access_token'],
          refreshToken: data['refresh_token'],
        );
        final user = User(
          id: data['user']['id'],
          email: data['user']['email'],
          name: data['user']['name'],
          riskLevel: data['user']['risk_level'] ?? 'medium',
          status: data['user']['status'] ?? 'active',
        );
        state = state.copyWith(status: AuthStatus.authenticated, user: user);
        return true;
      } else {
        state = state.copyWith(
          status: AuthStatus.unauthenticated,
          error: '注册失败',
        );
        return false;
      }
    } on DioException catch (e) {
      String msg = '网络错误';
      if (e.response?.data != null) {
        final detail = e.response!.data['detail'] ?? e.response!.data['message'];
        if (detail != null) msg = detail.toString();
      }
      state = state.copyWith(
        status: AuthStatus.unauthenticated,
        error: msg,
      );
      return false;
    } catch (e) {
      state = state.copyWith(
        status: AuthStatus.unauthenticated,
        error: '注册失败: $e',
      );
      return false;
    }
  }

  /// 获取当前用户信息
  Future<void> _fetchCurrentUser() async {
    try {
      final response = await _apiClient.get('${ApiConstants.auth}/me');
      final data = response.data;
      final user = User.fromJson(data);
      state = state.copyWith(status: AuthStatus.authenticated, user: user);
    } catch (e) {
      // Token 失效，清除并登出
      await logout();
    }
  }

  /// 登出
  Future<void> logout() async {
    await _apiClient.clearTokens();
    state = const AuthState(status: AuthStatus.unauthenticated);
  }
}
