import 'package:flutter_riverpod/flutter_riverpod.dart';

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
}

class AuthNotifier extends Notifier<AuthUser?> {
  @override
  AuthUser? build() {
    return null;
  }

  void setUser(AuthUser user) {
    state = user;
  }

  void logout() {
    state = null;
  }
}

final authProvider = NotifierProvider<AuthNotifier, AuthUser?>(() {
  return AuthNotifier();
});
