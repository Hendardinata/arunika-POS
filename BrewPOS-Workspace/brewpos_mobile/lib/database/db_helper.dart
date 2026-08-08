import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import '../models/menu.dart';

class DBHelper {
  static final DBHelper _instance = DBHelper._internal();
  factory DBHelper() => _instance;
  DBHelper._internal();

  final String apiUrl = 'http://100.77.229.76:3001/api';
  Database? _db;

  Future<Database> get db async {
    if (kIsWeb) throw UnsupportedError('SQLite is not supported on Web without sqflite_common_ffi_web');
    if (_db != null) return _db!;
    _db = await _initDB();
    return _db!;
  }

  Future<Database> _initDB() async {
    String path = join(await getDatabasesPath(), 'brewpos.db');
    return await openDatabase(
      path,
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE offline_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT
          )
        ''');
      },
    );
  }

  Future<void> saveOfflineTransaction(Map<String, dynamic> transaction) async {
    if (kIsWeb) return;
    final client = await db;
    await client.insert('offline_transactions', {'payload': json.encode(transaction)});
  }

  Future<List<Map<String, dynamic>>> getOfflineTransactions() async {
    if (kIsWeb) return [];
    final client = await db;
    final List<Map<String, Object?>> maps = await client.query('offline_transactions');
    return maps.map((e) => {
      'id': e['id'],
      'payload': json.decode(e['payload'] as String),
    }).toList();
  }

  Future<void> deleteOfflineTransaction(int id) async {
    if (kIsWeb) return;
    final client = await db;
    await client.delete('offline_transactions', where: 'id = ?', whereArgs: [id]);
  }

  Future<List<Category>> getCategories() async {
    try {
      final response = await http.get(Uri.parse('$apiUrl/categories'));
      if (response.statusCode == 200) {
        final List<dynamic> data = json.decode(response.body);
        return data.map((json) => Category.fromJson(json)).toList();
      }
    } catch (e) {
      print('Error fetching categories: $e');
    }
    return [];
  }

  Future<List<Menu>> getMenus() async {
    try {
      final response = await http.get(Uri.parse('$apiUrl/menus'));
      if (response.statusCode == 200) {
        final List<dynamic> data = json.decode(response.body);
        return data.map((json) => Menu.fromJson(json)).toList();
      }
    } catch (e) {
      print('Error fetching menus: $e');
    }
    return [];
  }
}
