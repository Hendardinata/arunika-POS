import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../database/db_helper.dart';
import '../providers/cart_provider.dart';
import '../providers/auth_provider.dart';
import 'pos_screen.dart';
import 'history_screen.dart';
import 'report_screen.dart';
import 'inventory_screen.dart';
import 'login_screen.dart';
import 'opname_screen.dart';

class MainScreen extends ConsumerStatefulWidget {
  const MainScreen({super.key});

  @override
  ConsumerState<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends ConsumerState<MainScreen> {
  int _selectedIndex = 0;

  List<Widget> _getScreens(bool isCashier, bool hideReport) {
    List<Widget> screens = [
      const PosScreen(),
      const HistoryScreen(),
    ];
    if (!hideReport) screens.add(const ReportScreen());
    screens.add(const InventoryScreen());
    if (!isCashier) screens.add(const OpnameScreen());
    return screens;
  }

  Future<void> _syncOfflineTransactions() async {
    final offlineTx = await DBHelper().getOfflineTransactions();
    if (offlineTx.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Tidak ada transaksi tertunda.')));
      }
      return;
    }
    
    try {
      final res = await http.post(
        Uri.parse('http://127.0.0.1:3001/api/checkout/sync'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'transactions': offlineTx.map((e) => e['payload']).toList()}),
      );
      if (res.statusCode == 201) {
        for (var tx in offlineTx) {
          await DBHelper().deleteOfflineTransaction(tx['id']);
        }
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Berhasil sinkronisasi ${offlineTx.length} transaksi.'), backgroundColor: Colors.green));
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Gagal sinkronisasi: Server error'), backgroundColor: Colors.red));
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Gagal sinkronisasi: Tidak ada internet'), backgroundColor: Colors.red));
      }
    }
  }

  void _logout() {
    ref.read(cartProvider.notifier).clearCart();
    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        pageBuilder: (context, animation, secondaryAnimation) => const LoginScreen(),
        transitionsBuilder: (context, animation, secondaryAnimation, child) {
          return FadeTransition(opacity: animation, child: child);
        },
        transitionDuration: const Duration(milliseconds: 300),
      ),
    );
  }

  void _showMoreMenu() {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(Icons.sync),
                title: const Text('Sinkronisasi Offline'),
                onTap: () {
                  Navigator.pop(context);
                  _syncOfflineTransactions();
                },
              ),
              ListTile(
                leading: const Icon(Icons.logout, color: Colors.red),
                title: const Text('Keluar', style: TextStyle(color: Colors.red)),
                onTap: () {
                  Navigator.pop(context);
                  _logout();
                },
              ),
            ],
          ),
        );
      }
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authProvider);
    final bool isCashier = user?.role == 'CASHIER';
    final bool isHeadbar = user?.role == 'HEADBAR';
    final bool hideReport = isCashier || isHeadbar;
    final isTablet = MediaQuery.of(context).size.width >= 600;
    
    final screens = _getScreens(isCashier, hideReport);
    
    List<NavigationRailDestination> railDestinations = [
      const NavigationRailDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: Text('POS')),
      const NavigationRailDestination(icon: Icon(Icons.history_outlined), selectedIcon: Icon(Icons.history), label: Text('Riwayat')),
    ];
    if (!hideReport) railDestinations.add(const NavigationRailDestination(icon: Icon(Icons.bar_chart_outlined), selectedIcon: Icon(Icons.bar_chart), label: Text('Laporan')));
    railDestinations.add(const NavigationRailDestination(icon: Icon(Icons.inventory_2_outlined), selectedIcon: Icon(Icons.inventory_2), label: Text('Stok')));
    if (!isCashier) railDestinations.add(const NavigationRailDestination(icon: Icon(Icons.fact_check_outlined), selectedIcon: Icon(Icons.fact_check), label: Text('Opname')));

    int syncIdx = railDestinations.length;
    railDestinations.add(const NavigationRailDestination(icon: Icon(Icons.sync_outlined), selectedIcon: Icon(Icons.sync), label: Text('Sinkron')));
    
    int logoutIdx = railDestinations.length;
    railDestinations.add(const NavigationRailDestination(icon: Icon(Icons.logout, color: Colors.red), label: Text('Keluar', style: TextStyle(color: Colors.red))));

    List<BottomNavigationBarItem> bottomItems = [
      const BottomNavigationBarItem(icon: Icon(Icons.dashboard), label: 'POS'),
      const BottomNavigationBarItem(icon: Icon(Icons.history), label: 'Riwayat'),
    ];
    if (!hideReport) bottomItems.add(const BottomNavigationBarItem(icon: Icon(Icons.bar_chart), label: 'Laporan'));
    bottomItems.add(const BottomNavigationBarItem(icon: Icon(Icons.inventory_2), label: 'Stok'));
    if (!isCashier) bottomItems.add(const BottomNavigationBarItem(icon: Icon(Icons.fact_check), label: 'Opname'));
    
    int moreIdx = bottomItems.length;
    bottomItems.add(const BottomNavigationBarItem(icon: Icon(Icons.more_horiz), label: 'Lainnya'));

    final maxScreenIndex = screens.length - 1;

    if (isTablet) {
      return Scaffold(
        body: Row(
          children: [
            NavigationRail(
              selectedIndex: _selectedIndex > maxScreenIndex ? null : _selectedIndex,
              onDestinationSelected: (idx) {
                if (idx == logoutIdx) {
                  _logout();
                } else if (idx == syncIdx) {
                  _syncOfflineTransactions();
                } else {
                  setState(() => _selectedIndex = idx);
                }
              },
              labelType: NavigationRailLabelType.all,
              backgroundColor: Colors.white,
              indicatorColor: Theme.of(context).primaryColor,
              selectedIconTheme: const IconThemeData(color: Colors.white),
              unselectedIconTheme: const IconThemeData(color: Colors.grey),
              selectedLabelTextStyle: TextStyle(color: Theme.of(context).primaryColor, fontWeight: FontWeight.bold, fontSize: 12),
              unselectedLabelTextStyle: TextStyle(color: Colors.grey[500], fontSize: 12),
              destinations: railDestinations,
            ),
            Expanded(child: screens[_selectedIndex > maxScreenIndex ? 0 : _selectedIndex]),
          ],
        ),
      );
    }

    return Scaffold(
      body: screens[_selectedIndex > maxScreenIndex ? 0 : _selectedIndex],
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _selectedIndex > maxScreenIndex ? 0 : _selectedIndex,
        onTap: (idx) {
          if (idx == moreIdx) {
            _showMoreMenu();
          } else {
            setState(() => _selectedIndex = idx);
          }
        },
        type: BottomNavigationBarType.fixed,
        selectedItemColor: Theme.of(context).primaryColor,
        unselectedItemColor: Colors.grey,
        items: bottomItems,
      ),
    );
  }
}
