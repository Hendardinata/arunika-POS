class Category {
  final int id;
  final String name;

  Category({required this.id, required this.name});

  factory Category.fromJson(Map<String, dynamic> json) {
    return Category(id: json['id'], name: json['name']);
  }
}

class Menu {
  final int id;
  final String name;
  final int price;
  final int categoryId;
  final String? categoryName; // For UI display
  final int soldCount; // For favorite filter
  final String? imageUrl; // For UI display

  Menu({
    required this.id,
    required this.name,
    required this.price,
    required this.categoryId,
    this.categoryName,
    this.soldCount = 0,
    this.imageUrl,
  });

  factory Menu.fromJson(Map<String, dynamic> json) {
    return Menu(
      id: json['id'],
      name: json['name'],
      price: json['price'],
      categoryId: json['categoryId'],
      categoryName: json['category'] != null ? json['category']['name'] : json['categoryName'], // handles both API and SQLite formats
      soldCount: json['soldCount'] ?? 0,
      imageUrl: json['imageUrl'],
    );
  }
}

class CartItem {
  final Menu menu;
  int quantity;

  CartItem({required this.menu, this.quantity = 1});
  
  int get total => menu.price * quantity;
}
