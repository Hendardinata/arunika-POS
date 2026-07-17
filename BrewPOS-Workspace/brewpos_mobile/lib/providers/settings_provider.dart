import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

class SettingsState {
  final String storeName;
  final Color storeColor;
  final String? storeLogo; // Base64 string
  final String shiftMorningEnd;
  final String shiftNightEnd;
  final bool isLoading;

  SettingsState({
    required this.storeName,
    required this.storeColor,
    this.storeLogo,
    required this.shiftMorningEnd,
    required this.shiftNightEnd,
    this.isLoading = false,
  });

  SettingsState copyWith({
    String? storeName,
    Color? storeColor,
    String? storeLogo,
    String? shiftMorningEnd,
    String? shiftNightEnd,
    bool? isLoading,
  }) {
    return SettingsState(
      storeName: storeName ?? this.storeName,
      storeColor: storeColor ?? this.storeColor,
      storeLogo: storeLogo ?? this.storeLogo,
      shiftMorningEnd: shiftMorningEnd ?? this.shiftMorningEnd,
      shiftNightEnd: shiftNightEnd ?? this.shiftNightEnd,
      isLoading: isLoading ?? this.isLoading,
    );
  }
}

class SettingsNotifier extends Notifier<SettingsState> {
  @override
  SettingsState build() {
    _fetchSettings();
    return SettingsState(
      storeName: 'BrewPOS',
      storeColor: Colors.indigo,
      shiftMorningEnd: '15:00',
      shiftNightEnd: '23:00',
      isLoading: true,
    );
  }

  Color _parseColor(String hex) {
    hex = hex.replaceAll('#', '');
    if (hex.length == 6) {
      hex = 'FF$hex'; // Add alpha
    }
    return Color(int.parse(hex, radix: 16));
  }

  Future<void> _fetchSettings() async {
    try {
      final res = await http.get(Uri.parse('http://127.0.0.1:3001/api/settings'));
      if (res.statusCode == 200) {
        final List<dynamic> data = json.decode(res.body);
        
        String name = 'BrewPOS';
        Color color = Colors.indigo;
        String? logo;
        String morningEnd = '15:00';
        String nightEnd = '23:00';

        for (var item in data) {
          if (item['key'] == 'STORE_NAME') name = item['value'];
          if (item['key'] == 'STORE_COLOR') color = _parseColor(item['value']);
          if (item['key'] == 'STORE_LOGO' && item['value'].toString().isNotEmpty) {
            logo = item['value'];
          }
          if (item['key'] == 'SHIFT_MORNING_END') morningEnd = item['value'];
          if (item['key'] == 'SHIFT_NIGHT_END') nightEnd = item['value'];
        }

        state = state.copyWith(
          storeName: name,
          storeColor: color,
          storeLogo: logo,
          shiftMorningEnd: morningEnd,
          shiftNightEnd: nightEnd,
          isLoading: false,
        );
      } else {
        state = state.copyWith(isLoading: false);
      }
    } catch (e) {
      debugPrint('Error fetching settings: $e');
      state = state.copyWith(isLoading: false);
    }
  }

  void refresh() {
    state = state.copyWith(isLoading: true);
    _fetchSettings();
  }
}

final settingsProvider = NotifierProvider<SettingsNotifier, SettingsState>(() {
  return SettingsNotifier();
});
