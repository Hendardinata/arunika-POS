import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'pos_screen.dart' show formatRp;

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<dynamic> _history = [];
  bool _isLoading = true;
  
  // Pagination State
  int _currentPage = 1;
  final int _itemsPerPage = 10;

  @override
  void initState() {
    super.initState();
    _fetchHistory();
  }

  Future<void> _fetchHistory() async {
    try {
      final res = await http.get(Uri.parse('http://127.0.0.1:3001/api/checkout/history'));
      if (res.statusCode == 200) {
        setState(() {
          _history = json.decode(res.body);
          _isLoading = false;
          _currentPage = 1; // Reset to page 1 on fetch
        });
      } else {
        setState(() => _isLoading = false);
      }
    } catch (e) {
      setState(() => _isLoading = false);
      debugPrint('Error fetching history: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final isTablet = MediaQuery.of(context).size.width > 800;
    
    // Calculate Pagination
    final int totalItems = _history.length;
    final int totalPages = totalItems > 0 ? (totalItems / _itemsPerPage).ceil() : 1;
    final int startIndex = (_currentPage - 1) * _itemsPerPage;
    final int endIndex = (startIndex + _itemsPerPage > totalItems) ? totalItems : startIndex + _itemsPerPage;
    
    final paginatedHistory = _history.isNotEmpty ? _history.sublist(startIndex, endIndex) : [];

    return Scaffold(
      backgroundColor: const Color(0xFFFAFAFA),
      appBar: AppBar(
        title: const Text('Riwayat Pemesanan', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.black87)),
        backgroundColor: Colors.white,
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.black87),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1.0),
          child: Container(color: Colors.grey[200], height: 1.0),
        ),
      ),
      body: _isLoading
          ? Center(child: CircularProgressIndicator(color: Theme.of(context).primaryColor))
          : _history.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.history_rounded, size: 80, color: Colors.grey[300]),
                      const SizedBox(height: 16),
                      Text('Belum ada riwayat transaksi', style: TextStyle(color: Colors.grey[500], fontSize: 16)),
                    ],
                  ),
                )
              : Column(
                  children: [
                    Expanded(
                      child: ListView.builder(
                        padding: EdgeInsets.symmetric(horizontal: isTablet ? 32 : 16, vertical: 24),
                        itemCount: paginatedHistory.length,
                        itemBuilder: (context, index) {
                          final tx = paginatedHistory[index];
                          final customerName = tx['customer'] != null ? tx['customer']['nickname'] : 'Pelanggan (Offline)';
                          final date = DateTime.parse(tx['createdAt']).toLocal();
                          final formattedDate = '${date.day.toString().padLeft(2, '0')}/${date.month.toString().padLeft(2, '0')}/${date.year} ${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';
                          final total = tx['totalAmount'] + (tx['totalAmount'] * 0.1).round(); // Calculate Grand Total
                          final paymentMethod = tx['paymentMethod'] ?? 'CASH';

                          return Container(
                            margin: const EdgeInsets.only(bottom: 20),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(color: Colors.grey[200]!),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withOpacity(0.02),
                                  blurRadius: 15,
                                  offset: const Offset(0, 5),
                                )
                              ],
                            ),
                            child: Material(
                              color: Colors.transparent,
                              child: Theme(
                                data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                                child: ExpansionTile(
                                  tilePadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
                                  childrenPadding: EdgeInsets.zero,
                                leading: Container(
                                  padding: const EdgeInsets.all(12),
                                  decoration: BoxDecoration(
                                    color: Theme.of(context).primaryColor.withOpacity(0.08),
                                    borderRadius: BorderRadius.circular(16),
                                  ),
                                  child: Icon(Icons.receipt_long_rounded, color: Theme.of(context).primaryColor, size: 28),
                                ),
                                title: Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(customerName, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17, color: Colors.black87), maxLines: 1, overflow: TextOverflow.ellipsis),
                                          const SizedBox(height: 4),
                                          Text(formattedDate, style: TextStyle(color: Colors.grey[500], fontSize: 13)),
                                        ],
                                      ),
                                    ),
                                    const SizedBox(width: 16),
                                    Column(
                                      crossAxisAlignment: CrossAxisAlignment.end,
                                      children: [
                                        Text('Rp ${formatRp(total)}', style: TextStyle(color: Theme.of(context).primaryColor, fontWeight: FontWeight.bold, fontSize: 16)),
                                        const SizedBox(height: 4),
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                          decoration: BoxDecoration(
                                            color: paymentMethod == 'CASH' ? Colors.green.withOpacity(0.1) : Colors.blue.withOpacity(0.1),
                                            borderRadius: BorderRadius.circular(8)
                                          ),
                                          child: Text(paymentMethod, style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: paymentMethod == 'CASH' ? Colors.green[700] : Colors.blue[700])),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.symmetric(horizontal: 24.0),
                                    child: Divider(color: Colors.grey[200], height: 1),
                                  ),
                                  Container(
                                    padding: const EdgeInsets.all(24),
                                    decoration: const BoxDecoration(
                                      color: Colors.white,
                                      borderRadius: BorderRadius.vertical(bottom: Radius.circular(20)),
                                    ),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        const Text('Detail Pesanan', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.grey, letterSpacing: 1.2)),
                                        const SizedBox(height: 12),
                                        ...(tx['items'] as List<dynamic>).map((item) {
                                          return Padding(
                                            padding: const EdgeInsets.only(bottom: 12.0),
                                            child: Row(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                Container(
                                                  padding: const EdgeInsets.all(6),
                                                  decoration: BoxDecoration(
                                                    color: Colors.grey[100],
                                                    borderRadius: BorderRadius.circular(8),
                                                  ),
                                                  child: Text('${item['quantity']}x', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.grey[800], fontSize: 13)),
                                                ),
                                                const SizedBox(width: 12),
                                                Expanded(
                                                  child: Padding(
                                                    padding: const EdgeInsets.only(top: 4.0),
                                                    child: Text('${item['menu'] != null ? item['menu']['name'] : 'Menu #${item['menuId']}'}', style: const TextStyle(color: Colors.black87, fontWeight: FontWeight.w600)),
                                                  ),
                                                ),
                                                Padding(
                                                  padding: const EdgeInsets.only(top: 4.0),
                                                  child: Text('Rp ${formatRp(item['price'] * item['quantity'])}', style: const TextStyle(color: Colors.black54, fontWeight: FontWeight.w500)),
                                                ),
                                              ],
                                            ),
                                          );
                                        }).toList(),
                                        const SizedBox(height: 8),
                                        Divider(color: Colors.grey[200]),
                                        const SizedBox(height: 8),
                                        Row(
                                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                          children: [
                                            const Text('Subtotal', style: TextStyle(color: Colors.grey)),
                                            Text('Rp ${formatRp(tx['totalAmount'])}', style: const TextStyle(color: Colors.black87)),
                                          ],
                                        ),
                                        const SizedBox(height: 4),
                                        Row(
                                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                          children: [
                                            const Text('Pajak (10%)', style: TextStyle(color: Colors.grey)),
                                            Text('Rp ${formatRp((tx['totalAmount'] * 0.1).round())}', style: const TextStyle(color: Colors.black87)),
                                          ],
                                        ),
                                      ],
                                    ),
                                  )
                                ],
                              ),
                            ),
                          ),
                        );
                        },
                      ),
                    ),
                    
                    // Pagination Controls
                    if (totalPages > 1)
                      Container(
                        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 24),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          border: Border(top: BorderSide(color: Colors.grey[200]!)),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            _buildPageButton(
                              icon: Icons.chevron_left_rounded, 
                              isActive: _currentPage > 1, 
                              onTap: () {
                                if (_currentPage > 1) setState(() => _currentPage--);
                              }
                            ),
                            const SizedBox(width: 16),
                            Text('Halaman $_currentPage dari $totalPages', style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.black87)),
                            const SizedBox(width: 16),
                            _buildPageButton(
                              icon: Icons.chevron_right_rounded, 
                              isActive: _currentPage < totalPages, 
                              onTap: () {
                                if (_currentPage < totalPages) setState(() => _currentPage++);
                              }
                            ),
                          ],
                        ),
                      )
                  ],
                ),
    );
  }

  Widget _buildPageButton({required IconData icon, required bool isActive, required VoidCallback onTap}) {
    return InkWell(
      onTap: isActive ? onTap : null,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: isActive ? Theme.of(context).primaryColor.withOpacity(0.1) : Colors.grey[100],
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: isActive ? Theme.of(context).primaryColor.withOpacity(0.3) : Colors.transparent),
        ),
        child: Icon(
          icon, 
          color: isActive ? Theme.of(context).primaryColor : Colors.grey[400],
        ),
      ),
    );
  }
}
