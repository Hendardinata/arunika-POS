import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import '../models/shift.dart';
import 'auth_provider.dart';

const String apiUrl = 'http://127.0.0.1:3001/api';

class ShiftNotifier extends Notifier<AsyncValue<Shift?>> {
  @override
  AsyncValue<Shift?> build() {
    // Initial fetch when provider is created
    fetchCurrentShift();
    return const AsyncValue.loading();
  }

  Future<void> fetchCurrentShift() async {
    state = const AsyncValue.loading();
    try {
      final user = ref.read(authProvider);
      if (user == null) {
        state = const AsyncValue.data(null);
        return;
      }

      final response = await http.get(
        Uri.parse('$apiUrl/shift/current'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ${user.token}',
        },
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        if (data['currentShift'] != null) {
          state = AsyncValue.data(Shift.fromJson(data['currentShift']));
        } else {
          state = const AsyncValue.data(null);
        }
      } else {
        state = AsyncValue.error('Failed to fetch current shift', StackTrace.current);
      }
    } catch (e, st) {
      state = AsyncValue.error(e, st);
    }
  }

  Future<void> openShift(int startingCash) async {
    try {
      final user = ref.read(authProvider);
      if (user == null) return;

      final response = await http.post(
        Uri.parse('$apiUrl/shift/open'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ${user.token}',
        },
        body: json.encode({'startingCash': startingCash}),
      );

      if (response.statusCode == 201) {
        final data = json.decode(response.body);
        state = AsyncValue.data(Shift.fromJson(data));
      } else {
        throw Exception('Failed to open shift: ${response.body}');
      }
    } catch (e) {
      rethrow;
    }
  }

  Future<void> closeShift(int endingCash) async {
    try {
      final user = ref.read(authProvider);
      if (user == null) return;

      final response = await http.post(
        Uri.parse('$apiUrl/shift/close'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ${user.token}',
        },
        body: json.encode({'endingCash': endingCash}),
      );

      if (response.statusCode == 200) {
        // Shift closed successfully
        state = const AsyncValue.data(null);
      } else {
        throw Exception('Failed to close shift: ${response.body}');
      }
    } catch (e) {
      rethrow;
    }
  }
}

final shiftProvider = NotifierProvider<ShiftNotifier, AsyncValue<Shift?>>(() {
  return ShiftNotifier();
});
