import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../database/db_helper.dart';
import '../providers/cart_provider.dart';
import '../providers/auth_provider.dart';
import 'dashboard_screen.dart';
import 'pos_screen.dart';
import 'history_screen.dart';
import 'report_screen.dart';
import 'inventory_screen.dart';
import 'login_screen.dart';
import 'opname_screen.dart';
import '../providers/settings_provider.dart';

class MainScreen extends ConsumerStatefulWidget {
  const MainScreen({super.key});

  @override
  ConsumerState<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends ConsumerState<MainScreen> {
  int _selectedIndex = 0;

  List<Widget> _getScreens(bool isCashier, bool hideReport) {
    List<Widget> screens = [
      const DashboardScreen(),
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

  Widget _buildSidebarItem(String title, IconData icon, IconData activeIcon, bool isSelected, VoidCallback onTap, {bool isDestructive = false}) {
    final primaryColor = Theme.of(context).primaryColor;
    final bgColor = const Color(0xFFFAFAFA);

    if (!isSelected) {
      return InkWell(
        onTap: onTap,
        child: SizedBox(
          height: 60,
          child: Row(
            children: [
              const SizedBox(width: 24),
              Icon(icon, color: isDestructive ? Colors.red[300] : Colors.white70, size: 22),
              const SizedBox(width: 12),
              Text(
                title, 
                style: TextStyle(
                  color: isDestructive ? Colors.red[300] : Colors.white70, 
                  fontWeight: FontWeight.w500, 
                  fontSize: 14
                )
              ),
            ],
          ),
        ),
      );
    }

    return InkWell(
      onTap: onTap,
      child: SizedBox(
        height: 56,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            if (isSelected)
              Positioned(
                top: -24,
                bottom: -24,
                right: 0,
                left: 8,
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(child: Container(height: 24, color: Colors.transparent)),
                        Container(
                          width: 24, height: 24, color: bgColor,
                          child: Container(
                            decoration: BoxDecoration(
                              color: primaryColor,
                              borderRadius: const BorderRadius.only(bottomRight: Radius.circular(24)),
                            ),
                          ),
                        ),
                      ],
                    ),
                    Expanded(
                      child: Container(
                        decoration: BoxDecoration(
                          color: bgColor,
                          borderRadius: const BorderRadius.horizontal(left: Radius.circular(28)),
                        ),
                      ),
                    ),
                    Row(
                      children: [
                        Expanded(child: Container(height: 24, color: Colors.transparent)),
                        Container(
                          width: 24, height: 24, color: bgColor,
                          child: Container(
                            decoration: BoxDecoration(
                              color: primaryColor,
                              borderRadius: const BorderRadius.only(topRight: Radius.circular(24)),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            Align(
              alignment: Alignment.centerLeft,
              child: Padding(
                padding: const EdgeInsets.only(left: 24),
                child: Row(
                  children: [
                    Icon(isSelected ? activeIcon : icon, color: isSelected ? primaryColor : (isDestructive ? Colors.red[300] : const Color(0xFFC8E6C9)), size: 22),
                    const SizedBox(width: 12),
                    Text(
                      title,
                      style: TextStyle(
                        color: isSelected ? primaryColor : (isDestructive ? Colors.red[300] : Colors.white),
                        fontWeight: isSelected ? FontWeight.w800 : FontWeight.w500,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authProvider);
    final settings = ref.watch(settingsProvider);
    final bool isCashier = user?.role == 'CASHIER';
    final bool isHeadbar = user?.role == 'HEADBAR';
    final bool hideReport = isCashier || isHeadbar;
    final isTablet = MediaQuery.of(context).size.width >= 600;
    
    final screens = _getScreens(isCashier, hideReport);
    
    List<NavigationRailDestination> railDestinations = [
      const NavigationRailDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: Text('Beranda')),
      const NavigationRailDestination(icon: Icon(Icons.point_of_sale_outlined), selectedIcon: Icon(Icons.point_of_sale), label: Text('POS')),
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
      const BottomNavigationBarItem(icon: Icon(Icons.dashboard), label: 'Beranda'),
      const BottomNavigationBarItem(icon: Icon(Icons.point_of_sale), label: 'POS'),
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
        backgroundColor: const Color(0xFFFAFAFA),
        body: Row(
          children: [
            Container(
              width: 145, // Narrower width, fitting text + padding
              color: Theme.of(context).primaryColor,
              child: Column(
                children: [
                  const SizedBox(height: 40),
                  if (settings.storeLogo != null && settings.storeLogo!.isNotEmpty)
                    ClipRRect(
                      borderRadius: BorderRadius.circular(12),
                      child: SizedBox(
                        height: 48,
                        width: 48,
                        child: Builder(
                          builder: (context) {
                            try {
                              final base64Str = settings.storeLogo!.split(',').last;
                              return Image.memory(
                                base64Decode(base64.normalize(base64Str)),
                                fit: BoxFit.cover,
                              );
                            } catch (e) {
                              return const Icon(Icons.store, color: Colors.white, size: 24);
                            }
                          }
                        ),
                      ),
                    )
                  else
                    const Icon(Icons.storefront_rounded, color: Colors.white, size: 44),
                  const SizedBox(height: 32),
                  Expanded(
                    child: ListView(
                      padding: EdgeInsets.zero,
                      children: [
                        _buildSidebarItem('Beranda', Icons.dashboard_outlined, Icons.dashboard, _selectedIndex == 0, () => setState(() => _selectedIndex = 0)),
                        _buildSidebarItem('POS', Icons.point_of_sale_outlined, Icons.point_of_sale, _selectedIndex == 1, () => setState(() => _selectedIndex = 1)),
                        _buildSidebarItem('Riwayat', Icons.history_outlined, Icons.history, _selectedIndex == 2, () => setState(() => _selectedIndex = 2)),
                        if (!hideReport) _buildSidebarItem('Laporan', Icons.bar_chart_outlined, Icons.bar_chart, _selectedIndex == 3, () => setState(() => _selectedIndex = 3)),
                        _buildSidebarItem('Stok', Icons.inventory_2_outlined, Icons.inventory_2, _selectedIndex == (hideReport ? 3 : 4), () => setState(() => _selectedIndex = (hideReport ? 3 : 4))),
                        if (!isCashier) _buildSidebarItem('Opname', Icons.fact_check_outlined, Icons.fact_check, _selectedIndex == (hideReport ? 4 : 5), () => setState(() => _selectedIndex = (hideReport ? 4 : 5))),
                      ],
                    ),
                  ),
                  const Divider(color: Colors.white24, height: 1, indent: 24, endIndent: 24),
                  const SizedBox(height: 12),
                  _buildSidebarItem('Sinkron', Icons.sync_outlined, Icons.sync, false, _syncOfflineTransactions),
                  _buildSidebarItem('Keluar', Icons.logout, Icons.logout, false, _logout, isDestructive: true),
                  const SizedBox(height: 24),
                ],
              ),
            ),
            Expanded(
              child: screens[_selectedIndex > maxScreenIndex ? 0 : _selectedIndex],
            ),
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
