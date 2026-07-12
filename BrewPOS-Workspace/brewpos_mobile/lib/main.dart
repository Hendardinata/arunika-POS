import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/foundation.dart';
import 'screens/login_screen.dart';
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
  
  runApp(
    const ProviderScope(
      child: BrewPOSApp(),
    ),
  );
}

class BrewPOSApp extends ConsumerWidget {
  const BrewPOSApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(settingsProvider);

    return MaterialApp(
      title: settings.storeName,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: settings.storeColor),
        primaryColor: settings.storeColor,
        useMaterial3: true,
      ),
      home: const LoginScreen(),
      debugShowCheckedModeBanner: false,
    );
  }
}
