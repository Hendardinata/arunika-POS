import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/auth_provider.dart';

class InventoryScreen extends ConsumerStatefulWidget {
  const InventoryScreen({super.key});

  @override
  ConsumerState<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends ConsumerState<InventoryScreen> {
  List<dynamic> _inventory = [];
  bool _isLoading = true;
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    _fetchInventory();
  }

  Future<void> _fetchInventory() async {
    setState(() => _isLoading = true);
    try {
      final res = await http.get(Uri.parse('http://127.0.0.1:3001/api/inventory'));
      if (res.statusCode == 200) {
        setState(() {
          _inventory = json.decode(res.body);
          _isLoading = false;
        });
      } else {
        setState(() => _isLoading = false);
      }
    } catch (e) {
      setState(() => _isLoading = false);
      debugPrint('Error fetching inventory: $e');
    }
  }

  Future<void> _adjustStock(int id, int quantity, String type, String notes) async {
    try {
      final res = await http.put(
        Uri.parse('http://127.0.0.1:3001/api/inventory/$id/adjust'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'quantity': quantity, 'type': type, 'notes': notes}),
      );
      if (res.statusCode == 200) {
        _fetchInventory();
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Stok berhasil diupdate', style: TextStyle(color: Colors.white)), backgroundColor: Colors.green));
      } else {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Gagal update stok', style: TextStyle(color: Colors.white)), backgroundColor: Colors.red));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Error jaringan', style: TextStyle(color: Colors.white)), backgroundColor: Colors.red));
    }
  }

  Future<void> _addItem(String name, int stock, String unit) async {
    try {
      final res = await http.post(
        Uri.parse('http://127.0.0.1:3001/api/inventory'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'name': name, 'stock': stock, 'unit': unit}),
      );
      if (res.statusCode == 201) {
        _fetchInventory();
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Barang berhasil ditambahkan', style: TextStyle(color: Colors.white)), backgroundColor: Colors.green));
      } else {
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Gagal tambah barang', style: TextStyle(color: Colors.white)), backgroundColor: Colors.red));
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Error jaringan', style: TextStyle(color: Colors.white)), backgroundColor: Colors.red));
    }
  }

  void _showAdjustStockDialog(dynamic item) {
    int qty = 1;
    String type = 'IN';
    final TextEditingController noteCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setStateSB) {
          return AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
            title: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Sesuaikan Stok', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 22)),
                const SizedBox(height: 4),
                Text(item['name'], style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Theme.of(context).primaryColor)),
              ],
            ),
            content: SizedBox(
              width: 400,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // IN / OUT Toggle
                  Container(
                    decoration: BoxDecoration(
                      color: Colors.grey[100],
                      borderRadius: BorderRadius.circular(16),
                    ),
                    padding: const EdgeInsets.all(4),
                    child: Row(
                      children: [
                        Expanded(
                          child: InkWell(
                            onTap: () => setStateSB(() => type = 'IN'),
                            borderRadius: BorderRadius.circular(12),
                            child: Container(
                              padding: const EdgeInsets.symmetric(vertical: 12),
                              decoration: BoxDecoration(
                                color: type == 'IN' ? Colors.white : Colors.transparent,
                                borderRadius: BorderRadius.circular(12),
                                boxShadow: type == 'IN' ? [BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 8, offset: const Offset(0, 2))] : [],
                              ),
                              child: Center(
                                child: Text('Masuk (+)', style: TextStyle(fontWeight: FontWeight.bold, color: type == 'IN' ? Colors.green[700] : Colors.grey)),
                              ),
                            ),
                          ),
                        ),
                        Expanded(
                          child: InkWell(
                            onTap: () => setStateSB(() => type = 'OUT'),
                            borderRadius: BorderRadius.circular(12),
                            child: Container(
                              padding: const EdgeInsets.symmetric(vertical: 12),
                              decoration: BoxDecoration(
                                color: type == 'OUT' ? Colors.white : Colors.transparent,
                                borderRadius: BorderRadius.circular(12),
                                boxShadow: type == 'OUT' ? [BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 8, offset: const Offset(0, 2))] : [],
                              ),
                              child: Center(
                                child: Text('Keluar (-)', style: TextStyle(fontWeight: FontWeight.bold, color: type == 'OUT' ? Colors.red[700] : Colors.grey)),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 32),
                  // Counter
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      InkWell(
                        onTap: () { if (qty > 1) setStateSB(() => qty--); },
                        borderRadius: BorderRadius.circular(30),
                        child: Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(color: Colors.grey[100], shape: BoxShape.circle),
                          child: Icon(Icons.remove, color: Colors.grey[700]),
                        ),
                      ),
                      const SizedBox(width: 32),
                      Text('$qty', style: const TextStyle(fontSize: 36, fontWeight: FontWeight.w900, color: Colors.black87)),
                      const SizedBox(width: 32),
                      InkWell(
                        onTap: () => setStateSB(() => qty++),
                        borderRadius: BorderRadius.circular(30),
                        child: Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(color: Theme.of(context).primaryColor.withOpacity(0.1), shape: BoxShape.circle),
                          child: Icon(Icons.add, color: Theme.of(context).primaryColor),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  // Note Field
                  TextField(
                    controller: noteCtrl,
                    decoration: InputDecoration(
                      labelText: 'Catatan (opsional)',
                      labelStyle: TextStyle(color: Colors.grey[500]),
                      filled: true,
                      fillColor: Colors.grey[50],
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
                      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Colors.grey[200]!)),
                      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Theme.of(context).primaryColor, width: 2)),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                    ),
                  ),
                ],
              ),
            ),
            actionsPadding: const EdgeInsets.only(bottom: 24, right: 24, left: 24),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx), 
                style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30))),
                child: const Text('Batal', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.grey))
              ),
              ElevatedButton(
                onPressed: () {
                  Navigator.pop(ctx);
                  _adjustStock(item['id'], qty, type, noteCtrl.text);
                },
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
                  elevation: 0,
                  backgroundColor: Theme.of(context).primaryColor,
                  foregroundColor: Colors.white,
                ),
                child: const Text('Simpan Stok', style: TextStyle(fontWeight: FontWeight.bold)),
              )
            ],
          );
        }
      ),
    );
  }

  void _showAddItemDialog() {
    final nameCtrl = TextEditingController();
    final stockCtrl = TextEditingController(text: '0');
    final unitCtrl = TextEditingController(text: 'pcs');

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        title: const Text('Barang Baru', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 22)),
        content: SizedBox(
          width: 400,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: nameCtrl, 
                decoration: InputDecoration(
                  labelText: 'Nama Barang',
                  filled: true,
                  fillColor: Colors.grey[50],
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
                  enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Colors.grey[200]!)),
                  focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Theme.of(context).primaryColor, width: 2)),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                )
              ),
              const SizedBox(height: 16),
              TextField(
                controller: stockCtrl, 
                keyboardType: TextInputType.number, 
                decoration: InputDecoration(
                  labelText: 'Stok Awal',
                  filled: true,
                  fillColor: Colors.grey[50],
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
                  enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Colors.grey[200]!)),
                  focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Theme.of(context).primaryColor, width: 2)),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                )
              ),
              const SizedBox(height: 16),
              TextField(
                controller: unitCtrl, 
                decoration: InputDecoration(
                  labelText: 'Satuan (misal: pcs, kg, cup)',
                  filled: true,
                  fillColor: Colors.grey[50],
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide.none),
                  enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Colors.grey[200]!)),
                  focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(16), borderSide: BorderSide(color: Theme.of(context).primaryColor, width: 2)),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                )
              ),
            ],
          ),
        ),
        actionsPadding: const EdgeInsets.only(bottom: 24, right: 24, left: 24),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx), 
            style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30))),
            child: const Text('Batal', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.grey))
          ),
          ElevatedButton(
            onPressed: () {
              if (nameCtrl.text.trim().isEmpty) return;
              Navigator.pop(ctx);
              _addItem(nameCtrl.text.trim(), int.tryParse(stockCtrl.text) ?? 0, unitCtrl.text.trim());
            },
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 12),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
              elevation: 0,
              backgroundColor: Theme.of(context).primaryColor,
              foregroundColor: Colors.white,
            ),
            child: const Text('Simpan Data', style: TextStyle(fontWeight: FontWeight.bold)),
          )
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authProvider);
    final bool isCashier = user?.role == 'CASHIER';

    final filteredInventory = _inventory.where((item) {
      return item['name'].toString().toLowerCase().contains(_searchQuery.toLowerCase());
    }).toList();

    return Scaffold(
      backgroundColor: const Color(0xFFFAFAFA),
      appBar: AppBar(
        title: const Text('Stok Barang', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.black87)),
        backgroundColor: Colors.white,
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.black87),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1.0),
          child: Container(color: Colors.grey[200], height: 1.0),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            onPressed: _fetchInventory,
            tooltip: 'Segarkan',
          )
        ],
      ),
      floatingActionButton: isCashier 
          ? null 
          : FloatingActionButton.extended(
              onPressed: () => _showAddItemDialog(),
              backgroundColor: Theme.of(context).primaryColor,
              icon: const Icon(Icons.add_rounded, color: Colors.white),
              label: const Text('Barang Baru', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
      body: Column(
        children: [
          // Search Bar Section
          Container(
            color: Colors.white,
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
            child: Container(
              decoration: BoxDecoration(
                color: Colors.grey[100],
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: Colors.grey[200]!),
              ),
              child: TextField(
                decoration: InputDecoration(
                  hintText: 'Cari barang di gudang...',
                  hintStyle: TextStyle(color: Colors.grey[500]),
                  prefixIcon: Icon(Icons.search_rounded, color: Colors.grey[500]),
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                ),
                onChanged: (val) {
                  setState(() {
                    _searchQuery = val;
                  });
                },
              ),
            ),
          ),

          // Inventory List Section
          Expanded(
            child: _isLoading
                ? Center(child: CircularProgressIndicator(color: Theme.of(context).primaryColor))
                : filteredInventory.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Container(
                              padding: const EdgeInsets.all(24),
                              decoration: BoxDecoration(
                                color: Colors.grey[100],
                                shape: BoxShape.circle,
                              ),
                              child: Icon(Icons.inventory_2_rounded, size: 64, color: Colors.grey[400]),
                            ),
                            const SizedBox(height: 24),
                            Text('Barang tidak ditemukan', style: TextStyle(color: Colors.grey[600], fontSize: 18, fontWeight: FontWeight.bold)),
                            const SizedBox(height: 8),
                            Text('Coba kata kunci lain atau tambahkan barang.', style: TextStyle(color: Colors.grey[500], fontSize: 14)),
                          ],
                        ),
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                        itemCount: filteredInventory.length,
                        itemBuilder: (context, index) {
                          final item = filteredInventory[index];
                          final int stock = item['stock'] ?? 0;
                          final String unit = item['unit'] ?? 'pcs';
                          
                          // Determine status
                          Color statusColor = Colors.green;
                          Color statusBgColor = Colors.green.withOpacity(0.1);
                          String statusText = 'Tersedia';
                          IconData statusIcon = Icons.check_circle_rounded;

                          if (stock == 0) {
                            statusColor = Colors.red;
                            statusBgColor = Colors.red.withOpacity(0.1);
                            statusText = 'Habis';
                            statusIcon = Icons.cancel_rounded;
                          } else if (stock <= 5) {
                            statusColor = Colors.orange;
                            statusBgColor = Colors.orange.withOpacity(0.1);
                            statusText = 'Menipis';
                            statusIcon = Icons.warning_rounded;
                          }

                          return GestureDetector(
                            onTap: () {
                              if (!isCashier) {
                                _showAdjustStockDialog(item);
                              }
                            },
                            child: Container(
                              margin: const EdgeInsets.only(bottom: 16),
                              padding: const EdgeInsets.all(20),
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
                              child: Row(
                                children: [
                                  // Icon Box
                                  Container(
                                    padding: const EdgeInsets.all(16),
                                    decoration: BoxDecoration(
                                      color: Theme.of(context).primaryColor.withOpacity(0.08),
                                      borderRadius: BorderRadius.circular(16),
                                    ),
                                    child: Icon(Icons.inventory_2_outlined, color: Theme.of(context).primaryColor, size: 28),
                                  ),
                                  const SizedBox(width: 20),
                                  
                                  // Item Info
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          item['name'], 
                                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 17, color: Colors.black87),
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                        const SizedBox(height: 8),
                                        Row(
                                          children: [
                                            Container(
                                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                              decoration: BoxDecoration(
                                                color: statusBgColor,
                                                borderRadius: BorderRadius.circular(8),
                                              ),
                                              child: Row(
                                                mainAxisSize: MainAxisSize.min,
                                                children: [
                                                  Icon(statusIcon, color: statusColor, size: 12),
                                                  const SizedBox(width: 4),
                                                  Text(statusText, style: TextStyle(color: statusColor, fontSize: 11, fontWeight: FontWeight.bold)),
                                                ],
                                              ),
                                            ),
                                          ],
                                        ),
                                      ],
                                    ),
                                  ),
                                  
                                  // Stock Quantity
                                  const SizedBox(width: 16),
                                  Column(
                                    crossAxisAlignment: CrossAxisAlignment.end,
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Text(
                                        '$stock',
                                        style: TextStyle(
                                          fontWeight: FontWeight.w900,
                                          fontSize: 24,
                                          color: stock == 0 ? Colors.red : Colors.black87,
                                        ),
                                      ),
                                      Text(
                                        unit,
                                        style: TextStyle(
                                          fontSize: 13,
                                          color: Colors.grey[500],
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ],
                                  ),
                                  if (!isCashier) ...[
                                    const SizedBox(width: 12),
                                    const Icon(Icons.edit_note, color: Colors.grey),
                                  ]
                                ],
                              ),
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}
