# Data Dictionary - Arunika-POS

Dokumen ini memastikan tidak ada miss antara backend, database, dan frontend.

---

## 1. User

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| username | NVARCHAR(255) | NO | - | UNIQUE | |
| password | NVARCHAR(255) | NO | - | - | bcrypt hashed |
| role | NVARCHAR(50) | NO | 'CASHIER' | - | OWNER, HEADBAR, CASHIER |
| assignedShift | NVARCHAR(50) | YES | NULL | - | MORNING, NIGHT |
| createdAt | DATETIME2 | NO | GETDATE() | - | |

**Relations**: expenses(1:N), shifts(1:N), systemLogs(1:N)

---

## 2. SystemSettings

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| key | NVARCHAR(255) | NO | - | UNIQUE | e.g., POINT_EXPIRATION_DAYS |
| value | NVARCHAR(MAX) | NO | - | - | |
| description | NVARCHAR(MAX) | YES | NULL | - | |
| updatedAt | DATETIME2 | NO | auto-update | - | |

**Known Keys**: POINT_EXPIRATION_DAYS (default 90), TAX_PERCENTAGE (default 11), PARKING_FEE (default 2000)

---

## 3. Category

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| name | NVARCHAR(255) | NO | - | UNIQUE | |

**Relations**: menus(1:N)

---

## 4. Menu

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| name | NVARCHAR(255) | NO | - | UNIQUE | |
| description | NVARCHAR(MAX) | YES | NULL | - | |
| price | INT | NO | - | - | Rupiah (no decimal) |
| hpp | INT | NO | 0 | - | Harga Pokok Penjualan |
| imageUrl | NVARCHAR(500) | YES | NULL | - | /uploads/filename |
| categoryId | INT | NO | - | FK→Category.id | |
| recipeNotes | NVARCHAR(MAX) | YES | NULL | - | |

**Relations**: transactionItems(1:N), category(N:1)

---

## 5. Customer

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| nickname | NVARCHAR(255) | NO | - | UNIQUE | Coffee identity |
| points | INT | NO | 0 | - | Loyalty points |
| pointsExpiryDate | DATETIME2 | YES | NULL | - | |
| xp | INT | NO | 0 | - | Experience points |
| level | INT | NO | 1 | - | floor(xp/100)+1 |
| lastVisitDate | DATETIME2 | YES | NULL | - | |
| streakCount | INT | NO | 0 | - | Consecutive daily visits |
| createdAt | DATETIME2 | NO | GETDATE() | - | |

**Relations**: transactions(1:N), quests(1:N via CustomerQuest), badges(1:N via CustomerBadge)

---

## 6. Transaction

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| subTotal | INT | NO | 0 | - | Before tax |
| taxAmount | INT | NO | 0 | - | Tax portion |
| parkingFee | INT | NO | 0 | - | Parking allocation |
| totalAmount | INT | NO | - | - | Final amount |
| pointsEarned | INT | NO | - | - | Points given |
| paymentMethod | NVARCHAR(50) | NO | 'CASH' | - | CASH, QRIS, etc |
| status | NVARCHAR(50) | NO | 'COMPLETED' | - | COMPLETED, VOID |
| voidReason | NVARCHAR(MAX) | YES | NULL | - | |
| voidedAt | DATETIME2 | YES | NULL | - | |
| voidedBy | INT | YES | NULL | - | User ID who voided |
| customerId | INT | NO | - | FK→Customer.id | |
| shiftId | INT | YES | NULL | FK→Shift.id | |
| createdAt | DATETIME2 | NO | GETDATE() | - | |

**Relations**: customer(N:1), shift(N:1), items(1:N)

---

## 7. TransactionItem

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| transactionId | INT | NO | - | FK→Transaction.id | |
| menuId | INT | NO | - | FK→Menu.id | |
| quantity | INT | NO | - | - | |
| price | INT | NO | - | - | Price at time of sale |
| hpp | INT | NO | 0 | - | HPP at time of sale |

---

## 8. Reward

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| name | NVARCHAR(255) | NO | - | - | |
| description | NVARCHAR(MAX) | YES | NULL | - | |
| type | NVARCHAR(50) | NO | 'NORMAL' | - | NORMAL, MYSTERY_BOX, LUCKY_SPIN |
| pointsRequired | INT | NO | - | - | |
| active | BIT | NO | 1 | - | Soft delete flag |

---

## 9. Quest

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| name | NVARCHAR(255) | NO | - | - | |
| description | NVARCHAR(MAX) | YES | NULL | - | |
| type | NVARCHAR(50) | NO | 'TOTAL_TRANSACTIONS' | - | TOTAL_TRANSACTIONS, TOTAL_SPEND, BUY_ITEM |
| targetEntityId | INT | YES | NULL | - | menuId for BUY_ITEM type |
| targetValue | INT | NO | - | - | |
| rewardPoints | INT | NO | 0 | - | |
| rewardXp | INT | NO | 0 | - | |
| active | BIT | NO | 1 | - | |
| isDaily | BIT | NO | 0 | - | Reset by cron |

**Relations**: customers(1:N via CustomerQuest)

---

## 10. CustomerQuest

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| customerId | INT | NO | - | FK→Customer.id | |
| questId | INT | NO | - | FK→Quest.id | |
| progress | INT | NO | 0 | - | |
| isCompleted | BIT | NO | 0 | - | |
| updatedAt | DATETIME2 | NO | auto-update | - | |

**Constraint**: UNIQUE(customerId, questId)

---

## 11. Badge

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| name | NVARCHAR(255) | NO | - | - | |
| description | NVARCHAR(MAX) | YES | NULL | - | |
| iconUrl | NVARCHAR(500) | YES | NULL | - | |
| requiredTransactions | INT | NO | 0 | - | Threshold to unlock |

---

## 12. CustomerBadge

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| customerId | INT | NO | - | FK→Customer.id | |
| badgeId | INT | NO | - | FK→Badge.id | |
| unlockedAt | DATETIME2 | NO | GETDATE() | - | |

**Constraint**: UNIQUE(customerId, badgeId)

---

## 13. InventoryItem

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| name | NVARCHAR(255) | NO | - | UNIQUE | |
| stock | INT | NO | 0 | - | Current stock |
| unit | NVARCHAR(50) | NO | 'pcs' | - | |
| imageUrl | NVARCHAR(500) | YES | NULL | - | |

---

## 14. InventoryLog

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| itemId | INT | NO | - | FK→InventoryItem.id | |
| quantity | INT | NO | - | - | |
| type | NVARCHAR(10) | NO | - | - | IN, OUT |
| notes | NVARCHAR(MAX) | YES | NULL | - | |
| receiptUrl | NVARCHAR(500) | YES | NULL | - | |
| createdAt | DATETIME2 | NO | GETDATE() | - | |

---

## 15. DailyOpname

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| date | DATETIME2 | NO | GETDATE() | - | |
| status | NVARCHAR(20) | NO | 'OPEN' | - | OPEN, CLOSED |
| isStockConfirmed | BIT | NO | 0 | - | |
| createdAt | DATETIME2 | NO | GETDATE() | - | |
| updatedAt | DATETIME2 | NO | auto-update | - | |

---

## 16. DailyOpnameItem

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| opnameId | INT | NO | - | FK→DailyOpname.id | |
| inventoryItemId | INT | NO | - | FK→InventoryItem.id | |
| openingStock | INT | NO | 0 | - | |
| addedStock | INT | NO | 0 | - | |
| closingStock | INT | YES | NULL | - | Filled when closing |
| used | INT | YES | NULL | - | opening+added-closing |
| morningNotes | NVARCHAR(MAX) | YES | NULL | - | |
| nightNotes | NVARCHAR(MAX) | YES | NULL | - | |

---

## 17. ExpenseCategory

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| name | NVARCHAR(255) | NO | - | UNIQUE | |
| description | NVARCHAR(MAX) | YES | NULL | - | |

**Default Seeds**: Bahan Baku, Operasional, Gaji, Sewa, Lain-lain

---

## 18. Expense

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| amount | INT | NO | - | - | Rupiah |
| date | DATETIME2 | NO | GETDATE() | - | |
| notes | NVARCHAR(MAX) | YES | NULL | - | |
| categoryId | INT | NO | - | FK→ExpenseCategory.id | |
| userId | INT | NO | - | FK→User.id | |
| receiptUrl | NVARCHAR(500) | YES | NULL | - | |
| createdAt | DATETIME2 | NO | GETDATE() | - | |
| updatedAt | DATETIME2 | NO | auto-update | - | |

---

## 19. Shift

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| type | NVARCHAR(20) | NO | - | - | MORNING, NIGHT |
| startTime | DATETIME2 | NO | GETDATE() | - | |
| endTime | DATETIME2 | YES | NULL | - | |
| status | NVARCHAR(20) | NO | 'OPEN' | - | OPEN, CLOSED |
| startingCash | INT | NO | 0 | - | |
| endingCash | INT | YES | NULL | - | Actual cash |
| expectedEndingCash | INT | YES | NULL | - | Calculated |
| userId | INT | NO | - | FK→User.id | |
| createdAt | DATETIME2 | NO | GETDATE() | - | |
| updatedAt | DATETIME2 | NO | auto-update | - | |

---

## 20. AppMenu

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| name | NVARCHAR(255) | NO | - | - | Display name |
| path | NVARCHAR(500) | NO | - | - | Frontend URL path |
| icon | NVARCHAR(100) | YES | NULL | - | Icon identifier |

---

## 21. RoleAccess

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| role | NVARCHAR(50) | NO | - | - | OWNER, HEADBAR, CASHIER |
| appMenuId | INT | NO | - | FK→AppMenu.id | |
| canView | BIT | NO | 1 | - | |
| canEdit | BIT | NO | 0 | - | |

**Constraint**: UNIQUE(role, appMenuId)

---

## 22. SystemLog

| Column | Type | Nullable | Default | Constraint | Notes |
|:---|:---|:---|:---|:---|:---|
| id | INT | NO | autoincrement | PK | |
| action | NVARCHAR(100) | NO | - | - | CREATE_USER, VOID_TRANSACTION, etc |
| entity | NVARCHAR(100) | YES | NULL | - | Table/context name |
| entityId | INT | YES | NULL | - | |
| details | NVARCHAR(MAX) | YES | NULL | - | |
| userId | INT | YES | NULL | FK→User.id | |
| createdAt | DATETIME2 | NO | GETDATE() | - | |

---

## API Response Field Mapping

Semua field names yang dikonsumsi oleh Flutter mobile app HARUS tetap konsisten (camelCase JSON):

```
# User response
id, username, role, assignedShift, createdAt

# Menu response  
id, name, description, price, hpp, imageUrl, categoryId, category{id,name}, soldCount, recipeNotes

# Customer response
id, nickname, points, pointsExpiryDate, xp, level, lastVisitDate, streakCount, createdAt
  + _count{transactions}, badges[{badge{...}}], quests[{quest{...}}]

# Transaction response
id, subTotal, taxAmount, parkingFee, totalAmount, pointsEarned, paymentMethod, status, 
  voidReason, voidedAt, voidedBy, customerId, shiftId, createdAt
  + customer{...}, items[{id, menuId, quantity, price, hpp, menu{...}}]

# Checkout response
message, customer{...}, transaction{...}, luckyDrop{bonusPoints}|null

# Analytics response
totalRevenue, totalExpenses, netProfit, totalOrders, totalCustomers, 
  topCustomers[...], chartData[{date, revenue}], popularMenus[{name, count}]

# Shift response
id, type, startTime, endTime, status, startingCash, endingCash, expectedEndingCash, userId, createdAt
  + user{username}, transactions[...]
```
