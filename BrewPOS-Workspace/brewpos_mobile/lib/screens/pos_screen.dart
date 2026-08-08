import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../providers/menu_provider.dart';
import '../providers/cart_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/shift_provider.dart';
import '../models/shift.dart';
import '../database/db_helper.dart';
import '../models/menu.dart';
import 'receipt_dialog.dart';
import 'login_screen.dart';
import 'mystery_box_dialog.dart';
import 'lucky_spin_dialog.dart';
String formatRp(num amount) {
  String str = amount.toStringAsFixed(0);
  return str.replaceAllMapped(RegExp(r'(\d{1,3})(?=(\d{3})+(?!\d))'), (Match m) => '${m[1]}.');
}

class PosScreen extends ConsumerStatefulWidget {
  const PosScreen({super.key});

  @override
  ConsumerState<PosScreen> createState() => _PosScreenState();
}

class _PosScreenState extends ConsumerState<PosScreen> {
  final TextEditingController _nicknameController = TextEditingController();
  final TextEditingController _searchController = TextEditingController();
  Map<String, dynamic>? _customerProfile;
  bool _isLoadingCustomer = false;
  bool _isCustomerNotFound = false;
  List<dynamic> _availableRewards = [];
  Map<String, dynamic>? _selectedReward;
  
  String _selectedCategory = 'Semua';
  bool _isCartExpanded = false;
  final ValueNotifier<int> _uiRebuilder = ValueNotifier<int>(0);

  @override
  void setState(VoidCallback fn) {
    if (mounted) {
      super.setState(fn);
      _uiRebuilder.value++;
    }
  }

  @override
  void initState() {
    super.initState();
    _fetchRewards();
    _nicknameController.addListener(() {
      if (_nicknameController.text.trim().isEmpty) {
        if (_customerProfile != null || _isCustomerNotFound) {
          setState(() {
            _customerProfile = null;
            _selectedReward = null;
            _isCustomerNotFound = false;
          });
        }
      } else {
        if (_isCustomerNotFound) {
          setState(() => _isCustomerNotFound = false);
        }
      }
    });
  }

  @override
  void dispose() {
    _nicknameController.dispose();
    _searchController.dispose();
    _uiRebuilder.dispose();
    super.dispose();
  }

  Future<void> _fetchRewards() async {
    try {
      final res = await http.get(Uri.parse('http://100.77.229.76:3001/api/gamification/rewards'));
      if (!mounted) return;
      if (res.statusCode == 200) {
        setState(() {
          _availableRewards = json.decode(res.body);
        });
      }
    } catch (e) {
      debugPrint('Failed to fetch rewards: $e');
    }
  }

  Future<void> _searchCustomer() async {
    final nickname = _nicknameController.text.trim();
    if (nickname.isEmpty) return;

    setState(() { _isLoadingCustomer = true; _customerProfile = null; _selectedReward = null; _isCustomerNotFound = false; });
    
    try {
      final res = await http.get(Uri.parse('http://100.77.229.76:3001/api/customers/search?nickname=$nickname'));
      if (!mounted) return;
      if (res.statusCode == 200) {
        setState(() { _customerProfile = json.decode(res.body); });
      } else {
        setState(() { _isCustomerNotFound = true; });
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      if (mounted) setState(() { _isLoadingCustomer = false; });
    }
  }

  Future<void> _doLuckySpin(int customerId) async {
    try {
      final res = await http.post(
        Uri.parse('http://100.77.229.76:3001/api/gamification/spin'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'customerId': customerId}),
      );
      if (!mounted) return;
      if (res.statusCode == 200) {
        final data = json.decode(res.body);
        setState(() {
          _customerProfile = data['customer'];
        });
        if (mounted) {
          await showDialog(
            context: context,
            builder: (ctx) => LuckySpinDialog(
              rewardName: data['rewardName'],
              bonusPoints: data['bonusPoints'],
              bonusXp: data['bonusXp'],
            ),
          );
        }
      } else {
        final err = json.decode(res.body);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err['error'] ?? 'Gagal spin')));
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Terjadi kesalahan jaringan')));
      }
    }
  }

  Widget _buildProductImage(Menu menu) {
    if (menu.imageUrl != null && menu.imageUrl!.isNotEmpty) {
      return Expanded(
        child: Container(
          width: double.infinity,
          decoration: const BoxDecoration(
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          clipBehavior: Clip.antiAlias,
          child: Image.network(
            'http://100.77.229.76:3001${menu.imageUrl}',
            fit: BoxFit.cover,
            errorBuilder: (context, error, stackTrace) => _buildFallbackImage(menu),
          ),
        ),
      );
    }
    return _buildFallbackImage(menu);
  }

  Widget _buildFallbackImage(Menu menu) {
    final colors = [
      Colors.brown[600]!, 
      Colors.orange[400]!, 
      Theme.of(context).primaryColor, 
      Colors.blueGrey[600]!,
      Colors.deepOrange[400]!
    ];
    final color = colors[menu.id % colors.length];
    
    return Expanded(
      child: Container(
        width: double.infinity,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [color.withOpacity(0.8), color],
          ),
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: Center(
          child: Icon(
            menu.categoryName == 'Minuman' ? Icons.local_cafe_rounded : Icons.fastfood_rounded, 
            size: 48, 
            color: Colors.white.withOpacity(0.9)
          ),
        ),
      ),
    );
  }

  Widget _buildCheckoutPanel(BuildContext context, bool isPhone, WidgetRef ref) {
    final cart = ref.watch(cartProvider);
    final cartNotifier = ref.read(cartProvider.notifier);
    final finalTotal = cartNotifier.totalAmount;
    
    return Container(
      width: isPhone ? double.infinity : 300,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: isPhone ? const BorderRadius.vertical(top: Radius.circular(28)) : null,
        border: isPhone ? null : Border(left: BorderSide(color: Colors.grey[200]!, width: 1)),
      ),
      child: SafeArea(
        child: Column(
          children: [
            // Header Pesanan
            Padding(
              padding: const EdgeInsets.all(20.0).copyWith(bottom: 0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Pesanan', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  if (!isPhone)
                    IconButton(
                      icon: const Icon(Icons.close),
                      onPressed: () => setState(() => _isCartExpanded = false),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            // Customer Information (Compact to match design)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SizedBox(height: 12),
                  // Search Field
                  Container(
                    height: 44,
                    decoration: BoxDecoration(
                      color: Colors.grey[50],
                      border: Border.all(color: Colors.grey[300]!),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Row(
                      children: [
                        const SizedBox(width: 12),
                        Icon(Icons.person_outline, color: Colors.grey[500], size: 20),
                        const SizedBox(width: 8),
                        Expanded(
                          child: TextField(
                            controller: _nicknameController,
                            style: const TextStyle(fontSize: 14),
                            decoration: InputDecoration(
                              hintText: 'Cari Pelanggan',
                              hintStyle: TextStyle(color: Colors.grey[400], fontSize: 14),
                              border: InputBorder.none,
                              isDense: true,
                            ),
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.search, color: Colors.grey, size: 20),
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(),
                          onPressed: _isLoadingCustomer ? null : _searchCustomer,
                        ),
                        const SizedBox(width: 8),
                      ],
                    ),
                  ),
                  
                  // Register Button if not found
                  if (_isCustomerNotFound)
                    InkWell(
                      onTap: () {
                        setState(() {
                          _customerProfile = {
                            'nickname': _nicknameController.text.trim(),
                            'points': 0,
                            'level': 1,
                            'xp': 0,
                            'streakCount': 0
                          };
                          _isCustomerNotFound = false;
                        });
                      },
                      child: Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        margin: const EdgeInsets.only(top: 8),
                        decoration: BoxDecoration(
                          color: Theme.of(context).primaryColor.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: Theme.of(context).primaryColor.withOpacity(0.2)!),
                        ),
                        child: Center(
                          child: Text('+ Tambahkan Baru', style: TextStyle(color: Theme.of(context).primaryColor, fontSize: 13, fontWeight: FontWeight.bold)),
                        ),
                      ),
                    ),

                  // Compact Profile Display if exists
                  if (_customerProfile != null)
                    Container(
                      margin: const EdgeInsets.only(top: 8),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: Theme.of(context).primaryColor.withOpacity(0.05),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Theme.of(context).primaryColor.withOpacity(0.2)!),
                      ),
                      child: Column(
                        children: [
                          Row(
                            children: [
                              CircleAvatar(
                                radius: 14,
                                backgroundColor: Theme.of(context).primaryColor,
                                child: Text(_nicknameController.text.isNotEmpty ? _nicknameController.text.substring(0,1).toUpperCase() : 'U', style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold)),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text('${_customerProfile!['nickname']} • ${_customerProfile!['points']} Pts', style: TextStyle(fontWeight: FontWeight.bold, color: Theme.of(context).primaryColor, fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis),
                              ),
                              if (_customerProfile!['points'] >= 50)
                                InkWell(
                                  onTap: () => _doLuckySpin(_customerProfile!['id']),
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                    decoration: BoxDecoration(color: Theme.of(context).primaryColor, borderRadius: BorderRadius.circular(6)),
                                    child: const Text('Spin!', style: TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold)),
                                  ),
                                )
                            ],
                          ),
                          if (_availableRewards.isNotEmpty && _customerProfile!['points'] > 0) ...[
                            const SizedBox(height: 6),
                            SizedBox(
                              height: 24,
                              child: DropdownButton<Map<String, dynamic>>(
                                isExpanded: true,
                                isDense: true,
                                value: _selectedReward,
                                hint: Text('Tukar Reward...', style: TextStyle(fontSize: 12, color: Theme.of(context).primaryColor.withOpacity(0.8))),
                                underline: const SizedBox(),
                                iconSize: 16,
                                items: [
                                  const DropdownMenuItem<Map<String, dynamic>>(value: null, child: Text('Tidak pakai reward', style: TextStyle(fontSize: 12))),
                                  ..._availableRewards.where((r) => r['pointsRequired'] <= _customerProfile!['points']).map((r) => DropdownMenuItem<Map<String, dynamic>>(value: r, child: Text('${r['name']} (-${r['pointsRequired']})', style: const TextStyle(fontSize: 12))))
                                ],
                                onChanged: (val) => setState(() => _selectedReward = val),
                              ),
                            ),
                          ]
                        ],
                      ),
                    ),
                  

                ],
              ),
            ),
            
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 16),
              child: Divider(height: 1, color: Color(0xFFEEEEEE)),
            ),
            
            // Order Details List
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20.0).copyWith(bottom: 12),
              child: const Row(
                children: [
                  Text('Detail pesanan', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                ],
              ),
            ),
            Expanded(
              child: cart.isEmpty 
              ? Center(child: Text('Belum ada pesanan', style: TextStyle(color: Colors.grey[400])))
              : ListView.builder(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                itemCount: cart.length,
                itemBuilder: (context, index) {
                  final item = cart[index];
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        // Small image thumb (modern)
                        Container(
                          width: 50,
                          height: 50,
                          decoration: BoxDecoration(
                            color: Theme.of(context).primaryColor.withOpacity(0.1),
                            borderRadius: BorderRadius.circular(12),
                          ),
                            clipBehavior: Clip.antiAlias,
                            child: (item.menu.imageUrl != null && item.menu.imageUrl!.isNotEmpty)
                                ? Image.network(
                                    'http://100.77.229.76:3001${item.menu.imageUrl}',
                                    fit: BoxFit.cover,
                                    errorBuilder: (ctx, err, stack) => Icon(
                                      item.menu.categoryName == 'Minuman' ? Icons.local_cafe_rounded : Icons.fastfood_rounded, 
                                      color: Theme.of(context).primaryColor, 
                                      size: 24
                                    ),
                                  )
                                : Icon(
                                    item.menu.categoryName == 'Minuman' ? Icons.local_cafe_rounded : Icons.fastfood_rounded, 
                                    color: Theme.of(context).primaryColor, 
                                    size: 24
                                  ),
                          ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(item.menu.name, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15), maxLines: 1, overflow: TextOverflow.ellipsis),
                              const SizedBox(height: 4),
                              Text('Rp ${formatRp(item.menu.price)}', style: TextStyle(color: Theme.of(context).primaryColor, fontSize: 14, fontWeight: FontWeight.bold)),
                            ],
                          ),
                        ),
                        // Modern + - controls
                        Container(
                          padding: const EdgeInsets.all(4),
                          decoration: BoxDecoration(
                            color: Colors.grey[100],
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(color: Colors.grey[200]!),
                          ),
                          child: Row(
                            children: [
                              InkWell(
                                onTap: () => cartNotifier.decreaseQuantity(item.menu),
                                borderRadius: BorderRadius.circular(20),
                                child: Container(
                                  width: 28, height: 28,
                                  decoration: BoxDecoration(shape: BoxShape.circle, color: Colors.white, boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 4)]),
                                  child: const Icon(Icons.remove_rounded, size: 16, color: Colors.black87),
                                ),
                              ),
                              SizedBox(
                                width: 32,
                                child: Text('${item.quantity}', textAlign: TextAlign.center, style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15)),
                              ),
                              InkWell(
                                onTap: () => cartNotifier.addToCart(item.menu),
                                borderRadius: BorderRadius.circular(20),
                                child: Container(
                                  width: 28, height: 28,
                                  decoration: BoxDecoration(shape: BoxShape.circle, color: Theme.of(context).primaryColor, boxShadow: [BoxShadow(color: Theme.of(context).primaryColor.withOpacity(0.3), blurRadius: 4)]),
                                  child: const Icon(Icons.add_rounded, size: 16, color: Colors.white),
                                ),
                              ),
                            ],
                          ),
                        )
                      ],
                    ),
                  );
                },
              ),
            ),
            
            // Totals
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Total', style: TextStyle(fontSize: 16, color: Colors.grey)),
                      Text('Rp ${formatRp(finalTotal)}', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Theme.of(context).primaryColor)),
                    ],
                  ),
                  const SizedBox(height: 18),
                  SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: ElevatedButton(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Theme.of(context).primaryColor,
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                        elevation: 0,
                      ),
                      onPressed: cart.isEmpty ? null : () => _handleCheckout(finalTotal),
                      child: const Text('Bayar', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                    ),
                  ),
                ],
              ),
            )
          ],
        ),
      ),
    );
  }

  Future<void> _handleCheckout(int finalTotal) async {
    final cart = ref.read(cartProvider);
    final cartNotifier = ref.read(cartProvider.notifier);
    final nickname = _nicknameController.text.trim();
    
    String selectedPaymentMethod = 'CASH';
    final paymentDisplayMap = {'CASH': 'TUNAI', 'QRIS': 'QRIS', 'CARD': 'KARTU'};

    TextEditingController cashReceivedController = TextEditingController();
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(builder: (context, setStateDialog) {
          return Dialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            backgroundColor: Colors.white,
            elevation: 0,
            child: Container(
              width: 450,
              padding: const EdgeInsets.all(32),
              child: AnimatedSize(
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeInOut,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Header with close button
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Metode Pembayaran', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.black87)),
                        IconButton(
                          icon: const Icon(Icons.close, color: Colors.grey),
                          onPressed: () => Navigator.pop(ctx, null),
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(),
                        ),
                      ],
                    ),
                    const SizedBox(height: 24),
                    
                    // Bill Summary (Clean text style matching the image)

                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('Total', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.grey[600])),
                        Text('Rp ${formatRp(finalTotal)}', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: Theme.of(context).primaryColor)),
                      ],
                    ),
                    const SizedBox(height: 32),
                    
                    // Payment Methods Selection (Clean thin borders)
                    Row(
                      children: ['CASH', 'QRIS', 'CARD'].map((method) {
                        final isSelected = selectedPaymentMethod == method;
                        return Expanded(
                          child: Padding(
                            padding: EdgeInsets.only(right: method == 'CARD' ? 0 : 12.0),
                            child: InkWell(
                              onTap: () => setStateDialog(() => selectedPaymentMethod = method),
                              borderRadius: BorderRadius.circular(16),
                              child: AnimatedContainer(
                                duration: const Duration(milliseconds: 200),
                                padding: const EdgeInsets.symmetric(vertical: 20),
                                decoration: BoxDecoration(
                                  color: isSelected ? Theme.of(context).primaryColor.withOpacity(0.08) : Colors.white,
                                  border: Border.all(
                                    color: isSelected ? Theme.of(context).primaryColor : Colors.grey[200]!,
                                    width: isSelected ? 2 : 1
                                  ),
                                  borderRadius: BorderRadius.circular(16),
                                  boxShadow: isSelected ? [BoxShadow(color: Theme.of(context).primaryColor.withOpacity(0.2), blurRadius: 8, offset: const Offset(0, 4))] : [],
                                ),
                                child: Column(
                                  children: [
                                    Icon(
                                      method == 'CASH' ? Icons.payments_rounded : method == 'QRIS' ? Icons.qr_code_2_rounded : Icons.credit_card_rounded,
                                      color: isSelected ? Theme.of(context).primaryColor : Colors.grey[400],
                                      size: 32,
                                    ),
                                    const SizedBox(height: 8),
                                    Text(
                                      paymentDisplayMap[method]!, 
                                      style: TextStyle(
                                        fontWeight: isSelected ? FontWeight.w900 : FontWeight.w600, 
                                        color: isSelected ? Theme.of(context).primaryColor : Colors.grey[500], 
                                        fontSize: 13
                                      )
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                    
                    // Cash Received Input
                    if (selectedPaymentMethod == 'CASH') ...[
                      const SizedBox(height: 24),
                      Text('Nominal Diterima', style: TextStyle(fontSize: 14, color: Colors.grey[600])),
                      const SizedBox(height: 8),
                      TextField(
                        controller: cashReceivedController,
                        keyboardType: TextInputType.number,
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                        decoration: InputDecoration(
                          prefixText: 'Rp ',
                          prefixStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.black87),
                          filled: true,
                          fillColor: Colors.white,
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: Colors.grey[200]!)),
                          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: Colors.grey[200]!)),
                          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: Theme.of(context).primaryColor, width: 2)),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                        ),
                        onChanged: (val) {
                          if (val.isEmpty) {
                            setStateDialog(() {});
                            return;
                          }
                          final cleanStr = val.replaceAll(RegExp(r'[^\d]'), '');
                          if (cleanStr.isEmpty) {
                            cashReceivedController.clear();
                            setStateDialog(() {});
                            return;
                          }
                          String result = '';
                          int count = 0;
                          for (int i = cleanStr.length - 1; i >= 0; i--) {
                            if (count != 0 && count % 3 == 0) result = '.$result';
                            result = cleanStr[i] + result;
                            count++;
                          }
                          cashReceivedController.value = TextEditingValue(
                            text: result,
                            selection: TextSelection.collapsed(offset: result.length),
                          );
                          setStateDialog(() {});
                        },
                      ),
                      if (cashReceivedController.text.isNotEmpty && double.tryParse(cashReceivedController.text.replaceAll('.', '')) != null) ...[
                        const SizedBox(height: 16),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('Kembalian', style: TextStyle(fontSize: 14, color: Colors.grey[500])),
                            Text(
                              'Rp ${formatRp(double.parse(cashReceivedController.text.replaceAll('.', '')) - finalTotal)}',
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                fontSize: 16,
                                color: (double.parse(cashReceivedController.text.replaceAll('.', '')) - finalTotal) >= 0 ? Colors.green : Colors.red,
                              ),
                            ),
                          ],
                        ),
                      ]
                    ],
                    
                    const SizedBox(height: 32),
                    
                    // Big Orange Confirm Button
                    SizedBox(
                      height: 56,
                      child: ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Theme.of(context).primaryColor,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                          elevation: 0,
                        ),
                        onPressed: () {
                          final cleanAmountStr = cashReceivedController.text.replaceAll('.', '');
                          double? cash = double.tryParse(cleanAmountStr);
                          double? change;
                          if (selectedPaymentMethod == 'CASH') {
                            if (cash == null || cash < finalTotal) {
                              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Uang yang diterima kurang atau tidak valid')));
                              return;
                            }
                            change = cash - finalTotal;
                          }
                          Navigator.pop(ctx, {
                            'confirm': true, 
                            'method': selectedPaymentMethod,
                            'cashReceived': cash,
                            'change': change,
                          });
                        },
                        child: const Text('Konfirmasi Bayar', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        });
      },
    );

    if (result != null && result['confirm'] == true) {
      final shiftState = ref.read(shiftProvider);
      final shift = shiftState.value;

      if (shift == null || shift.status != 'OPEN') {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Anda harus membuka Shift terlebih dahulu di menu Beranda!')));
        }
        return;
      }

      final method = result['method'];
      final payload = {
        'nickname': _customerProfile != null ? _customerProfile!['nickname'] : 'Guest',
        'table': 'Takeaway',
        'totalAmount': finalTotal,
        'rewardId': _selectedReward?['id'],
        'paymentMethod': method,
        'shiftId': shift.id,
        'items': cart.map((i) => {'menuId': i.menu.id, 'quantity': i.quantity, 'price': i.menu.price}).toList(),
        'createdAt': DateTime.now().toIso8601String(),
      };

      try {
        final res = await http.post(
          Uri.parse('http://100.77.229.76:3001/api/checkout'),
          headers: {'Content-Type': 'application/json'},
          body: json.encode(payload),
        );
        if (!mounted) return;

        if (res.statusCode == 201) {
          final data = json.decode(res.body);
          final points = data['transaction']['pointsEarned'];
          
          cartNotifier.clearCart();
          setState(() {
            _nicknameController.clear();
            _customerProfile = null;
            _selectedReward = null;
          });
          
          if (data['luckyDrop'] != null) {
            final bonus = data['luckyDrop']['bonusPoints'];
            await showDialog(
              context: context,
              barrierDismissible: false,
              builder: (ctx) => MysteryBoxDialog(rewardName: "BONUS +$bonus POIN!"),
            );
          }
          
          await showDialog(
            context: context,
            builder: (ctx) => ReceiptDialog(
              transactionData: data['transaction'],
              nickname: nickname,
              cashReceived: result['cashReceived'],
              change: result['change'],
            ),
          );

          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('🎉 Checkout Berhasil! Mendapat $points Poin'),
              backgroundColor: Colors.green[700],
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Checkout gagal (Server error)')));
        }
      } catch (e) {
        await DBHelper().saveOfflineTransaction(payload);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('⚡ Offline: Transaksi disimpan secara lokal.'),
            backgroundColor: Theme.of(context).primaryColor,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          )
        );
        cartNotifier.clearCart();
        setState(() {
          _nicknameController.clear();
          _customerProfile = null;
          _selectedReward = null;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final menusAsync = ref.watch(menuProvider);
    final settings = ref.watch(settingsProvider);
    final isTablet = MediaQuery.of(context).size.width > 800;
    final cartNotifier = ref.read(cartProvider.notifier);

    // Extract unique categories from menus if data is available
    List<String> categories = ['Semua', 'Favorit'];
    if (menusAsync.hasValue && menusAsync.value != null) {
      final uniqueCats = menusAsync.value!.map((m) => m.categoryName ?? 'Lainnya').toSet().toList();
      categories.addAll(uniqueCats);
    }

    List<Menu> filteredMenus = [];
    if (menusAsync.hasValue && menusAsync.value != null) {
      filteredMenus = menusAsync.value!.where((m) {
        if (_selectedCategory == 'Favorit') {
          return _searchController.text.isEmpty || m.name.toLowerCase().contains(_searchController.text.toLowerCase());
        }
        final catToMatch = m.categoryName ?? 'Lainnya';
        final matchesCat = _selectedCategory == 'Semua' || catToMatch == _selectedCategory;
        final matchesSearch = _searchController.text.isEmpty || m.name.toLowerCase().contains(_searchController.text.toLowerCase());
        return matchesCat && matchesSearch;
      }).toList();
      
      if (_selectedCategory == 'Favorit') {
        filteredMenus.sort((a, b) => b.soldCount.compareTo(a.soldCount));
      }
    }

    return Scaffold(
      backgroundColor: const Color(0xFFFAFAFA),
      floatingActionButton: (isTablet && !_isCartExpanded)
          ? FloatingActionButton.extended(
              backgroundColor: Theme.of(context).primaryColor,
              onPressed: () => setState(() => _isCartExpanded = true),
              icon: const Icon(Icons.shopping_cart, color: Colors.white),
              label: Text('Pesanan (${ref.watch(cartProvider).length})', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            )
          : null,
      body: SafeArea(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Main Menu Grid Area
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(20.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Custom Header matching the provided layout
                    if (isTablet)
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            flex: 1,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  () {
                                    final now = DateTime.now();
                                    final months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
                                    return '${months[now.month - 1]} ${now.day}, ${now.year}';
                                  }(),
                                  style: TextStyle(fontSize: 14, color: Colors.grey[600], fontWeight: FontWeight.w600),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  settings.storeName, 
                                  style: const TextStyle(fontSize: 24, color: Colors.black87, fontWeight: FontWeight.w900, letterSpacing: -0.5),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 16),
                          // Search Bar
                          Expanded(
                            flex: 1,
                            child: Container(
                              height: 48,
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(color: Colors.grey[200]!)
                              ),
                              child: TextField(
                                controller: _searchController,
                                onChanged: (val) => setState(() {}),
                                decoration: InputDecoration(
                                  hintText: 'Cari Menu...',
                                  hintStyle: TextStyle(color: Colors.grey[400], fontSize: 14),
                                  prefixIcon: Icon(Icons.search_rounded, color: Colors.grey[400], size: 22),
                                  border: InputBorder.none,
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                                ),
                              ),
                            ),
                          ),
                        ],
                      )
                    else
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      () {
                                        final now = DateTime.now();
                                        final months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
                                        return '${months[now.month - 1]} ${now.day}, ${now.year}';
                                      }(),
                                      style: TextStyle(fontSize: 13, color: Colors.grey[500], fontWeight: FontWeight.w600),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      settings.storeName, 
                                      style: const TextStyle(fontSize: 24, color: Colors.black87, fontWeight: FontWeight.w900, letterSpacing: -0.5),
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ],
                                ),
                              ),
                              // Mobile Cart Icon
                              Stack(
                                clipBehavior: Clip.none,
                                children: [
                                  InkWell(
                                    onTap: () {
                                      showModalBottomSheet(
                                        context: context, 
                                        isScrollControlled: true,
                                        backgroundColor: Colors.transparent,
                                        builder: (ctx) => ValueListenableBuilder<int>(
                                          valueListenable: _uiRebuilder,
                                          builder: (context, _, __) {
                                            return Consumer(
                                              builder: (context, ref, child) {
                                                return FractionallySizedBox(
                                                  heightFactor: 0.9,
                                                  child: _buildCheckoutPanel(context, true, ref),
                                                );
                                              }
                                            );
                                          }
                                        ),
                                      );
                                    },
                                    borderRadius: BorderRadius.circular(16),
                                    child: Container(
                                      padding: const EdgeInsets.all(12),
                                      decoration: BoxDecoration(
                                        color: Colors.white,
                                        borderRadius: BorderRadius.circular(16),
                                        boxShadow: [
                                          BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 10, offset: const Offset(0, 4))
                                        ]
                                      ),
                                      child: Icon(Icons.shopping_bag_outlined, color: Theme.of(context).primaryColor, size: 24),
                                    ),
                                  ),
                                  if (ref.watch(cartProvider).isNotEmpty)
                                    Positioned(
                                      top: -6,
                                      right: -6,
                                      child: Container(
                                        padding: const EdgeInsets.all(6),
                                        decoration: const BoxDecoration(
                                          color: Colors.redAccent,
                                          shape: BoxShape.circle,
                                        ),
                                        child: Text(
                                          '${ref.watch(cartProvider).length}',
                                          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold),
                                        ),
                                      ),
                                    ),
                                ],
                              )
                            ],
                          ),
                          const SizedBox(height: 20),
                          Container(
                            height: 48,
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(color: Colors.grey[200]!)
                            ),
                            child: TextField(
                              controller: _searchController,
                              onChanged: (val) => setState(() {}),
                              decoration: InputDecoration(
                                hintText: 'Cari Menu...',
                                hintStyle: TextStyle(color: Colors.grey[400], fontSize: 14),
                                prefixIcon: Icon(Icons.search_rounded, color: Colors.grey[400], size: 22),
                                border: InputBorder.none,
                                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                              ),
                            ),
                          ),
                        ],
                      ),
                  const SizedBox(height: 24),
                  // "Cari Menu Terbaik" Section
                  const Text(
                    'Cari Menu Terbaik', 
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.black87)
                  ),
                  const SizedBox(height: 12),
                  // Category Filter (Pill shapes)
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: categories.map((cat) {
                        final isSelected = _selectedCategory == cat;
                        return Padding(
                          padding: const EdgeInsets.only(right: 12.0),
                          child: InkWell(
                            onTap: () => setState(() => _selectedCategory = cat),
                            borderRadius: BorderRadius.circular(8),
                            child: AnimatedContainer(
                              duration: const Duration(milliseconds: 200),
                              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                              decoration: BoxDecoration(
                                color: isSelected ? Theme.of(context).primaryColor : Colors.grey[200],
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                cat, 
                                style: TextStyle(
                                  color: isSelected ? Colors.white : Colors.black87,
                                  fontWeight: isSelected ? FontWeight.bold : FontWeight.w600,
                                  fontSize: 14,
                                )
                              ),
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  ),
                  const SizedBox(height: 24),
                  
                  // Product Grid
                  Expanded(
                    child: AnimatedSwitcher(
                      duration: const Duration(milliseconds: 300),
                      child: menusAsync.when(
                        data: (_) => filteredMenus.isEmpty
                            ? Center(key: const ValueKey('empty'), child: Text('Menu tidak ditemukan', style: TextStyle(color: Colors.grey[500], fontSize: 16)))
                            : GridView.builder(
                                key: ValueKey('grid_${_selectedCategory}_${_searchController.text}'),
                              gridDelegate: SliverGridDelegateWithMaxCrossAxisExtent(
                                maxCrossAxisExtent: 200,
                                childAspectRatio: 0.75,
                                crossAxisSpacing: 20,
                                mainAxisSpacing: 20,
                              ),
                              itemCount: filteredMenus.length,
                              itemBuilder: (context, index) {
                                final menu = filteredMenus[index];
                                return Container(
                                  decoration: BoxDecoration(
                                    color: Colors.white,
                                    borderRadius: BorderRadius.circular(20),
                                    boxShadow: [
                                      BoxShadow(color: Colors.black.withOpacity(0.04), blurRadius: 15, offset: const Offset(0, 6)),
                                    ],
                                  ),
                                  child: Material(
                                    color: Colors.transparent,
                                    child: InkWell(
                                      borderRadius: BorderRadius.circular(20),
                                      hoverColor: Theme.of(context).primaryColor.withOpacity(0.05),
                                      splashColor: Theme.of(context).primaryColor.withOpacity(0.1),
                                      highlightColor: Theme.of(context).primaryColor.withOpacity(0.05),
                                      onTap: () {
                                        cartNotifier.addToCart(menu);
                                        if (isTablet) {
                                          setState(() => _isCartExpanded = true);
                                        } else {
                                          showModalBottomSheet(
                                            context: context, 
                                            isScrollControlled: true,
                                            backgroundColor: Colors.transparent,
                                            builder: (ctx) => ValueListenableBuilder<int>(
                                              valueListenable: _uiRebuilder,
                                              builder: (context, _, __) {
                                                return Consumer(
                                                  builder: (context, ref, child) {
                                                    return FractionallySizedBox(
                                                      heightFactor: 0.85,
                                                      child: _buildCheckoutPanel(context, true, ref),
                                                    );
                                                  }
                                                );
                                              }
                                            ),
                                          );
                                        }
                                      },
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          _buildProductImage(menu),
                                          Padding(
                                            padding: const EdgeInsets.all(12.0),
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                Text(
                                                  menu.name,
                                                  style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Colors.black87),
                                                  maxLines: 2,
                                                  overflow: TextOverflow.ellipsis,
                                                ),
                                                const SizedBox(height: 8),
                                                Row(
                                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                                  children: [
                                                    Expanded(
                                                      child: Text(
                                                        'Rp ${formatRp(menu.price)}',
                                                        style: TextStyle(color: Theme.of(context).primaryColor, fontWeight: FontWeight.w900, fontSize: 13),
                                                        maxLines: 1,
                                                        overflow: TextOverflow.ellipsis,
                                                      ),
                                                    ),
                                                    const SizedBox(width: 4),
                                                    Container(
                                                      padding: const EdgeInsets.all(6),
                                                      decoration: BoxDecoration(
                                                        color: Theme.of(context).primaryColor.withOpacity(0.1),
                                                        borderRadius: BorderRadius.circular(8)
                                                      ),
                                                      child: Icon(Icons.add_shopping_cart_rounded, size: 16, color: Theme.of(context).primaryColor),
                                                    ),
                                                  ],
                                                ),
                                              ],
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                );
                              },
                            ),
                      loading: () => const Center(key: ValueKey('loading'), child: CircularProgressIndicator()),
                      error: (err, stack) => Center(key: ValueKey('error'), child: Text('Error: $err')),
                    ),
                  ),
                  ),
                ],
              ),
            ),
          ),
          // Checkout Panel Slide-in Slot
          if (isTablet)
            SizedBox(
              width: _isCartExpanded ? 300 : 0,
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  AnimatedPositioned(
                    duration: const Duration(milliseconds: 400),
                    curve: Curves.easeOutCubic,
                    top: 0,
                    bottom: 0,
                    right: _isCartExpanded ? 0 : -300,
                    width: 300,
                    child: Material(
                      elevation: 16,
                      color: Colors.white,
                      child: _buildCheckoutPanel(context, false, ref),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    ),
  );
}
}
