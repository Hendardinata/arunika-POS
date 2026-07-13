import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

final sharedPrefsProvider = Provider<SharedPreferences>((ref) {
  throw UnimplementedError('sharedPrefsProvider must be overridden in main.dart');
});

class AuthUser {
  final int id;
  final String username;
  final String role;
  final String token;

  AuthUser({
    required this.id,
    required this.username,
    required this.role,
    required this.token,
  });

  factory AuthUser.fromJson(Map<String, dynamic> json, String token) {
    return AuthUser(
      id: json['id'] ?? 0,
      username: json['username'] ?? '',
      role: json['role'] ?? 'CASHIER',
      token: token,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'username': username,
      'role': role,
    };
  }
}

class AuthNotifier extends Notifier<AuthUser?> {
  @override
  AuthUser? build() {
    final prefs = ref.read(sharedPrefsProvider);
    final token = prefs.getString('auth_token');
    final userJson = prefs.getString('auth_user');

    if (token != null && userJson != null) {
      try {
        final decoded = json.decode(userJson);
        return AuthUser.fromJson(decoded, token);
      } catch (e) {
        return null;
      }
    }
    return null;
  }

  void setUser(AuthUser user) {
    state = user;
    final prefs = ref.read(sharedPrefsProvider);
    prefs.setString('auth_token', user.token);
    prefs.setString('auth_user', json.encode(user.toJson()));
  }

  void logout() {
    state = null;
    final prefs = ref.read(sharedPrefsProvider);
    prefs.remove('auth_token');
    prefs.remove('auth_user');
  }
}

final authProvider = NotifierProvider<AuthNotifier, AuthUser?>(() {
  return AuthNotifier();
});
