from sqlalchemy import text
from app.extensions import db

def _migrate_customer_identity(conn):
    """
    Member identity moved from nickname to contact: nickname may now repeat, while
    phone and email must be unique whenever they are filled in (either one suffices).
    Every step is guarded so a second run is a no-op.
    """
    # 1. Normalise stored contacts so the unique indexes below compare like with like.
    try:
        conn.execute(text("""
            UPDATE [Customer]
               SET [phone] = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                             [phone], ' ', ''), '-', ''), '(', ''), ')', ''), '+', ''), '.', '')
             WHERE [phone] IS NOT NULL
        """))
        # Samakan dengan normalize_phone() di models/customer.py: 62xxx -> 0xxx
        conn.execute(text(
            "UPDATE [Customer] SET [phone] = '0' + SUBSTRING([phone], 3, LEN([phone])) "
            "WHERE [phone] LIKE '62%'"
        ))
        conn.execute(text("UPDATE [Customer] SET [email] = LOWER(LTRIM(RTRIM([email]))) WHERE [email] IS NOT NULL"))
        conn.execute(text("UPDATE [Customer] SET [phone] = NULL WHERE [phone] = ''"))
        conn.execute(text("UPDATE [Customer] SET [email] = NULL WHERE [email] = ''"))
        conn.commit()
    except Exception as e:
        print(f"[Schema Sync] FAILED normalising customer contacts: {e}")
        return

    # 2. Drop the unique constraint/index on nickname. MSSQL generates the name, so
    #    it has to be looked up rather than hardcoded.
    try:
        rows = conn.execute(text("""
            SELECT i.name, i.is_unique_constraint
              FROM sys.indexes i
              JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
              JOIN sys.columns c ON c.object_id = i.object_id AND c.column_id = ic.column_id
             WHERE i.object_id = OBJECT_ID(N'[Customer]')
               AND c.name = 'nickname' AND i.is_unique = 1 AND i.is_primary_key = 0
        """)).fetchall()
        for index_name, is_constraint in rows:
            if is_constraint:
                conn.execute(text(f"ALTER TABLE [Customer] DROP CONSTRAINT [{index_name}]"))
            else:
                conn.execute(text(f"DROP INDEX [{index_name}] ON [Customer]"))
            conn.commit()
            print(f"[Schema Sync] Dropped unique index on Customer.nickname ({index_name})")
    except Exception as e:
        print(f"[Schema Sync] FAILED dropping Customer.nickname unique index: {e}")

    # 3. Unique phone/email, but only for rows that actually have one. A filtered
    #    index is what allows many NULLs — members with only an email are valid.
    for column in ('phone', 'email'):
        index_name = f"UX_Customer_{column}"
        try:
            exists = conn.execute(text(
                "SELECT COUNT(*) FROM sys.indexes WHERE name = :n AND object_id = OBJECT_ID(N'[Customer]')"
            ), {'n': index_name}).scalar()
            if exists:
                continue

            dupes = conn.execute(text(f"""
                SELECT [{column}], COUNT(*) FROM [Customer]
                 WHERE [{column}] IS NOT NULL
                 GROUP BY [{column}] HAVING COUNT(*) > 1
            """)).fetchall()
            if dupes:
                listed = ', '.join(f"{value} ({count}x)" for value, count in dupes[:10])
                print(f"[Schema Sync] SKIPPED {index_name}: Customer.{column} masih duplikat -> {listed}")
                print(f"[Schema Sync] Rapikan duplikat tersebut lalu restart aplikasi agar {index_name} dibuat.")
                continue

            conn.execute(text(
                f"CREATE UNIQUE INDEX [{index_name}] ON [Customer]([{column}]) WHERE [{column}] IS NOT NULL"
            ))
            conn.commit()
            print(f"[Schema Sync] Created {index_name}")
        except Exception as e:
            print(f"[Schema Sync] FAILED creating {index_name}: {e}")


def auto_sync_schema(app):
    """
    Automatically checks and adds missing columns to existing MSSQL tables without data loss.
    """
    schema_updates = [
        ("Transaction", "discountAmount", "INT NOT NULL DEFAULT 0"),
        ("Transaction", "transactionCode", "NVARCHAR(50) NULL"),
        ("TransactionItem", "discountAmount", "INT NOT NULL DEFAULT 0"),
        ("InventoryItem", "minStock", "FLOAT NOT NULL DEFAULT 10.0"),
        ("InventoryItem", "costPerUnit", "FLOAT NOT NULL DEFAULT 0.0"),
        ("InventoryLog", "totalCost", "FLOAT NOT NULL DEFAULT 0.0"),
        ("InventoryLog", "costPerUnit", "FLOAT NOT NULL DEFAULT 0.0"),
        ("InventoryLog", "supplier", "NVARCHAR(255) NULL"),
        ("Menu", "recipeNotes", "NVARCHAR(MAX) NULL"),
        ("Customer", "customerType", "NVARCHAR(30) NOT NULL DEFAULT 'REGULAR'"),
        ("Customer", "phone", "NVARCHAR(50) NULL"),
        ("Customer", "email", "NVARCHAR(255) NULL"),
        ("Customer", "dailyQuota", "INT NOT NULL DEFAULT 0"),
        ("Customer", "usedQuotaToday", "INT NOT NULL DEFAULT 0"),
        ("Customer", "lastQuotaResetDate", "DATETIME NULL"),
        ("User", "allowedPages", "NVARCHAR(MAX) NULL"),
        ("Reward", "discountValue", "INT NOT NULL DEFAULT 0"),
        # Cashier attribution: a shift is now shared by the whole store, so the
        # transaction itself has to remember who rang it up.
        ("Transaction", "userId", "INT NULL"),
        ("Shift", "sessionNo", "INT NULL"),
        ("Shift", "openedBy", "INT NULL"),
        ("Shift", "closedBy", "INT NULL"),
        ("Shift", "currentUserId", "INT NULL"),
        ("Shift", "closingNote", "NVARCHAR(MAX) NULL"),
        # Arsip: menu/bahan yang sudah terpakai di transaksi tidak boleh dihapus
        # (riwayat penjualan & HPP ikut hilang), jadi dinonaktifkan saja.
        ("Menu", "isActive", "BIT NOT NULL DEFAULT 1"),
        ("InventoryItem", "isActive", "BIT NOT NULL DEFAULT 1"),
        # Sumber dana pengeluaran: yang diambil dari laci harus ikut mengurangi
        # ekspektasi kas saat sesi ditutup.
        ("Expense", "paymentSource", "NVARCHAR(20) NOT NULL DEFAULT 'CASH_DRAWER'"),
        ("Expense", "shiftId", "INT NULL"),
    ]

    # Backfill for the shift rework. Safe to re-run: every statement is scoped to
    # rows that have not been filled in yet.
    shift_backfills = [
        "UPDATE [Shift] SET [openedBy] = [userId] WHERE [openedBy] IS NULL",
        "UPDATE [Shift] SET [currentUserId] = [userId] WHERE [currentUserId] IS NULL",
        # Historic attribution used to live only on the shift; rescue it before
        # shifts stop belonging to a single cashier.
        """UPDATE t SET t.[userId] = s.[userId]
           FROM [Transaction] t INNER JOIN [Shift] s ON s.[id] = t.[shiftId]
           WHERE t.[userId] IS NULL""",
    ]

    new_tables = [
        ("ShiftHandover", """
            CREATE TABLE [ShiftHandover] (
                [id] INT IDENTITY(1,1) PRIMARY KEY,
                [shiftId] INT NOT NULL,
                [fromUserId] INT NULL,
                [toUserId] INT NOT NULL,
                [note] NVARCHAR(500) NULL,
                [createdAt] DATETIME NOT NULL DEFAULT GETDATE()
            )
        """),
        ("Attendance", """
            CREATE TABLE [Attendance] (
                [id] INT IDENTITY(1,1) PRIMARY KEY,
                [userId] INT NOT NULL,
                [clockIn] DATETIME NOT NULL,
                [clockOut] DATETIME NULL,
                [note] NVARCHAR(500) NULL,
                [createdAt] DATETIME NOT NULL DEFAULT GETDATE()
            )
        """),
        # Uang keluar-masuk laci di luar penjualan & belanja: setor brankas,
        # tambah receh, diambil pemilik. Tanpa ini laci tidak akan pernah cocok
        # begitu salah satunya terjadi -- dan di kafe 16 jam itu terjadi harian.
        ("CashMovement", """
            CREATE TABLE [CashMovement] (
                [id] INT IDENTITY(1,1) PRIMARY KEY,
                [shiftId] INT NOT NULL,
                [type] NVARCHAR(20) NOT NULL,
                [amount] INT NOT NULL,
                [reason] NVARCHAR(255) NOT NULL,
                [userId] INT NULL,
                [createdAt] DATETIME NOT NULL DEFAULT GETDATE(),
                CONSTRAINT [fk_cashmovement_shift] FOREIGN KEY ([shiftId])
                    REFERENCES [Shift]([id]) ON DELETE CASCADE
            )
        """),
        # Omzet harian dari masa sebelum aplikasi dipakai. Sengaja bukan
        # Transaction: tidak ada rincian menu, dan menyimpannya di sana akan
        # memotong stok hari ini serta menghitung poin member dua kali.
        ("HistoricalSales", """
            CREATE TABLE [HistoricalSales] (
                [id] INT IDENTITY(1,1) PRIMARY KEY,
                [date] DATE NOT NULL UNIQUE,
                [totalAmount] INT NOT NULL DEFAULT 0,
                [transactionCount] INT NULL,
                [notes] NVARCHAR(MAX) NULL,
                [createdAt] DATETIME NOT NULL DEFAULT GETDATE(),
                [updatedAt] DATETIME NOT NULL DEFAULT GETDATE()
            )
        """),
        # Resep menu: berapa banyak tiap bahan yang terpakai per 1 porsi.
        # Sempat hanya lahir lewat seed.py, jadi database yang dibangun tanpa
        # seed tidak punya tabel ini sama sekali -- akibatnya potong stok
        # otomatis, HPP, dan seluruh fitur resep diam-diam tidak jalan.
        # Harus dibuat setelah Menu & InventoryItem karena mengacu ke keduanya.
        ("RecipeIngredient", """
            CREATE TABLE [RecipeIngredient] (
                [id] INT IDENTITY(1,1) PRIMARY KEY,
                [menuId] INT NOT NULL,
                [inventoryItemId] INT NOT NULL,
                [quantityNeeded] FLOAT NOT NULL,
                CONSTRAINT [fk_recipe_menu] FOREIGN KEY ([menuId])
                    REFERENCES [Menu]([id]) ON DELETE CASCADE,
                CONSTRAINT [fk_recipe_inventory] FOREIGN KEY ([inventoryItemId])
                    REFERENCES [InventoryItem]([id]),
                CONSTRAINT [uq_menu_inventory_ingredient] UNIQUE ([menuId], [inventoryItemId])
            )
        """),
    ]

    # Indeks. MSSQL membuatkan indeks sendiri untuk PRIMARY KEY dan UNIQUE, tapi
    # TIDAK untuk foreign key -- jadi setiap join dan setiap filter rentang
    # tanggal di laporan berjalan sebagai pemindaian tabel penuh. Tidak terasa
    # saat tabelnya masih ratusan baris, mulai menggigit di puluhan ribu.
    #
    # Kolom di sini diambil dari yang benar-benar difilter kode, bukan ditebak:
    # Transaction.createdAt dan Expense.date masing-masing dipakai 11 kali.
    #
    # Urutan kolom pada indeks gabungan mengikuti urutan pemakaian: kolom yang
    # dibandingkan sama-dengan lebih dulu, rentang tanggal terakhir.
    new_indexes = [
        # Laporan penjualan: hampir selalu rentang tanggal, sering plus status.
        ('IX_Transaction_createdAt', 'Transaction', '[createdAt]'),
        ('IX_Transaction_status_createdAt', 'Transaction', '[status], [createdAt]'),
        ('IX_Transaction_shiftId', 'Transaction', '[shiftId]'),
        ('IX_Transaction_customerId', 'Transaction', '[customerId]'),
        ('IX_Transaction_userId', 'Transaction', '[userId]'),
        ('IX_Transaction_transactionCode', 'Transaction', '[transactionCode]'),
        # Setiap struk & setiap laporan margin menjahit tabel ini ke Transaction.
        ('IX_TransactionItem_transactionId', 'TransactionItem', '[transactionId]'),
        ('IX_TransactionItem_menuId', 'TransactionItem', '[menuId]'),
        # Riwayat mutasi stok per bahan, dan hitung pemakaian per rentang.
        ('IX_InventoryLog_itemId_createdAt', 'InventoryLog', '[itemId], [createdAt]'),
        ('IX_InventoryLog_createdAt', 'InventoryLog', '[createdAt]'),
        # Identitas member: cukup salah satu dari HP atau email, dua-duanya dicari.
        ('IX_Customer_phone', 'Customer', '[phone]'),
        ('IX_Customer_email', 'Customer', '[email]'),
        ('IX_Customer_nickname', 'Customer', '[nickname]'),
        ('IX_Expense_date', 'Expense', '[date]'),
        ('IX_Expense_categoryId', 'Expense', '[categoryId]'),
        ('IX_Expense_shiftId', 'Expense', '[shiftId]'),
        ('IX_Shift_startTime', 'Shift', '[startTime]'),
        ('IX_CashMovement_shiftId', 'CashMovement', '[shiftId]'),
        ('IX_Shift_status', 'Shift', '[status]'),
        ('IX_Menu_categoryId', 'Menu', '[categoryId]'),
        ('IX_RecipeIngredient_inventoryItemId', 'RecipeIngredient', '[inventoryItemId]'),
        ('IX_DailyOpnameItem_opnameId', 'DailyOpnameItem', '[opnameId]'),
        ('IX_Attendance_userId_clockIn', 'Attendance', '[userId], [clockIn]'),
        ('IX_SystemLog_createdAt', 'SystemLog', '[createdAt]'),
    ]

    # One-time backfill: the rupiah value used to be parsed out of the reward name in the
    # browser. Move that rule server-side for rows created before discountValue existed.
    backfill_updates = [
        ("50", 50000),
        ("20", 20000),
        ("15", 15000),
    ]
    
    with app.app_context():
        try:
            with db.engine.connect() as conn:
                for table_name, col_name, col_type in schema_updates:
                    try:
                        check_sql = text(f"""
                            IF EXISTS (SELECT * FROM sys.tables WHERE name = '{table_name}')
                            BEGIN
                                IF NOT EXISTS (
                                    SELECT * FROM sys.columns 
                                    WHERE object_id = OBJECT_ID(N'[{table_name}]') 
                                    AND name = '{col_name}'
                                )
                                BEGIN
                                    ALTER TABLE [{table_name}] ADD [{col_name}] {col_type};
                                END
                            END
                        """)
                        conn.execute(check_sql)
                        conn.commit()
                    except Exception as e:
                        print(f"[Schema Sync] Column sync note ({table_name}.{col_name}): {e}")

                for table_name, create_sql in new_tables:
                    try:
                        conn.execute(text(f"""
                            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = '{table_name}')
                            BEGIN
                                {create_sql}
                            END
                        """))
                        conn.commit()
                    except Exception as e:
                        print(f"[Schema Sync] FAILED creating table {table_name}: {e}")

                # Indeks dibuat setelah tabel & kolomnya ada. Aman diulang:
                # tiap pernyataan memeriksa sys.indexes lebih dulu.
                for nama, tabel, kolom in new_indexes:
                    try:
                        conn.execute(text(f"""
                            IF EXISTS (SELECT * FROM sys.tables WHERE name = '{tabel}')
                            AND NOT EXISTS (
                                SELECT * FROM sys.indexes
                                WHERE name = '{nama}' AND object_id = OBJECT_ID(N'[{tabel}]')
                            )
                            BEGIN
                                CREATE NONCLUSTERED INDEX [{nama}] ON [{tabel}] ({kolom});
                            END
                        """))
                        conn.commit()
                    except Exception as e:
                        print(f"[Schema Sync] Index note ({nama}): {e}")

                for sql in shift_backfills:
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                    except Exception as e:
                        print(f"[Schema Sync] FAILED shift backfill: {e}")

                _migrate_customer_identity(conn)

                try:
                    for needle, value in backfill_updates:
                        conn.execute(text(
                            "UPDATE [Reward] SET [discountValue] = :val "
                            "WHERE [discountValue] = 0 AND [name] LIKE :pattern"
                        ), {'val': value, 'pattern': f'%{needle}%'})
                    # Anything still at 0 keeps the old default of Rp 10.000
                    conn.execute(text(
                        "UPDATE [Reward] SET [discountValue] = 10000 WHERE [discountValue] = 0"
                    ))
                    conn.commit()
                except Exception as e:
                    print(f"[Schema Sync] Reward.discountValue backfill note: {e}")
        except Exception as e:
            print(f"[Schema Sync] Warning connecting for auto-sync: {e}")
