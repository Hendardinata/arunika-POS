import 'package:flutter/material.dart';

String formatRp(num amount) {
  String str = amount.toStringAsFixed(0);
  return str.replaceAllMapped(RegExp(r'(\d{1,3})(?=(\d{3})+(?!\d))'), (Match m) => '${m[1]}.');
}

class ReceiptDialog extends StatelessWidget {
  final Map<String, dynamic> transactionData;
  final String nickname;
  final double? cashReceived;
  final double? change;

  const ReceiptDialog({
    super.key, 
    required this.transactionData, 
    required this.nickname,
    this.cashReceived,
    this.change,
  });

  @override
  Widget build(BuildContext context) {
    final items = transactionData['items'] as List<dynamic>;
    final totalAmount = transactionData['totalAmount'];
    final paymentMethod = transactionData['paymentMethod'];
    final pointsEarned = transactionData['pointsEarned'];

    return Dialog(
      backgroundColor: Colors.transparent,
      elevation: 0,
      child: Center(
        child: Container(
          width: 360,
          padding: const EdgeInsets.only(top: 24),
          decoration: BoxDecoration(
            color: Colors.brown[900],
            borderRadius: BorderRadius.circular(24),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.print_rounded, color: Colors.white70, size: 24),
                  SizedBox(width: 8),
                  Text('Thermal Receipt', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16)),
                ],
              ),
              const SizedBox(height: 24),
              // Kertas Struk
              Container(
                margin: const EdgeInsets.symmetric(horizontal: 20),
                padding: const EdgeInsets.all(32),
                decoration: const BoxDecoration(
                  color: Color(0xFFFAF8F5), // Warm White
                  borderRadius: BorderRadius.only(topLeft: Radius.circular(12), topRight: Radius.circular(12)),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.local_cafe_rounded, size: 40, color: Colors.black87),
                    const SizedBox(height: 12),
                    const Text('BREWPOS COFFEE', style: TextStyle(fontFamily: 'monospace', fontSize: 20, fontWeight: FontWeight.bold, color: Colors.black87)),
                    const Text('Every Cup Has A Story', style: TextStyle(fontFamily: 'monospace', fontSize: 12, color: Colors.black54)),
                    const SizedBox(height: 24),
                    const Text('--------------------------------', style: TextStyle(fontFamily: 'monospace', color: Colors.black38)),
                    const SizedBox(height: 12),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Customer:', style: TextStyle(fontFamily: 'monospace', fontSize: 14, color: Colors.black87)),
                        Text(nickname, style: const TextStyle(fontFamily: 'monospace', fontSize: 14, fontWeight: FontWeight.bold, color: Colors.black87)),
                      ],
                    ),
                    const SizedBox(height: 12),
                    const Text('--------------------------------', style: TextStyle(fontFamily: 'monospace', color: Colors.black38)),
                    const SizedBox(height: 12),
                    ...items.map((item) {
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('${item['quantity']}x Menu #${item['menuId']}', style: const TextStyle(fontFamily: 'monospace', fontSize: 14, color: Colors.black87)),
                            Text('Rp ${formatRp(item['price'] * item['quantity'])}', style: const TextStyle(fontFamily: 'monospace', fontSize: 14, color: Colors.black87)),
                          ],
                        ),
                      );
                    }).toList(),
                    const SizedBox(height: 12),
                    const Text('--------------------------------', style: TextStyle(fontFamily: 'monospace', color: Colors.black38)),
                    const SizedBox(height: 12),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('TOTAL:', style: TextStyle(fontFamily: 'monospace', fontSize: 16, fontWeight: FontWeight.bold, color: Colors.black87)),
                        Text('Rp ${formatRp(totalAmount)}', style: const TextStyle(fontFamily: 'monospace', fontSize: 16, fontWeight: FontWeight.bold, color: Colors.black87)),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('PAYMENT:', style: TextStyle(fontFamily: 'monospace', fontSize: 14, color: Colors.black87)),
                        Text(paymentMethod, style: const TextStyle(fontFamily: 'monospace', fontSize: 14, color: Colors.black87)),
                      ],
                    ),
                    if (paymentMethod == 'CASH' && cashReceived != null && change != null) ...[
                      const SizedBox(height: 8),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text('TUNAI:', style: TextStyle(fontFamily: 'monospace', fontSize: 14, color: Colors.black87)),
                          Text('Rp ${formatRp(cashReceived!)}', style: const TextStyle(fontFamily: 'monospace', fontSize: 14, color: Colors.black87)),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text('KEMBALIAN:', style: TextStyle(fontFamily: 'monospace', fontSize: 14, color: Colors.black87)),
                          Text('Rp ${formatRp(change!)}', style: const TextStyle(fontFamily: 'monospace', fontSize: 14, color: Colors.black87)),
                        ],
                      ),
                    ],
                    const SizedBox(height: 24),
                    const Text('--------------------------------', style: TextStyle(fontFamily: 'monospace', color: Colors.black38)),
                    const SizedBox(height: 8),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.stars_rounded, color: Colors.amber, size: 18),
                        const SizedBox(width: 8),
                        Text('+ $pointsEarned Loyalty Pts', style: const TextStyle(fontFamily: 'monospace', fontSize: 14, fontWeight: FontWeight.bold, color: Colors.black87)),
                      ],
                    ),
                    const SizedBox(height: 8),
                    const Text('--------------------------------', style: TextStyle(fontFamily: 'monospace', color: Colors.black38)),
                    const SizedBox(height: 24),
                    const Text('Terima Kasih!', style: TextStyle(fontFamily: 'monospace', fontSize: 16, fontWeight: FontWeight.bold, color: Colors.black87)),
                  ],
                ),
              ),
              // Bagian sobekan bergerigi
              Row(
                children: List.generate(
                  40,
                  (index) => Expanded(
                    child: Container(
                      height: 10,
                      decoration: BoxDecoration(
                        color: const Color(0xFFFAF8F5),
                        borderRadius: index % 2 == 0 ? const BorderRadius.only(bottomLeft: Radius.circular(12), bottomRight: Radius.circular(12)) : BorderRadius.zero,
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 32),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.brown[600],
                    foregroundColor: Colors.white,
                    minimumSize: const Size(double.infinity, 56),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    elevation: 0,
                  ),
                  onPressed: () {
                    Navigator.of(context).pop();
                  },
                  child: const Text('Selesai', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
