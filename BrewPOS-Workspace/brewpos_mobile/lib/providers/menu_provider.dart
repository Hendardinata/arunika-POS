import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/menu.dart';
import '../database/db_helper.dart';

final menuProvider = FutureProvider<List<Menu>>((ref) async {
  return await DBHelper().getMenus();
});

final categoryProvider = FutureProvider<List<Category>>((ref) async {
  return await DBHelper().getCategories();
});
