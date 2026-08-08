import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';
import 'pos_screen.dart' show formatRp;

class ReportScreen extends StatefulWidget {
  const ReportScreen({super.key});

  @override
  State<ReportScreen> createState() => _ReportScreenState();
}

class _ReportScreenState extends State<ReportScreen> {
  int _selectedDays = 1;
  Map<String, dynamic>? _reportData;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _fetchReport();
  }

  Future<void> _fetchReport() async {
    setState(() => _isLoading = true);
    try {
      final res = await http.get(Uri.parse('http://100.77.229.76:3001/api/analytics?days=$_selectedDays'));
      if (res.statusCode == 200) {
        setState(() {
          _reportData = json.decode(res.body);
          _isLoading = false;
        });
      } else {
        setState(() => _isLoading = false);
      }
    } catch (e) {
      setState(() => _isLoading = false);
      debugPrint('Error fetching report: $e');
    }
  }

  Future<void> _generatePdf() async {
    if (_reportData == null) return;

    final pdf = pw.Document();
    
    final String title = _selectedDays == 1 
      ? 'Laporan Penjualan (Hari Ini)' 
      : 'Laporan Penjualan ($_selectedDays Hari Terakhir)';
      
    final popularMenus = _reportData!['popularMenus'] as List<dynamic>;

    pdf.addPage(
      pw.Page(
        pageFormat: PdfPageFormat.a4,
        build: (pw.Context context) {
          return pw.Column(
            crossAxisAlignment: pw.CrossAxisAlignment.start,
            children: [
              pw.Text(title, style: pw.TextStyle(fontSize: 24, fontWeight: pw.FontWeight.bold)),
              pw.SizedBox(height: 20),
              
              pw.Text('Ringkasan', style: pw.TextStyle(fontSize: 18, fontWeight: pw.FontWeight.bold)),
              pw.SizedBox(height: 10),
              pw.Text('Total Pendapatan: Rp ${formatRp(_reportData!['totalRevenue'] ?? 0)}', style: const pw.TextStyle(fontSize: 14)),
              pw.Text('Total Pesanan: ${_reportData!['totalOrders'] ?? 0}', style: const pw.TextStyle(fontSize: 14)),
              
              pw.SizedBox(height: 20),
              pw.Text('Menu Terlaris', style: pw.TextStyle(fontSize: 18, fontWeight: pw.FontWeight.bold)),
              pw.SizedBox(height: 10),
              if (popularMenus.isEmpty)
                pw.Text('Belum ada data menu.')
              else
                pw.ListView.builder(
                  itemCount: popularMenus.length,
                  itemBuilder: (context, index) {
                    final menu = popularMenus[index];
                    return pw.Text('${index + 1}. ${menu['name']} - ${menu['count']} terjual', style: const pw.TextStyle(fontSize: 14));
                  }
                ),
            ],
          );
        },
      ),
    );

    await Printing.layoutPdf(
      onLayout: (PdfPageFormat format) async => pdf.save(),
      name: 'laporan_penjualan_${_selectedDays}_hari',
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAFAFA),
      appBar: AppBar(
        title: const Text('Laporan Penjualan', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.black87)),
        backgroundColor: Colors.white,
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.black87),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1.0),
          child: Container(color: Colors.grey[200], height: 1.0),
        ),
        actions: [
          if (!_isLoading && _reportData != null)
            Padding(
              padding: const EdgeInsets.only(right: 8.0),
              child: ElevatedButton.icon(
                onPressed: _generatePdf,
                icon: const Icon(Icons.picture_as_pdf_rounded, size: 20, color: Colors.white),
                label: const Text('Unduh PDF', style: TextStyle(color: Colors.white)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.redAccent,
                  elevation: 0,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
        ],
      ),
      body: Column(
        children: [
          // Filter section (Modern Pills)
          Container(
            color: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  const Icon(Icons.calendar_month_rounded, color: Colors.grey, size: 20),
                  const SizedBox(width: 12),
                  _buildFilterChip('Hari Ini', 1),
                  const SizedBox(width: 8),
                  _buildFilterChip('7 Hari', 7),
                  const SizedBox(width: 8),
                  _buildFilterChip('30 Hari', 30),
                ],
              ),
            ),
          ),
          
          // Data Section
          Expanded(
            child: _isLoading
                ? Center(child: CircularProgressIndicator(color: Theme.of(context).primaryColor))
                : _reportData == null
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.error_outline_rounded, size: 80, color: Colors.red[200]),
                            const SizedBox(height: 16),
                            Text('Gagal mengambil data laporan.', style: TextStyle(color: Colors.grey[600], fontSize: 16)),
                          ],
                        ),
                      )
                    : ListView(
                        padding: const EdgeInsets.all(24),
                        children: [
                          // Summary Cards
                          Row(
                            children: [
                              Expanded(
                                child: _buildSummaryCard(
                                  'Total Pendapatan',
                                  'Rp ${formatRp(_reportData!['totalRevenue'] ?? 0)}',
                                  Icons.account_balance_wallet_rounded,
                                  Colors.green,
                                ),
                              ),
                              const SizedBox(width: 16),
                              Expanded(
                                child: _buildSummaryCard(
                                  'Total Pesanan',
                                  '${_reportData!['totalOrders'] ?? 0}',
                                  Icons.receipt_long_rounded,
                                  Colors.blue,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 32),
                          
                          // Popular Menus
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.all(8),
                                decoration: BoxDecoration(
                                  color: Theme.of(context).primaryColor.withOpacity(0.1),
                                  borderRadius: BorderRadius.circular(10),
                                ),
                                child: Icon(Icons.star_rounded, color: Theme.of(context).primaryColor, size: 20),
                              ),
                              const SizedBox(width: 12),
                              const Text('Menu Terlaris', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: Colors.black87)),
                            ],
                          ),
                          const SizedBox(height: 16),
                          if ((_reportData!['popularMenus'] as List).isEmpty)
                            Container(
                              padding: const EdgeInsets.symmetric(vertical: 40),
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(20),
                                border: Border.all(color: Colors.grey[200]!),
                              ),
                              child: Column(
                                children: [
                                  Icon(Icons.fastfood_outlined, size: 48, color: Colors.grey[300]),
                                  const SizedBox(height: 12),
                                  Text('Belum ada menu yang terjual.', style: TextStyle(color: Colors.grey[500])),
                                ],
                              ),
                            )
                          else
                            Container(
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(20),
                                border: Border.all(color: Colors.grey[200]!),
                                boxShadow: [
                                  BoxShadow(color: Colors.black.withOpacity(0.02), blurRadius: 15, offset: const Offset(0, 5)),
                                ],
                              ),
                              child: Material(
                                color: Colors.transparent,
                                child: Column(
                                  children: List.generate((_reportData!['popularMenus'] as List).length, (index) {
                                  final menu = _reportData!['popularMenus'][index];
                                  final isFirst = index == 0;
                                  final isSecond = index == 1;
                                  final isThird = index == 2;
                                  
                                  Color rankColor = Colors.grey[400]!;
                                  if (isFirst) rankColor = Colors.amber;
                                  if (isSecond) rankColor = Colors.grey[400]!; // Silver
                                  if (isThird) rankColor = Colors.brown[300]!; // Bronze

                                  return Column(
                                    children: [
                                      ListTile(
                                        contentPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
                                        leading: Stack(
                                          clipBehavior: Clip.none,
                                          children: [
                                            Container(
                                              width: 50,
                                              height: 50,
                                              decoration: BoxDecoration(
                                                color: index < 3 ? rankColor.withOpacity(0.1) : Colors.grey[100],
                                                borderRadius: BorderRadius.circular(12),
                                              ),
                                              child: Center(
                                                child: Text(
                                                  '#${index + 1}',
                                                  style: TextStyle(
                                                    fontWeight: FontWeight.w900,
                                                    fontSize: 16,
                                                    color: index < 3 ? rankColor : Colors.grey[600],
                                                  ),
                                                ),
                                              ),
                                            ),
                                            if (isFirst)
                                              Positioned(
                                                top: -8,
                                                right: -8,
                                                child: Icon(Icons.workspace_premium_rounded, color: Colors.amber, size: 20),
                                              ),
                                          ],
                                        ),
                                        title: Text(menu['name'], style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                                        trailing: Column(
                                          mainAxisAlignment: MainAxisAlignment.center,
                                          crossAxisAlignment: CrossAxisAlignment.end,
                                          children: [
                                            Text('${menu['count']}', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 18, color: Theme.of(context).primaryColor)),
                                            const Text('terjual', style: TextStyle(fontSize: 10, color: Colors.grey)),
                                          ],
                                        ),
                                      ),
                                      if (index < (_reportData!['popularMenus'] as List).length - 1)
                                        Padding(
                                          padding: const EdgeInsets.symmetric(horizontal: 24.0),
                                          child: Divider(height: 1, color: Colors.grey[100]),
                                        ),
                                    ],
                                  );
                                }),
                              ),
                            ),
                          ),
                        ],
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterChip(String label, int days) {
    final isSelected = _selectedDays == days;
    return InkWell(
      onTap: () {
        if (_selectedDays != days) {
          setState(() => _selectedDays = days);
          _fetchReport();
        }
      },
      borderRadius: BorderRadius.circular(20),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
        decoration: BoxDecoration(
          color: isSelected ? Theme.of(context).primaryColor : Colors.grey[100],
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: isSelected ? Theme.of(context).primaryColor : Colors.transparent),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isSelected ? Colors.white : Colors.grey[600],
            fontWeight: isSelected ? FontWeight.bold : FontWeight.w600,
          ),
        ),
      ),
    );
  }

  Widget _buildSummaryCard(String title, String value, IconData icon, MaterialColor color) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.grey[200]!),
        boxShadow: [
          BoxShadow(color: Colors.black.withOpacity(0.02), blurRadius: 15, offset: const Offset(0, 5)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: color.withOpacity(0.1),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Icon(icon, color: color[700], size: 28),
          ),
          const SizedBox(height: 16),
          Text(title, style: TextStyle(color: Colors.grey[500], fontSize: 13, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(
            value, 
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900, color: Colors.black87),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}
