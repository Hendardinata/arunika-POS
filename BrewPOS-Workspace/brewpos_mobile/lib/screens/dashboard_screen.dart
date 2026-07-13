import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../providers/settings_provider.dart';
import '../providers/auth_provider.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  bool _isLoading = true;
  Map<String, dynamic>? _analyticsData;

  @override
  void initState() {
    super.initState();
    _fetchAnalytics();
  }

  Future<void> _fetchAnalytics() async {
    try {
      final res = await http.get(Uri.parse('http://127.0.0.1:3001/api/analytics?days=7'));
      if (res.statusCode == 200) {
        if (mounted) {
          setState(() {
            _analyticsData = json.decode(res.body);
            _isLoading = false;
          });
        }
      } else {
        if (mounted) setState(() => _isLoading = false);
      }
    } catch (e) {
      debugPrint('Failed to fetch analytics: $e');
      if (mounted) setState(() => _isLoading = false);
    }
  }

  String _formatRp(dynamic amount) {
    if (amount == null) return '0';
    String numStr = amount.toString();
    // Use regex to add dots for thousands separators
    return numStr.replaceAllMapped(
      RegExp(r'(\d{1,3})(?=(\d{3})+(?!\d))'),
      (Match m) => '${m[1]}.'
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Scaffold(
        backgroundColor: Color(0xFFF8F9FA),
        body: Center(child: CircularProgressIndicator()),
      );
    }

    final settings = ref.watch(settingsProvider);
    final user = ref.watch(authProvider);
    final isCashier = user?.role == 'CASHIER';
    final isTablet = MediaQuery.of(context).size.width >= 600;

    return Scaffold(
      backgroundColor: const Color(0xFFF8F9FA),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Modern Header
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Halo, ${settings.storeName}',
                        style: const TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w900,
                          color: Colors.black87,
                          letterSpacing: -0.5,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Berikut adalah ringkasan bisnis Anda hari ini.',
                        style: TextStyle(
                          fontSize: 15,
                          color: Colors.grey[600],
                        ),
                      ),
                    ],
                  ),
                  if (settings.storeLogo != null && settings.storeLogo!.isNotEmpty)
                    Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: Colors.white,
                        boxShadow: [
                          BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 10, offset: const Offset(0, 5))
                        ],
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: Image.memory(
                        base64Decode(settings.storeLogo!.split(',').last),
                        fit: BoxFit.cover,
                        errorBuilder: (context, error, stackTrace) => Icon(Icons.store_rounded, size: 28, color: Theme.of(context).primaryColor),
                      ),
                    )
                  else
                    CircleAvatar(
                      radius: 28,
                      backgroundColor: Theme.of(context).primaryColor.withOpacity(0.1),
                      child: Icon(Icons.store_rounded, size: 28, color: Theme.of(context).primaryColor),
                    ),
                ],
              ),
              const SizedBox(height: 32),

              if (!isCashier) ...[
                // Summary Cards section
                isTablet 
                  ? Row(
                      children: [
                        Expanded(child: _buildSummaryCard(context, 'Total Pendapatan', 'Rp ${_formatRp(_analyticsData?['totalRevenue'] ?? 0)}', '+0%', Icons.trending_up_rounded, true)),
                        const SizedBox(width: 16),
                        Expanded(child: _buildSummaryCard(context, 'Total Transaksi', '${_analyticsData?['totalOrders'] ?? 0}', '+0%', Icons.receipt_long_rounded, false)),
                        const SizedBox(width: 16),
                        Expanded(child: _buildSummaryCard(context, 'Total Pelanggan', '${_analyticsData?['totalCustomers'] ?? 0}', '+0%', Icons.group_add_rounded, false)),
                      ],
                    )
                  : Column(
                      children: [
                        _buildSummaryCard(context, 'Total Pendapatan', 'Rp ${_formatRp(_analyticsData?['totalRevenue'] ?? 0)}', '+0%', Icons.trending_up_rounded, true),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(child: _buildSummaryCard(context, 'Transaksi', '${_analyticsData?['totalOrders'] ?? 0}', '+0%', Icons.receipt_long_rounded, false)),
                            const SizedBox(width: 12),
                            Expanded(child: _buildSummaryCard(context, 'Pelanggan', '${_analyticsData?['totalCustomers'] ?? 0}', '+0%', Icons.group_add_rounded, false)),
                          ],
                        )
                      ],
                    ),
                    
                const SizedBox(height: 32),
              ],
              
              // Analytics Section (Chart)
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(24),
                  boxShadow: [
                    BoxShadow(color: Colors.black.withOpacity(0.02), blurRadius: 15, offset: const Offset(0, 8))
                  ],
                  border: Border.all(color: Colors.grey[100]!),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Analitik Penjualan', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.black87)),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                          decoration: BoxDecoration(color: Colors.grey[100], borderRadius: BorderRadius.circular(20)),
                          child: const Text('Minggu Ini', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                        )
                      ],
                    ),
                    const SizedBox(height: 32),
                    // Dynamic Mock Bar Chart
                    SizedBox(
                      height: 180,
                      child: Builder(
                        builder: (context) {
                          final chartData = (_analyticsData?['chartData'] as List<dynamic>?) ?? [];
                          if (chartData.isEmpty) {
                            return const Center(child: Text('Belum ada data penjualan minggu ini', style: TextStyle(color: Colors.grey)));
                          }
                          
                          double maxRevenue = 0;
                          for (var item in chartData) {
                            final rev = (item['revenue'] as num).toDouble();
                            if (rev > maxRevenue) maxRevenue = rev;
                          }
                          if (maxRevenue == 0) maxRevenue = 1; 

                          final displayData = chartData.length > 7 ? chartData.sublist(chartData.length - 7) : chartData;

                          return Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: displayData.map((item) {
                              final rev = (item['revenue'] as num).toDouble();
                              final pct = rev / maxRevenue;
                              final dateStr = item['date'].toString(); 
                              final label = dateStr.split(' ').first; // usually the day or date
                              return _buildChartBar(context, label, pct, isHighlighted: rev == maxRevenue);
                            }).toList(),
                          );
                        }
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 24),

              // Top Items Section
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(24),
                  boxShadow: [
                    BoxShadow(color: Colors.black.withOpacity(0.02), blurRadius: 15, offset: const Offset(0, 8))
                  ],
                  border: Border.all(color: Colors.grey[100]!),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Menu Terlaris', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.black87)),
                    const SizedBox(height: 20),
                    Builder(
                      builder: (context) {
                        final topMenus = (_analyticsData?['popularMenus'] as List<dynamic>?) ?? [];
                        if (topMenus.isEmpty) {
                          return const Center(
                            child: Padding(
                              padding: EdgeInsets.all(16), 
                              child: Text('Belum ada data menu terjual minggu ini', style: TextStyle(color: Colors.grey))
                            )
                          );
                        }
                        
                        double maxCount = 0;
                        for (var item in topMenus) {
                          final count = (item['count'] as num).toDouble();
                          if (count > maxCount) maxCount = count;
                        }
                        if (maxCount == 0) maxCount = 1;

                        List<Widget> menuWidgets = [];
                        for (int i = 0; i < topMenus.length; i++) {
                          final menu = topMenus[i];
                          final count = (menu['count'] as num).toDouble();
                          menuWidgets.add(_buildTopItem(context, menu['name'], '${count.toInt()} terjual', count / maxCount, '${i + 1}'));
                          if (i < topMenus.length - 1) {
                            menuWidgets.add(const Padding(padding: EdgeInsets.symmetric(vertical: 16), child: Divider(height: 1, color: Color(0xFFF0F0F0))));
                          }
                        }
                        return Column(children: menuWidgets);
                      }
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSummaryCard(BuildContext context, String title, String value, String trend, IconData icon, bool isPrimary) {
    // For now we disable dynamic trend percentage since we don't have historical comparison data in the API.
    // It's kept aesthetic with a +0% or we can just hide it if preferred.
    final isPositive = trend.startsWith('+');
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isPrimary ? Theme.of(context).primaryColor : Colors.white,
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          if (isPrimary)
            BoxShadow(color: Theme.of(context).primaryColor.withOpacity(0.3), blurRadius: 15, offset: const Offset(0, 8))
          else
            BoxShadow(color: Colors.black.withOpacity(0.02), blurRadius: 10, offset: const Offset(0, 4))
        ],
        border: isPrimary ? null : Border.all(color: Colors.grey[100]!),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: isPrimary ? Colors.white.withOpacity(0.2) : Theme.of(context).primaryColor.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, color: isPrimary ? Colors.white : Theme.of(context).primaryColor, size: 24),
              ),
            ],
          ),
          const SizedBox(height: 20),
          Text(
            title,
            style: TextStyle(
              fontSize: 14,
              color: isPrimary ? Colors.white.withOpacity(0.8) : Colors.grey[500],
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 4),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              value,
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w900,
                color: isPrimary ? Colors.white : Colors.black87,
                letterSpacing: -0.5,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildChartBar(BuildContext context, String label, double percentage, {bool isHighlighted = false}) {
    // minimum height for visibility
    final safePercentage = percentage < 0.05 ? 0.05 : percentage;
    return Column(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        Container(
          width: 32,
          height: 140 * safePercentage,
          decoration: BoxDecoration(
            color: isHighlighted ? Theme.of(context).primaryColor : Theme.of(context).primaryColor.withOpacity(0.15),
            borderRadius: BorderRadius.circular(8),
          ),
        ),
        const SizedBox(height: 12),
        Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: isHighlighted ? FontWeight.bold : FontWeight.normal,
            color: isHighlighted ? Colors.black87 : Colors.grey[500],
          ),
        ),
      ],
    );
  }

  Widget _buildTopItem(BuildContext context, String name, String subtitle, double percentage, String rank) {
    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: rank == '1' ? const Color(0xFFFFD700).withOpacity(0.2) : Colors.grey[100],
            shape: BoxShape.circle,
          ),
          child: Center(
            child: Text(
              '#$rank',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: rank == '1' ? const Color(0xFFB8860B) : Colors.grey[600],
              ),
            ),
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(name, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
                  Text(subtitle, style: TextStyle(color: Colors.grey[500], fontSize: 13)),
                ],
              ),
              const SizedBox(height: 8),
              Stack(
                children: [
                  Container(
                    height: 6,
                    width: double.infinity,
                    decoration: BoxDecoration(color: Colors.grey[100], borderRadius: BorderRadius.circular(3)),
                  ),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      return Container(
                        height: 6,
                        width: constraints.maxWidth * percentage,
                        decoration: BoxDecoration(color: Theme.of(context).primaryColor, borderRadius: BorderRadius.circular(3)),
                      );
                    }
                  ),
                ],
              )
            ],
          ),
        ),
      ],
    );
  }
}
