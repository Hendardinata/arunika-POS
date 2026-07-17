import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;

class OpnameScreen extends StatefulWidget {
  const OpnameScreen({super.key});

  @override
  State<OpnameScreen> createState() => _OpnameScreenState();
}

class _OpnameScreenState extends State<OpnameScreen> {
  bool _isLoading = true;
  String _status = 'NOT_OPEN'; // NOT_OPEN, OPEN, CLOSING
  Map<String, dynamic>? _currentOpname;
  List<dynamic> _inventory = [];
  
  // controllers/data for form
  Map<int, int> _stocks = {};
  Map<int, String> _notes = {};

  @override
  void initState() {
    super.initState();
    _fetchOpnameData();
  }

  Future<void> _fetchOpnameData() async {
    setState(() => _isLoading = true);
    try {
      final res = await http.get(Uri.parse('http://127.0.0.1:3001/api/inventory/opname/today'));
      if (res.statusCode == 200) {
        final data = json.decode(res.body);
        setState(() {
          _status = data['status'];
          if (_status == 'OPEN') {
            _currentOpname = data['opname'];
            _inventory = _currentOpname!['items'].map((i) => i['inventoryItem']).toList();
            // Pre-fill stocks for closing just in case
            for (var item in _currentOpname!['items']) {
              _stocks[item['inventoryItem']['id']] = item['inventoryItem']['stock'];
              _notes[item['inventoryItem']['id']] = '';
            }
          } else {
            _inventory = data['inventory'];
            // Pre-fill opening stocks from last night's left over
            for (var item in _inventory) {
              _stocks[item['id']] = item['stock'];
              _notes[item['id']] = '';
            }
          }
        });
      }
    } catch (e) {
      debugPrint('Failed to fetch opname: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Gagal mengambil data opname. Cek koneksi.')));
      }
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _submitOpening() async {
    setState(() => _isLoading = true);
    try {
      final List<Map<String, dynamic>> payloadItems = [];
      for (var item in _inventory) {
        int id = item['id'];
        payloadItems.add({
          'inventoryItemId': id,
          'openingStock': _stocks[id] ?? item['stock'],
          'morningNotes': _notes[id],
        });
      }

      final res = await http.post(
        Uri.parse('http://127.0.0.1:3001/api/inventory/opname/open'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'items': payloadItems}),
      );

      if (res.statusCode == 201) {
        await _fetchOpnameData();
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Stok awal berhasil disimpan.')));
      } else {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Gagal menyimpan stok awal.')));
      }
    } catch (e) {
      debugPrint('Error: $e');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _submitClosing() async {
    setState(() => _isLoading = true);
    try {
      final List<Map<String, dynamic>> payloadItems = [];
      for (var opItem in _currentOpname!['items']) {
        int id = opItem['inventoryItem']['id'];
        payloadItems.add({
          'inventoryItemId': id,
          'closingStock': _stocks[id] ?? opItem['inventoryItem']['stock'],
          'nightNotes': _notes[id],
        });
      }

      final res = await http.post(
        Uri.parse('http://127.0.0.1:3001/api/inventory/opname/close'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'opnameId': _currentOpname!['id'],
          'items': payloadItems
        }),
      );

      if (res.statusCode == 200) {
        final result = json.decode(res.body);
        if (mounted) {
          _showClosingSummary(result);
        }
      } else {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Gagal menyimpan stok akhir.')));
      }
    } catch (e) {
      debugPrint('Error: $e');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _showClosingSummary(Map<String, dynamic> opnameResult) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) {
        return AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
          title: const Text('Rekap Opname Hari Ini', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 22)),
          content: SizedBox(
            width: double.maxFinite,
            child: ListView.builder(
              shrinkWrap: true,
              itemCount: opnameResult['items'].length,
              itemBuilder: (context, index) {
                final item = opnameResult['items'][index];
                return Container(
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.grey[50],
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: Colors.grey[200]!)
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(item['inventoryItem']['name'], style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                      const SizedBox(height: 8),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          _buildMiniStat('Awal', item['openingStock']),
                          _buildMiniStat('Tambah', '+${item['addedStock'] ?? 0}', customColor: Colors.green[700]),
                          _buildMiniStat('Akhir', item['closingStock']),
                          _buildMiniStat('Pakai', item['used'], isHighlight: true),
                        ],
                      )
                    ],
                  ),
                );
              },
            ),
          ),
          actionsPadding: const EdgeInsets.only(bottom: 24, right: 24),
          actions: [
            ElevatedButton(
              onPressed: () {
                Navigator.of(ctx).pop();
                setState(() => _status = 'NOT_OPEN');
                _fetchOpnameData();
              },
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
                elevation: 0,
                backgroundColor: Theme.of(context).primaryColor,
                foregroundColor: Colors.white,
              ),
              child: const Text('Selesai', style: TextStyle(fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );
  }

  Widget _buildMiniStat(String label, dynamic value, {bool isHighlight = false, Color? customColor}) {
    return Column(
      children: [
        Text(label, style: TextStyle(fontSize: 12, color: Colors.grey[500])),
        const SizedBox(height: 4),
        Text('$value', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 16, color: customColor ?? (isHighlight ? Theme.of(context).primaryColor : Colors.black87))),
      ],
    );
  }

  Widget _buildItemCard(dynamic item, {bool isOpening = true}) {
    int id = isOpening ? item['id'] : item['inventoryItem']['id'];
    String name = isOpening ? item['name'] : item['inventoryItem']['name'];
    int defaultStock = isOpening ? item['stock'] : item['inventoryItem']['stock'];
    String unit = isOpening ? item['unit'] : item['inventoryItem']['unit'];
    String? imageUrl = isOpening ? item['imageUrl'] : item['inventoryItem']['imageUrl'];
    int addedStock = (!isOpening && item['addedStock'] != null) ? item['addedStock'] : 0;

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.grey[200]!),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.04),
            blurRadius: 20,
            offset: const Offset(0, 10),
          )
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Image Section
          Expanded(
            flex: 3,
            child: (imageUrl != null && imageUrl.toString().isNotEmpty)
                ? ClipRRect(
                    borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
                    child: Image.network(
                      'http://127.0.0.1:3001$imageUrl',
                      fit: BoxFit.cover,
                      errorBuilder: (c,e,s) => _buildFallbackImage(),
                    ),
                  )
                : _buildFallbackImage(),
          ),
          
          // Form Section
          Expanded(
            flex: 4,
            child: Padding(
              padding: const EdgeInsets.all(12.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  Text(
                    name, 
                    style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15, color: Colors.black87),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (!isOpening && addedStock > 0)
                    Text(
                      'Ditambah Siang: +$addedStock $unit',
                      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.green),
                    ),
                  SizedBox(
                    height: 42,
                    child: TextFormField(
                      initialValue: (_stocks[id] ?? defaultStock).toString(),
                      keyboardType: TextInputType.number,
                      decoration: InputDecoration(
                        labelText: 'Fisik ($unit)',
                        labelStyle: TextStyle(color: Colors.grey[500], fontSize: 12),
                        filled: true,
                        fillColor: Colors.grey[50],
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
                        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: Colors.grey[200]!)),
                        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: Theme.of(context).primaryColor, width: 1.5)),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                      ),
                      onChanged: (val) => _stocks[id] = int.tryParse(val) ?? 0,
                    ),
                  ),
                  SizedBox(
                    height: 42,
                    child: TextFormField(
                      initialValue: _notes[id],
                      decoration: InputDecoration(
                        labelText: 'Catatan',
                        labelStyle: TextStyle(color: Colors.grey[500], fontSize: 12),
                        filled: true,
                        fillColor: Colors.grey[50],
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
                        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: Colors.grey[200]!)),
                        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: Theme.of(context).primaryColor, width: 1.5)),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
                      ),
                      onChanged: (val) => _notes[id] = val,
                    ),
                  )
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFallbackImage() {
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).primaryColor.withOpacity(0.1),
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Center(
        child: Icon(Icons.inventory_2_rounded, size: 40, color: Theme.of(context).primaryColor.withOpacity(0.5)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Scaffold(backgroundColor: Colors.white, body: Center(child: CircularProgressIndicator()));
    }

    if (_status == 'NOT_OPEN') {
      return Scaffold(
        backgroundColor: Colors.grey[50],
        appBar: AppBar(
          title: const Text('Buka Stok (Pagi)', style: TextStyle(color: Colors.black87, fontWeight: FontWeight.w900)),
          backgroundColor: Colors.white,
          elevation: 0,
          scrolledUnderElevation: 0,
          iconTheme: const IconThemeData(color: Colors.black87),
        ),
        body: LayoutBuilder(
          builder: (context, constraints) {
            int crossAxisCount = constraints.maxWidth > 900 ? 4 : constraints.maxWidth > 600 ? 3 : 2;
            return GridView.builder(
              padding: const EdgeInsets.all(20),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: crossAxisCount,
                childAspectRatio: 0.65,
                crossAxisSpacing: 16,
                mainAxisSpacing: 16,
              ),
              itemCount: _inventory.length,
              itemBuilder: (ctx, i) => _buildItemCard(_inventory[i], isOpening: true),
            );
          }
        ),
        bottomNavigationBar: Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: Colors.white,
            boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 20, offset: const Offset(0, -5))],
          ),
          child: ElevatedButton(
            onPressed: _submitOpening,
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.all(20),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
              elevation: 0,
              backgroundColor: Theme.of(context).primaryColor,
              foregroundColor: Colors.white,
            ),
            child: const Text('Submit Stok Awal', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          ),
        ),
      );
    }

    if (_status == 'CLOSING') {
      return Scaffold(
        backgroundColor: Colors.grey[50],
        appBar: AppBar(
          title: const Text('Tutup Stok (Malam)', style: TextStyle(color: Colors.black87, fontWeight: FontWeight.w900)),
          backgroundColor: Colors.white,
          elevation: 0,
          scrolledUnderElevation: 0,
          iconTheme: const IconThemeData(color: Colors.black87),
        ),
        body: LayoutBuilder(
          builder: (context, constraints) {
            int crossAxisCount = constraints.maxWidth > 900 ? 4 : constraints.maxWidth > 600 ? 3 : 2;
            return GridView.builder(
              padding: const EdgeInsets.all(20),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: crossAxisCount,
                childAspectRatio: 0.65,
                crossAxisSpacing: 16,
                mainAxisSpacing: 16,
              ),
              itemCount: _currentOpname!['items'].length,
              itemBuilder: (ctx, i) => _buildItemCard(_currentOpname!['items'][i], isOpening: false),
            );
          }
        ),
        bottomNavigationBar: Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: Colors.white,
            boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 20, offset: const Offset(0, -5))],
          ),
          child: ElevatedButton(
            onPressed: _submitClosing,
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.all(20),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
              elevation: 0,
              backgroundColor: Colors.red[600],
              foregroundColor: Colors.white,
            ),
            child: const Text('Submit Stok Akhir', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
          ),
        ),
      );
    }

    // OPEN state
    return Scaffold(
      backgroundColor: Colors.grey[50],
      appBar: AppBar(
        title: const Text('Status Opname', style: TextStyle(color: Colors.black87, fontWeight: FontWeight.w900)),
        backgroundColor: Colors.white,
        elevation: 0,
        scrolledUnderElevation: 0,
        iconTheme: const IconThemeData(color: Colors.black87),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _fetchOpnameData,
            tooltip: 'Segarkan',
          )
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: Colors.green[50],
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: Colors.green[200]!),
              ),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(color: Colors.green[100], shape: BoxShape.circle),
                    child: Icon(Icons.check_circle_outline, color: Colors.green[700], size: 32),
                  ),
                  const SizedBox(width: 16),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Toko Buka', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 18, color: Colors.green)),
                        SizedBox(height: 4),
                        Text('Stok awal sudah disubmit. Toko sedang beroperasi.', style: TextStyle(color: Colors.green)),
                      ],
                    ),
                  )
                ],
              ),
            ),
            const SizedBox(height: 32),
            const Text('Riwayat Stok Awal (Pagi)', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 18)),
            const SizedBox(height: 16),
            Expanded(
              child: ListView.builder(
                itemCount: _currentOpname!['items'].length,
                itemBuilder: (ctx, i) {
                  final item = _currentOpname!['items'][i];
                  return Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: Colors.grey[200]!),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(item['inventoryItem']['name'], style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                          decoration: BoxDecoration(color: Colors.grey[100], borderRadius: BorderRadius.circular(20)),
                          child: Text('${item['openingStock']} ${item['inventoryItem']['unit']}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                        )
                      ],
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 16),
            Builder(
              builder: (ctx) {
                bool isConfirmed = _currentOpname!['isStockConfirmed'] == true;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    ElevatedButton(
                      onPressed: isConfirmed ? () => setState(() => _status = 'CLOSING') : null,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: isConfirmed ? Colors.red[600] : Colors.grey[400],
                        padding: const EdgeInsets.all(20),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
                        elevation: 0,
                      ),
                      child: const Text('Tutup Stok Hari Ini (Malam)', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16)),
                    ),
                    if (!isConfirmed)
                      const Padding(
                        padding: EdgeInsets.only(top: 12),
                        child: Text(
                          'Harap Konfirmasi Stok di menu Stok terlebih dahulu.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Colors.red, fontWeight: FontWeight.bold, fontSize: 13),
                        ),
                      )
                  ],
                );
              }
            )
          ],
        ),
      ),
    );
  }
}
