import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'providers/auth_provider.dart';
import 'screens/login_screen.dart';
import 'screens/main_screen.dart';
import 'database/db_helper.dart';
import 'providers/settings_provider.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    if (!kIsWeb) {
      await DBHelper().db; // Inisialisasi DB SQLite sebelum app berjalan
    }
  } catch (e) {
    debugPrint('Gagal inisialisasi DB: $e');
  }

  final sharedPreferences = await SharedPreferences.getInstance();
  
  runApp(
    ProviderScope(
      overrides: [
        sharedPrefsProvider.overrideWithValue(sharedPreferences),
      ],
      child: const BrewPOSApp(),
    ),
  );
}

class BrewPOSApp extends ConsumerWidget {
  const BrewPOSApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(settingsProvider);
    final authUser = ref.watch(authProvider);

    return MaterialApp(
      title: settings.storeName,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: settings.storeColor),
        primaryColor: settings.storeColor,
        useMaterial3: true,
      ),
      home: authUser == null ? const LoginScreen() : const MainScreen(),
      debugShowCheckedModeBanner: false,
    );
  }
}
