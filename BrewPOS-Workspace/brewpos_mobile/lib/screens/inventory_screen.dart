import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';

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
  String _selectedFilter = 'Semua';
  final List<String> _filters = ['Semua', 'Tersedia', 'Menipis', 'Habis'];
  
  String _opnameStatus = 'NOT_OPEN';
  bool _isStockConfirmed = false;

  @override
  void initState() {
    super.initState();
    _fetchInventory();
  }

  Future<void> _fetchInventory() async {
    setState(() => _isLoading = true);
    try {
      final res = await http.get(Uri.parse('http://127.0.0.1:3001/api/inventory'));
      final opnameRes = await http.get(Uri.parse('http://127.0.0.1:3001/api/inventory/opname/today'));
      
      if (res.statusCode == 200) {
        setState(() {
          _inventory = json.decode(res.body);
          if (opnameRes.statusCode == 200) {
            final opData = json.decode(opnameRes.body);
            _opnameStatus = opData['status'];
            if (_opnameStatus == 'OPEN') {
               _isStockConfirmed = opData['opname']['isStockConfirmed'] ?? false;
            } else {
               _isStockConfirmed = false;
            }
          }
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

  Future<void> _confirmStock() async {
    setState(() => _isLoading = true);
    try {
      final res = await http.post(Uri.parse('http://127.0.0.1:3001/api/inventory/opname/confirm-stock'));
      if (res.statusCode == 200) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Data stok telah dikonfirmasi! Anda kini bisa Menutup Stok di menu Opname.', style: TextStyle(color: Colors.white)), backgroundColor: Colors.green));
          _fetchInventory();
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Gagal konfirmasi stok.', style: TextStyle(color: Colors.white)), backgroundColor: Colors.red));
        }
        setState(() => _isLoading = false);
      }
    } catch (e) {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _cancelConfirmStock() async {
    setState(() => _isLoading = true);
    try {
      final res = await http.post(Uri.parse('http://127.0.0.1:3001/api/inventory/opname/cancel-confirm-stock'));
      if (res.statusCode == 200) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Konfirmasi stok dibatalkan. Anda kini bisa merubah data stok kembali.', style: TextStyle(color: Colors.white)), backgroundColor: Colors.orange));
          _fetchInventory();
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Gagal membatalkan konfirmasi.', style: TextStyle(color: Colors.white)), backgroundColor: Colors.red));
        }
        setState(() => _isLoading = false);
      }
    } catch (e) {
      setState(() => _isLoading = false);
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

  Future<void> _addItem(String name, int stock, String unit, XFile? image) async {
    try {
      var request = http.MultipartRequest('POST', Uri.parse('http://127.0.0.1:3001/api/inventory'));
      request.fields['name'] = name;
      request.fields['stock'] = stock.toString();
      request.fields['unit'] = unit;

      if (image != null) {
        final bytes = await image.readAsBytes();
        request.files.add(http.MultipartFile.fromBytes(
          'image',
          bytes,
          filename: image.name,
        ));
      }

      final streamedResponse = await request.send();
      final res = await http.Response.fromStream(streamedResponse);

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
    XFile? selectedImage;
    final ImagePicker picker = ImagePicker();

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setStateSB) {
          return AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
            title: const Text('Barang Baru', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 22)),
            content: SizedBox(
              width: 400,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    InkWell(
                      onTap: () async {
                        final XFile? image = await picker.pickImage(source: ImageSource.gallery);
                        if (image != null) {
                          setStateSB(() {
                            selectedImage = image;
                          });
                        }
                      },
                      child: Container(
                        height: 120,
                        width: double.infinity,
                        decoration: BoxDecoration(
                          color: Colors.grey[100],
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: Colors.grey[300]!, style: BorderStyle.solid),
                        ),
                        child: selectedImage == null
                            ? Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(Icons.add_a_photo, color: Colors.grey[400], size: 32),
                                  const SizedBox(height: 8),
                                  Text('Pilih Foto Barang', style: TextStyle(color: Colors.grey[500])),
                                ],
                              )
                            : ClipRRect(
                                borderRadius: BorderRadius.circular(16),
                                child: Image.network(selectedImage!.path, fit: BoxFit.cover, errorBuilder: (c,e,s) => const Center(child: Text('Foto dipilih'))),
                              ),
                      ),
                    ),
                    const SizedBox(height: 16),
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
                  _addItem(nameCtrl.text.trim(), int.tryParse(stockCtrl.text) ?? 0, unitCtrl.text.trim(), selectedImage);
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
          );
        }
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authProvider);
    final bool isCashier = user?.role == 'CASHIER';

    final filteredInventory = _inventory.where((item) {
      bool matchSearch = item['name'].toString().toLowerCase().contains(_searchQuery.toLowerCase());
      int stock = item['stock'] ?? 0;
      bool matchFilter = true;
      
      if (_selectedFilter == 'Tersedia') matchFilter = stock > 5;
      else if (_selectedFilter == 'Menipis') matchFilter = stock > 0 && stock <= 5;
      else if (_selectedFilter == 'Habis') matchFilter = stock == 0;
      
      return matchSearch && matchFilter;
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
      floatingActionButton: (!isCashier && !(_opnameStatus == 'OPEN' && _isStockConfirmed))
          ? FloatingActionButton.extended(
              heroTag: 'btnAdd',
              onPressed: () => _showAddItemDialog(),
              backgroundColor: Theme.of(context).primaryColor,
              icon: const Icon(Icons.add_rounded, color: Colors.white),
              label: const Text('Barang Baru', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            )
          : null,
      bottomNavigationBar: (_opnameStatus == 'OPEN')
          ? Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.white,
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.05),
                    blurRadius: 15,
                    offset: const Offset(0, -5),
                  )
                ],
              ),
              child: SafeArea(
                child: ElevatedButton.icon(
                  onPressed: _isStockConfirmed ? _cancelConfirmStock : _confirmStock,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: _isStockConfirmed ? Colors.red[50] : Colors.blue[700],
                    foregroundColor: _isStockConfirmed ? Colors.red[700] : Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    elevation: 0,
                  ),
                  icon: Icon(_isStockConfirmed ? Icons.cancel_rounded : Icons.check_circle_outline, size: 24),
                  label: Text(_isStockConfirmed ? 'Batalkan Konfirmasi' : 'Konfirmasi Data Stok', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                ),
              ),
            )
          : null,
      body: Column(
        children: [
          // Search & Filter Section
          Container(
            color: Colors.white,
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Search Bar
                Container(
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
                const SizedBox(height: 16),
                // Filter Chips
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: _filters.map((filter) {
                      bool isSelected = _selectedFilter == filter;
                      return Padding(
                        padding: const EdgeInsets.only(right: 8.0),
                        child: ChoiceChip(
                          label: Text(filter, style: TextStyle(fontWeight: FontWeight.bold, color: isSelected ? Colors.white : Colors.black87)),
                          selected: isSelected,
                          selectedColor: Theme.of(context).primaryColor,
                          backgroundColor: Colors.white,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20), side: BorderSide(color: isSelected ? Theme.of(context).primaryColor : Colors.grey[300]!)),
                          onSelected: (selected) {
                            if (selected) {
                              setState(() => _selectedFilter = filter);
                            }
                          },
                        ),
                      );
                    }).toList(),
                  ),
                ),
              ],
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
                          
                          Color statusColor = Colors.green;
                          String statusText = 'Tersedia';
                          IconData statusIcon = Icons.check_circle_rounded;

                          if (stock == 0) {
                            statusColor = Colors.red;
                            statusText = 'Habis';
                            statusIcon = Icons.cancel_rounded;
                          } else if (stock <= 5) {
                            statusColor = Colors.orange;
                            statusText = 'Menipis';
                            statusIcon = Icons.warning_rounded;
                          }

                          return Container(
                            margin: const EdgeInsets.only(bottom: 20),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(28),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withOpacity(0.03),
                                  blurRadius: 24,
                                  offset: const Offset(0, 12),
                                )
                              ],
                            ),
                            child: Material(
                              color: Colors.transparent,
                              child: InkWell(
                                borderRadius: BorderRadius.circular(28),
                                hoverColor: Theme.of(context).primaryColor.withOpacity(0.05),
                                splashColor: Theme.of(context).primaryColor.withOpacity(0.1),
                                highlightColor: Theme.of(context).primaryColor.withOpacity(0.05),
                                onTap: () {
                                  if (!isCashier) {
                                    if (_opnameStatus == 'OPEN' && _isStockConfirmed) {
                                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Stok sudah dikonfirmasi. Batalkan konfirmasi untuk mengubah data.'), backgroundColor: Colors.red));
                                    } else {
                                      _showAdjustStockDialog(item);
                                    }
                                  }
                                },
                                child: Padding(
                                  padding: const EdgeInsets.all(20),
                                  child: Row(
                                    crossAxisAlignment: CrossAxisAlignment.center,
                                    children: [
                                      // Premium Image Container
                                      Hero(
                                        tag: 'item_img_${item['id']}',
                                        child: Container(
                                          width: 90,
                                          height: 90,
                                          decoration: BoxDecoration(
                                            color: Theme.of(context).primaryColor.withOpacity(0.06),
                                            borderRadius: BorderRadius.circular(24),
                                          ),
                                          clipBehavior: Clip.antiAlias,
                                          child: (item['imageUrl'] != null && item['imageUrl'].toString().isNotEmpty)
                                              ? Image.network(
                                                  'http://127.0.0.1:3001${item['imageUrl']}',
                                                  fit: BoxFit.cover,
                                                  errorBuilder: (c,e,s) => Icon(Icons.local_cafe_rounded, color: Theme.of(context).primaryColor.withOpacity(0.5), size: 40),
                                                )
                                              : Icon(Icons.local_cafe_rounded, color: Theme.of(context).primaryColor.withOpacity(0.5), size: 40),
                                        ),
                                      ),
                                      const SizedBox(width: 24),
                                      
                                      // Content Section
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            // Soft Badge
                                            Container(
                                              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                              decoration: BoxDecoration(
                                                color: statusColor.withOpacity(0.12),
                                                borderRadius: BorderRadius.circular(10),
                                              ),
                                              child: Row(
                                                mainAxisSize: MainAxisSize.min,
                                                children: [
                                                  Icon(statusIcon, color: statusColor, size: 12),
                                                  const SizedBox(width: 6),
                                                  Text(statusText, style: TextStyle(color: statusColor, fontSize: 11, fontWeight: FontWeight.w800)),
                                                ],
                                              ),
                                            ),
                                            const SizedBox(height: 10),
                                            // Title
                                            Text(
                                              item['name'],
                                              style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 17, color: Colors.black87, height: 1.2),
                                              maxLines: 2,
                                              overflow: TextOverflow.ellipsis,
                                            ),
                                            const SizedBox(height: 8),
                                            // Stock Typography
                                            Row(
                                              crossAxisAlignment: CrossAxisAlignment.baseline,
                                              textBaseline: TextBaseline.alphabetic,
                                              children: [
                                                Text(
                                                  '$stock',
                                                  style: TextStyle(
                                                    fontWeight: FontWeight.w900,
                                                    fontSize: 28,
                                                    color: stock == 0 ? Colors.red : Theme.of(context).primaryColor,
                                                    letterSpacing: -1,
                                                  ),
                                                ),
                                                const SizedBox(width: 6),
                                                Text(
                                                  unit,
                                                  style: TextStyle(
                                                    fontSize: 14,
                                                    color: Colors.grey[500],
                                                    fontWeight: FontWeight.w700,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ],
                                        ),
                                      ),
                                      
                                      // Action Icon (if headbar)
                                      if (!isCashier && !(_opnameStatus == 'OPEN' && _isStockConfirmed)) ...[
                                        const SizedBox(width: 12),
                                        Container(
                                          padding: const EdgeInsets.all(12),
                                          decoration: BoxDecoration(
                                            color: Colors.grey[50],
                                            shape: BoxShape.circle,
                                            border: Border.all(color: Colors.grey[200]!)
                                          ),
                                          child: Icon(Icons.edit_note_rounded, color: Colors.grey[400], size: 24),
                                        )
                                      ]
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          );
                        },
                      )
          ),
        ],
      ),
    );
  }
}
