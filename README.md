# Dinner Backend - Event Meal Management System

A Django REST API for managing lunch, dinner, and drink allowances at events.

## Quick Start

```bash
# 1. Place CSV files in project root:
#    - lunch_bbq_data.csv
#    - other_data.csv

# 2. Run setup script
./setup.sh

# 3. Start server
python manage.py runserver
```

For detailed migration guide, see [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md).

## Local CSV import workflow (DB-only)

The app now uses local DB records only (no Google Sheets fetch at runtime).

Source files expected at project root:
- `lunch_bbq_data.csv`
- `other_data.csv`

Run import:

```bash
python manage.py migrate
python manage.py import_event_data
```

Optional reset of users before import:

```bash
python manage.py import_event_data --reset-users
```

Import behavior:
- Creates/updates users from both CSV files.
- Maps `Friday Lunch` + `Saturday Lunch` to `lunches_remaining`.
- Maps `Meat & Greet BBQ` to `dinners_remaining`.
- Stores delegate metadata (`delegate_reg_id`, `external_uuid`, `membership`, `rotary_club`).


## API Endpoints

Base URL: `http://localhost:8000/main/api/`

---

### 1. Consume Lunch
**Endpoint:** `POST /main/api/lunch/`

**Request Body:**
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "gender": "M"
}
```

**Success Response (200):**
```json
{
  "id": 1,
  "first_name": "John",
  "last_name": "Doe",
  "full_name": "John Doe",
  "gender": "M",
  "lunches_remaining": 4,
  "dinners_remaining": 5,
  "drinks_remaining": 10
}
```

**Error Responses:**

Missing Parameters (400):
```json
{
  "error": "first_name, last_name and gender are required"
}
```

User Not Found (404):
```json
{
  "error": "User not found in registry"
}
```

No Lunches Remaining (400):
```json
{
  "error": "No lunches remaining"
}
```

---

### 2. Consume Dinner
**Endpoint:** `POST /main/api/dinner/`

**Request Body:**
```json
{
  "first_name": "Jane",
  "last_name": "Smith",
  "gender": "F"
}
```

**Success Response (200):**
```json
{
  "id": 2,
  "first_name": "Jane",
  "last_name": "Smith",
  "full_name": "Jane Smith",
  "gender": "F",
  "lunches_remaining": 5,
  "dinners_remaining": 4,
  "drinks_remaining": 10
}
```

**Error Responses:**
Same as Consume Lunch, but with "No dinners remaining" message.

---

### 3. Consume Drink
**Endpoint:** `POST /main/api/drink/`

**Request Body:**
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "gender": "M",
  "serving_point": "Bar A",
  "drink_name": "Coca Cola",
  "quantity": 2
}
```

**Request Body Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| first_name | string | Yes | User's first name |
| last_name | string | Yes | User's last name |
| gender | string | Yes | M or F |
| serving_point | string | Yes | Location where drink is served (e.g., "Bar A", "Pool Bar") |
| drink_name | string | Yes | Name of the drink (must exist in inventory) |
| quantity | integer | No | Number of drinks (default: 1) |

**Success Response (200):**
```json
{
  "user": {
    "id": 1,
    "first_name": "John",
    "last_name": "Doe",
    "full_name": "John Doe",
    "gender": "M",
    "lunches_remaining": 5,
    "dinners_remaining": 5,
    "drinks_remaining": 8
  },
  "transaction": {
    "id": 1,
    "user_name": "John Doe",
    "drink_name": "Coca Cola",
    "quantity": 2,
    "serving_point": "Bar A",
    "served_at": "2024-01-15T14:30:00Z"
  },
  "drink_stock_remaining": 48
}
```

**Error Responses:**

Missing Parameters (400):
```json
{
  "error": "serving_point is required"
}
```

Drink Not Found (404):
```json
{
  "error": "Drink type \"Coca Cola\" not found"
}
```

Insufficient Stock (400):
```json
{
  "error": "Insufficient stock. Only 3 Coca Cola available"
}
```

Insufficient Allowance (400):
```json
{
  "error": "Insufficient allowance. Only 5 drinks remaining"
}
```

---

### 4. Get User Status
**Endpoint:** `GET /main/api/user/`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| first_name | string | Yes | User's first name |
| last_name | string | Yes | User's last name |
| gender | string | Yes | M or F |

**Example Request:**
```
GET /main/api/user/?first_name=John&last_name=Doe&gender=M
```

**Success Response (200):**
```json
{
  "id": 1,
  "first_name": "John",
  "last_name": "Doe",
  "full_name": "John Doe",
  "gender": "M",
  "lunches_remaining": 5,
  "dinners_remaining": 5,
  "drinks_remaining": 10
}
```

**Error Responses:**

User Not Found (404):
```json
{
  "error": "User not found"
}
```

---

### 5. List Available Drinks
**Endpoint:** `GET /main/api/drinks/`

**Query Parameters:** None

**Example Request:**
```
GET /main/api/drinks/
```

**Success Response (200):**
```json
[
  {
    "id": 1,
    "name": "Coca Cola",
    "available_quantity": 50
  },
  {
    "id": 2,
    "name": "Sprite",
    "available_quantity": 30
  },
  {
    "id": 3,
    "name": "Water",
    "available_quantity": 100
  }
]
```

---

### 6. Add/Update Drink Stock
**Endpoint:** `POST /main/api/drinks/stock/`

**Request Body:**
```json
{
  "drink_name": "Coca Cola",
  "quantity": 50
}
```

**Success Response (200):**
```json
{
  "message": "Created Coca Cola",
  "drink": {
    "id": 1,
    "name": "Coca Cola",
    "available_quantity": 50
  }
}
```

---

### 7. Get Drink Transactions
**Endpoint:** `GET /main/api/drinks/transactions/`

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| serving_point | string | No | Filter by serving point |
| first_name | string | No | Filter by user first name (requires last_name) |
| last_name | string | No | Filter by user last name (requires first_name) |

**Example Request:**
```
GET /main/api/drinks/transactions/?serving_point=Bar A
```

**Success Response (200):**
```json
[
  {
    "id": 3,
    "user_name": "Jane Smith",
    "drink_name": "Sprite",
    "quantity": 1,
    "serving_point": "Bar A",
    "served_at": "2024-01-15T15:00:00Z"
  },
  {
    "id": 2,
    "user_name": "John Doe",
    "drink_name": "Coca Cola",
    "quantity": 2,
    "serving_point": "Bar A",
    "served_at": "2024-01-15T14:30:00Z"
  }
]
```

---

## Business Rules

### Weekly Allowances
- **Lunches**: 5 per week (max 1 per day)
- **Dinners**: 5 per week (max 1 per day)
- **Drinks**: 10 per week (no daily limit, supports multiple drinks per transaction)

### Automatic Reset
- Allowances automatically reset to default values after 7 days from the user's first check-in
- Week starts from the first time a user consumes a meal/drink

### User Verification
- All users must exist in the Google Sheet registry
- User lookup is based on exact match of: `firstName`, `lastName`, and `gender`
- New users are created in the database on first check-in if found in the sheet

### Drink Inventory
- Each drink type has a tracked inventory quantity
- Stock is deducted when drinks are served
- Transactions are logged with serving point, drink type, and quantity
- Admin can add/update drink stock via API or Django admin

### Serving Points
- Required for all drink transactions
- Used to track which location served the drink
- Can be any string value (e.g., "Bar A", "Pool Bar", "Main Lounge")

### Response Data
All successful requests return the same user object with current allowances:
- `id`: Database ID
- `first_name`: First name
- `last_name`: Last name  
- `full_name`: Combined first and last name
- `gender`: M or F
- `lunches_remaining`: Remaining lunch count (0-5)
- `dinners_remaining`: Remaining dinner count (0-5)
- `drinks_remaining`: Remaining drink count (0-10)
