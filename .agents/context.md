# Arunika-POS (BrewPOS) - Project Context

## Project Identity
- **Name**: Arunika-POS (internal codename: BrewPOS)
- **Tagline**: "Every Cup Has A Story"
- **Type**: Modern POS with CRM, Loyalty, Gamification for Coffee Shops
- **Branch**: `feature/flask-mssql-migration`

---

## Current Architecture (BEFORE Migration)

| Component | Technology |
|:---|:---|
| Backend API | Node.js + Express + TypeScript |
| ORM | Prisma (with PostgreSQL adapter) |
| Database | PostgreSQL |
| Mobile App | Flutter (Riverpod, GoRouter) |
| Web Dashboard | (planned, currently empty directory) |
| Auth | JWT (jsonwebtoken) |
| File Upload | Multer |
| Scheduler | node-cron |

---

## Target Architecture (AFTER Migration)

| Component | Technology |
|:---|:---|
| Backend API | Python Flask |
| ORM | SQLAlchemy |
| Database | Microsoft SQL Server (MSSQL) |
| Web Frontend | Flask Templates (Jinja2) + JS/CSS |
| Mobile App | Flutter (remains, API consumer) |
| Auth | Flask-JWT-Extended / PyJWT |
| File Upload | Flask built-in / Werkzeug |
| Scheduler | APScheduler |
| DB Driver | pyodbc / pymssql |

---

## Database Connection (MSSQL)
- **Server**: localhost (default instance)
- **Database**: grosirPusat
- **User**: sa
- **Password**: 12qwaszx#DB
- **Driver**: ODBC Driver 17/18 for SQL Server

---

## Database Schema (18 Tables)

### Core POS
1. **User** - Staff/admin accounts (id, username, password, role, assignedShift, createdAt)
2. **SystemSettings** - Key-value config store (id, key, value, description, updatedAt)
3. **Category** - Menu categories (id, name)
4. **Menu** - Product catalog (id, name, description, price, hpp, imageUrl, categoryId, recipeNotes)
5. **Transaction** - Orders/sales (id, subTotal, taxAmount, parkingFee, totalAmount, pointsEarned, paymentMethod, status, voidReason, voidedAt, voidedBy, customerId, shiftId, createdAt)
6. **TransactionItem** - Line items (id, transactionId, menuId, quantity, price, hpp)

### CRM & Gamification
7. **Customer** - Customer profiles (id, nickname, points, pointsExpiryDate, xp, level, lastVisitDate, streakCount, createdAt)
8. **Reward** - Redeemable rewards (id, name, description, type, pointsRequired, active)
9. **Quest** - Missions/challenges (id, name, description, type, targetEntityId, targetValue, rewardPoints, rewardXp, active, isDaily)
10. **CustomerQuest** - Quest progress tracking (id, customerId, questId, progress, isCompleted, updatedAt) - unique(customerId, questId)
11. **Badge** - Achievement badges (id, name, description, iconUrl, requiredTransactions)
12. **CustomerBadge** - Unlocked badges (id, customerId, badgeId, unlockedAt) - unique(customerId, badgeId)

### Inventory
13. **InventoryItem** - Stock items (id, name, stock, unit, imageUrl)
14. **InventoryLog** - Stock movements (id, itemId, quantity, type, notes, receiptUrl, createdAt)
15. **DailyOpname** - Daily stock audit sessions (id, date, status, isStockConfirmed, createdAt, updatedAt)
16. **DailyOpnameItem** - Audit line items (id, opnameId, inventoryItemId, openingStock, addedStock, closingStock, used, morningNotes, nightNotes)

### Finance
17. **ExpenseCategory** - Expense types (id, name, description)
18. **Expense** - Expenditures (id, amount, date, notes, categoryId, userId, receiptUrl, createdAt, updatedAt)

### Operations
19. **Shift** - Shift management (id, type, startTime, endTime, status, startingCash, endingCash, expectedEndingCash, userId, createdAt, updatedAt)
20. **AppMenu** - Application menu registry (id, name, path, icon)
21. **RoleAccess** - RBAC permissions (id, role, appMenuId, canView, canEdit) - unique(role, appMenuId)
22. **SystemLog** - Audit trail (id, action, entity, entityId, details, userId, createdAt)

---

## API Endpoints (15 Route Modules)

### Auth (`/api/auth`)
- POST `/login` - JWT login
- POST `/setup` - Initial admin seed
- GET `/users` - List all users
- POST `/users` - Create user
- PUT `/users/:id` - Update user
- DELETE `/users/:id` - Delete user (with reassign logic)

### Categories (`/api/categories`)
- GET `/` - List categories
- POST `/` - Create category

### Menus (`/api/menus`)
- GET `/` - List menus (with sold count)
- POST `/` - Create menu (multipart/image)
- PUT `/:id` - Update menu (multipart/image)
- DELETE `/:id` - Delete menu (FK protection)

### Checkout (`/api/checkout`)
- POST `/` - Process checkout (points, XP, streak, tax, HPP)
- GET `/history` - Transaction history
- POST `/sync` - Batch sync offline transactions
- POST `/history/:id/void` - Void transaction (revert points)

### Customers (`/api/customers`)
- GET `/` - List with badges/quests/counts
- GET `/search?nickname=` - Search by nickname

### Analytics (`/api/analytics`)
- GET `/` - Dashboard metrics (revenue, HPP, expenses, net profit, charts)
- GET `/reports` - Detailed transaction reports with filters

### Gamification (`/api/gamification`)
- CRUD `/quests` - Quest management
- CRUD `/badges` - Badge management
- CRUD `/rewards` - Reward management
- POST `/redeem` - Redeem reward
- POST `/spin` - Lucky Spin (50 pts)

### Inventory (`/api/inventory`)
- CRUD `/` - Inventory items
- PUT `/:id/adjust` - Stock adjustment (IN/OUT)
- GET/POST `/opname/*` - Daily stock audit (open/confirm/close/history)

### Expenses (`/api/expenses`)
- GET `/` - List with date filters
- POST `/` - Create (with receipt upload)
- GET `/summary` - Summary by category
- GET/POST `/categories` - Expense categories
- POST `/seed-categories` - Seed defaults

### Settings (`/api/settings`)
- GET `/` - Get all settings
- POST `/` - Upsert setting

### Shift (`/api/shift`)
- POST `/open` - Open shift (auth required)
- GET `/current` - Get current shift (auth required)
- POST `/close` - Close shift with reconciliation
- GET `/reports` - Shift reports

### Role Access (`/api/role-access`)
- GET `/menus` - App menu list
- GET `/:role` - Role permissions
- PUT `/:role` - Update permissions
- POST `/menus` - Create app menu

### Recipes (`/api/recipes`)
- GET `/` - List menus with recipe notes
- POST `/:menuId` - Update recipe notes

### Logs (`/api/logs`)
- GET `/` - System audit logs (200 latest)

---

## Business Logic Highlights

### Checkout Flow
1. Calculate points: 1 point + 1 XP per Rp 1.000
2. 20% chance Lucky Drop → +50 bonus points
3. Guest checkout → no points
4. Streak tracking (consecutive daily visits)
5. Level = floor(totalXP / 100) + 1
6. Point expiration configurable (default 90 days)
7. Tax & parking calculated from total (included pricing model)
8. HPP tracked per transaction item
9. Gamification processed async (non-blocking)

### Gamification Engine
- Quest types: TOTAL_TRANSACTIONS, TOTAL_SPEND, BUY_ITEM
- Badge unlock: based on transaction count threshold
- Lucky Spin: costs 50 pts, prizes weighted (10% jackpot, 30% +100pts, 40% break-even, 20% zonk)
- Daily quest reset via cron at midnight

### User Roles
- OWNER (admin), HEADBAR, CASHIER
- RBAC via AppMenu + RoleAccess tables

---

## Mobile App Screens (Flutter)
1. LoginScreen - Authentication
2. MainScreen - Navigation/layout
3. POSScreen - POS/checkout terminal (largest: 59KB)
4. DashboardScreen - Analytics overview
5. HistoryScreen - Transaction history
6. InventoryScreen - Stock management
7. OpnameScreen - Daily stock audit
8. ReportScreen - Financial reports
9. ReceiptDialog - Digital receipt
10. LuckySpinDialog - Lucky Spin game
11. MysteryBoxDialog - Mystery Box reward

---

## Key Design Decisions for Migration
1. All IDs are autoincrement integers
2. Monetary values stored as integers (Rupiah, no decimal)
3. Soft deletes for quests and rewards (active flag)
4. Hard deletes for badges, menus (with FK protection)
5. Image uploads to local filesystem `/public/uploads/`
6. JWT expiry: 24 hours
7. No pagination on most endpoints (except history=50, logs=200)
