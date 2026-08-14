# API Contract - Arunika-POS Flask Backend

Dokumen ini mendefinisikan kontrak API yang HARUS identik dengan backend Node.js yang lama,
agar Flutter mobile app bisa langsung switch tanpa perubahan code frontend.

---

## Base URL
```
http://{host}:{port}/api
```

## Authentication
- Header: `Authorization: Bearer <JWT_TOKEN>`
- JWT Payload: `{ id, username, role, assignedShift }`
- Expiry: 24 hours
- Header tambahan untuk logging: `X-User-Id: <user_id>`

---

## 1. Auth Routes (`/api/auth`)

### POST `/api/auth/login`
**Request**: `{ "username": str, "password": str }`
**Response 200**: `{ "message": "Login successful", "token": str, "user": { "id": int, "username": str, "role": str, "assignedShift": str|null } }`
**Response 401**: `{ "error": "Invalid username or password" }`

### POST `/api/auth/setup`
**Request**: (none)
**Response 201**: `{ "message": "Initial user admin created successfully" }`
**Response 400**: `{ "error": "Setup already completed. Users exist." }`

### GET `/api/auth/users`
**Response 200**: `[{ "id": int, "username": str, "role": str, "assignedShift": str|null, "createdAt": iso_datetime }]`

### POST `/api/auth/users`
**Request**: `{ "username": str, "password": str, "role": str, "assignedShift": str|null }`
**Response 201**: `{ "id": int, "username": str, "role": str, "assignedShift": str|null, "createdAt": iso_datetime }`

### PUT `/api/auth/users/:id`
**Request**: `{ "username": str, "password": str|empty, "role": str, "assignedShift": str|null }`
**Response 200**: Same as create response

### DELETE `/api/auth/users/:id`
**Response 200**: `{ "message": "User deleted" }`

---

## 2. Categories (`/api/categories`)

### GET `/api/categories`
**Response 200**: `[{ "id": int, "name": str }]`

### POST `/api/categories`
**Request**: `{ "name": str }`
**Response 201**: `{ "id": int, "name": str }`

---

## 3. Menus (`/api/menus`)

### GET `/api/menus`
**Response 200**: `[{ "id": int, "name": str, "description": str|null, "price": int, "hpp": int, "imageUrl": str|null, "categoryId": int, "category": { "id": int, "name": str }, "soldCount": int, "recipeNotes": str|null }]`

### POST `/api/menus`
**Content-Type**: `multipart/form-data`
**Fields**: name, description, price, categoryId, hpp, image(file)|imageUrl(str)
**Response 201**: Menu object

### PUT `/api/menus/:id`
**Content-Type**: `multipart/form-data`
**Fields**: name, description, price, categoryId, hpp, image(file)|imageUrl(str)
**Response 200**: Menu object

### DELETE `/api/menus/:id`
**Response 204**: No content
**Response 400**: `{ "error": "Cannot delete menu because it is already used in transactions..." }`

---

## 4. Checkout (`/api/checkout`)

### POST `/api/checkout`
**Request**:
```json
{
  "nickname": str,
  "totalAmount": int,
  "items": [{ "menuId": int, "quantity": int, "price": int }],
  "rewardId": int|null,
  "paymentMethod": "CASH"|"QRIS"|etc,
  "shiftId": int|null
}
```
**Response 201**:
```json
{
  "message": "Checkout successful",
  "customer": { ...full customer object... },
  "transaction": { ...with items... },
  "luckyDrop": { "bonusPoints": int } | null
}
```

### GET `/api/checkout/history`
**Response 200**: `[{ Transaction with customer and items[with menu] }]` (latest 50)

### POST `/api/checkout/sync`
**Request**: `{ "transactions": [{ ...same as checkout... }] }`
**Response 201**: `{ "message": "Sync successful", "syncedCount": int }`

### POST `/api/checkout/history/:id/void`
**Request**: `{ "voidReason": str, "voidedBy": int }`
**Response 200**: Updated transaction object

---

## 5. Customers (`/api/customers`)

### GET `/api/customers`
**Response 200**: Customer[] with `_count.transactions`, `badges[{ badge }]`, `quests[{ quest }]`

### GET `/api/customers/search?nickname=xxx`
**Response 200**: Customer with badges and quests
**Response 404**: `{ "error": "Customer not found" }`

---

## 6. Analytics (`/api/analytics`)

### GET `/api/analytics?days=7|30|all&startDate=&endDate=`
**Response 200**:
```json
{
  "totalRevenue": int,
  "totalExpenses": int,
  "netProfit": int,
  "totalOrders": int,
  "totalCustomers": int,
  "topCustomers": [...],
  "chartData": [{ "date": str, "revenue": int }],
  "popularMenus": [{ "name": str, "count": int }]
}
```

### GET `/api/analytics/reports?days=&startDate=&endDate=`
**Response 200**: Transaction[] with customer and items(with menu)

---

## 7. Gamification (`/api/gamification`)

### CRUD `/api/gamification/quests`
- GET `/quests` → Quest[] (active only)
- POST `/quests` → `{ name, description, targetValue, rewardPoints, rewardXp, type, targetEntityId }`
- PUT `/quests/:id` → same fields
- DELETE `/quests/:id` → soft delete (active=false)

### CRUD `/api/gamification/badges`
- GET `/badges` → Badge[]
- POST `/badges` → `{ name, description, iconUrl, requiredTransactions }`
- PUT `/badges/:id` → same fields
- DELETE `/badges/:id` → hard delete (cascade CustomerBadge)

### CRUD `/api/gamification/rewards`
- GET `/rewards` → Reward[] (active only)
- POST `/rewards` → `{ name, description, pointsRequired }`
- PUT `/rewards/:id` → same fields
- DELETE `/rewards/:id` → soft delete (active=false)

### POST `/api/gamification/redeem`
**Request**: `{ "customerId": int, "rewardId": int }`
**Response 200**: `{ "message": "Redeem successful", "customer": {...} }`

### POST `/api/gamification/spin`
**Request**: `{ "customerId": int }`
**Response 200**: `{ "message": "Spin completed", "rewardName": str, "bonusPoints": int, "bonusXp": int, "customer": {...} }`
**Cost**: 50 points

---

## 8. Inventory (`/api/inventory`)

### CRUD Items
- GET `/` → InventoryItem[]
- POST `/` (multipart: name, stock, unit, image) → InventoryItem
- PUT `/:id` (multipart: name, unit, image) → InventoryItem
- PUT `/:id/adjust` (multipart: quantity, type[IN|OUT], notes, receipt) → InventoryItem

### Opname
- GET `/opname/today` → `{ "status": "OPEN"|"NOT_OPEN", "opname": {...}|null, "inventory": [...]|null }`
- POST `/opname/open` → `{ "items": [{ inventoryItemId, openingStock, morningNotes }] }`
- POST `/opname/confirm-stock` → DailyOpname
- POST `/opname/cancel-confirm-stock` → DailyOpname
- POST `/opname/close` → `{ "opnameId": int, "items": [{ inventoryItemId, closingStock, nightNotes }] }`
- GET `/opname/history` → DailyOpname[] (CLOSED)

---

## 9. Expenses (`/api/expenses`)

### GET `/api/expenses?days=&startDate=&endDate=`
**Response**: Expense[] with category and recordedBy(username)

### POST `/api/expenses` (multipart)
**Fields**: amount, date, notes, categoryId, userId, receipt(file)

### GET `/api/expenses/summary`
**Response**: `{ "totalExpenses": int, "categoryGroup": [...] }`

### GET `/api/expenses/categories`
**Response**: ExpenseCategory[]

### POST `/api/expenses/categories`
**Request**: `{ "name": str, "description": str }`

### POST `/api/expenses/seed-categories`
Seeds: Bahan Baku, Operasional, Gaji, Sewa, Lain-lain

---

## 10. Settings (`/api/settings`)

### GET `/api/settings`
**Response**: SystemSettings[]

### POST `/api/settings`
**Request**: `{ "key": str, "value": str, "description": str|null }`
**Response**: Upserted SystemSettings object

---

## 11. Shift (`/api/shift`)

### POST `/api/shift/open` (Auth Required)
**Request**: `{ "startingCash": int }`
**Response 201**: Shift object

### GET `/api/shift/current` (Auth Required)
**Response**: `{ "currentShift": Shift|null }`

### POST `/api/shift/close` (Auth Required)
**Request**: `{ "endingCash": int }`
**Response**: Closed shift with expectedEndingCash

### GET `/api/shift/reports`
**Response**: Shift[] with user{username} and transactions[]

---

## 12. Role Access (`/api/role-access`)

### GET `/api/role-access/menus`
**Response**: AppMenu[]

### GET `/api/role-access/:role`
**Response**: RoleAccess[] with appMenu

### PUT `/api/role-access/:role`
**Request**: `{ "accesses": [{ "appMenuId": int, "canView": bool, "canEdit": bool }], "userId": int }`

### POST `/api/role-access/menus`
**Request**: `{ "name": str, "path": str, "icon": str }`

---

## 13. Recipes (`/api/recipes`)

### GET `/api/recipes`
**Response**: Menu[] (with recipeNotes)

### POST `/api/recipes/:menuId`
**Request**: `{ "recipeNotes": str }`

---

## 14. Logs (`/api/logs`)

### GET `/api/logs`
**Response**: SystemLog[] with user{username, role} (latest 200)

---

## Static Files

### `/uploads/<filename>`
Serve static uploaded files from `public/uploads/` directory.
