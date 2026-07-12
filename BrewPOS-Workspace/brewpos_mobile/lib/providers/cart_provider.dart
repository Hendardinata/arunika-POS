import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/menu.dart';

class CartNotifier extends Notifier<List<CartItem>> {
  @override
  List<CartItem> build() {
    return [];
  }

  void addToCart(Menu menu) {
    final existingIndex = state.indexWhere((item) => item.menu.id == menu.id);
    if (existingIndex >= 0) {
      final newState = [...state];
      newState[existingIndex].quantity += 1;
      state = newState;
    } else {
      state = [...state, CartItem(menu: menu)];
    }
  }

  void decreaseQuantity(Menu menu) {
    final existingIndex = state.indexWhere((item) => item.menu.id == menu.id);
    if (existingIndex >= 0) {
      if (state[existingIndex].quantity > 1) {
        final newState = [...state];
        newState[existingIndex].quantity -= 1;
        state = newState;
      } else {
        removeFromCart(menu);
      }
    }
  }

  void removeFromCart(Menu menu) {
    state = state.where((item) => item.menu.id != menu.id).toList();
  }

  void clearCart() {
    state = [];
  }
  
  int get totalAmount {
    return state.fold(0, (sum, item) => sum + item.total);
  }
}

final cartProvider = NotifierProvider<CartNotifier, List<CartItem>>(() {
  return CartNotifier();
});
