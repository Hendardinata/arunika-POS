from sqlalchemy import text
from app.extensions import db

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
        except Exception as e:
            print(f"[Schema Sync] Warning connecting for auto-sync: {e}")
