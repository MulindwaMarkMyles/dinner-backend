# Consume API Reference

All consume endpoints require a valid **JWT Bearer token** in the `Authorization` header and the caller must be in the `API_SCANNER_ADMIN` group (or be staff/superuser).

---

## Authentication

### `POST /main/api/auth/login/`

Obtain access and refresh tokens.

**Request**
```json
{ "username": "scanner_user", "password": "secret" }
```

**Response `200`**
```json
{
  "access": "<jwt_access_token>",
  "refresh": "<jwt_refresh_token>",
  "user": { "id": 1, "username": "scanner_user", "is_staff": true }
}
```

---

## Consume Lunch

### `POST /main/api/lunch/`

Marks a lunch as consumed for the user. A user may only have **one lunch per day**.

**Request**
```json
{ "first_name": "Charles", "last_name": "Odaga" }
```

**Response `200` — Success**
```json
{
  "message": "Lunch consumed successfully",
  "lunches_remaining": 2,
  "user": {
    "id": 42,
    "ticket_id": "uuid...",
    "first_name": "Charles",
    "last_name": "Odaga",
    "full_name": "Charles Odaga",
    "lunches_remaining": 2,
    "dinners_remaining": 3,
    "drinks_remaining": 15,
    "rotary_club": "Kampala",
    "membership": "active",
    "delegate_reg_id": "REG001",
    "has_friday_lunch": false,
    "has_saturday_lunch": false,
    "has_bbq": true
  }
}
```

**Error responses**

| Status | Condition |
|--------|-----------|
| `400` | `"No lunches remaining"` |
| `403` | `"You are only registered for Friday lunch"` (or Saturday) |
| `404` | `"User was not found in registry"` |
| `409` | `"User has already consumed lunch today"` |

---

## Consume Dinner

### `POST /main/api/dinner/`

Marks a dinner as consumed. A user may only have **one dinner per day**.

**Request**
```json
{ "first_name": "Charles", "last_name": "Odaga" }
```

**Response `200` — Success**
```json
{
  "message": "Dinner consumed successfully",
  "dinners_remaining": 2,
  "user": { "...same user object as above..." }
}
```

**Error responses**

| Status | Condition |
|--------|-----------|
| `400` | `"No dinners remaining"` |
| `404` | `"User was not found in registry"` |
| `409` | `"User has already consumed dinner today"` |

---

## Consume BBQ

### `POST /main/api/bbq/`

Marks the BBQ ticket as consumed. Can only be used **once total** (not per day).

**Request**
```json
{ "first_name": "Charles", "last_name": "Odaga" }
```

**Response `200` — Success**
```json
{
  "id": 42,
  "first_name": "Charles",
  "last_name": "Odaga",
  "has_bbq": true,
  "...rest of user object..."
}
```

**Error responses**

| Status | Condition |
|--------|-----------|
| `403` | `"User does not have access for BBQ"` |
| `404` | `"User was not found in registry"` |
| `409` | `"User has already consumed BBQ ticket"` |

---

## Consume Drinks

### `POST /main/api/drink/`

Submits a drink order. A user may make **multiple requests per day** but their total cannot exceed **5 drinks per day**. The order is placed with `pending` status and waits for approval.

**Request**

`items` is a dict mapping drink names to quantities.

```json
{
  "first_name": "Charles",
  "last_name": "Odaga",
  "serving_point": "Bar A",
  "items": {
    "Sparkling Water": 2,
    "Iced Tea": 1
  }
}
```

**Response `202` — Accepted (pending approval)**
```json
{
  "message": "Drink order submitted for approval",
  "status": "pending",
  "total_requested": 3,
  "drinks_remaining_today": 2,
  "user": { "...user object..." },
  "transactions": [
    {
      "id": 10,
      "user_name": "Charles Odaga",
      "drink_name": "Sparkling Water",
      "quantity": 2,
      "serving_point": "Bar A",
      "status": "pending",
      "served_at": "2026-03-01T14:00:00Z",
      "approved_at": null,
      "scanned_by_username": "scanner_user"
    },
    {
      "id": 11,
      "user_name": "Charles Odaga",
      "drink_name": "Iced Tea",
      "quantity": 1,
      "serving_point": "Bar A",
      "status": "pending",
      "served_at": "2026-03-01T14:00:00Z",
      "approved_at": null,
      "scanned_by_username": "scanner_user"
    }
  ]
}
```

> `drinks_remaining_today` = `5 - (drinks already ordered today) - (this request's total)`.  
> Denied transactions do **not** count against the daily limit.

**Error responses**

| Status | Condition |
|--------|-----------|
| `400` | `"Daily drink limit of 5 reached"` |
| `400` | `"Request exceeds daily limit. You can have at most N more drink(s) today"` |
| `400` | `"Insufficient stock. Only N <drink> available"` |
| `400` | `"Quantity for '<drink>' must be a positive integer"` |
| `404` | `"User was not found in registry"` |
| `404` | `"Drink type '<name>' not found"` |

---

## User Object Reference

All successful consume responses include a `user` object with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Internal user ID |
| `ticket_id` | uuid | Unique ticket UUID |
| `first_name` | string | First name |
| `last_name` | string | Last name |
| `full_name` | string | Combined name (read-only) |
| `lunches_remaining` | int | Weekly lunches still available |
| `dinners_remaining` | int | Weekly dinners still available |
| `drinks_remaining` | int | Weekly drinks counter (informational) |
| `rotary_club` | string\|null | Club affiliation |
| `membership` | string\|null | Membership type |
| `delegate_reg_id` | string\|null | Registration ID |
| `has_friday_lunch` | bool | Registered for Friday lunch |
| `has_saturday_lunch` | bool | Registered for Saturday lunch |
| `has_bbq` | bool | Has a BBQ ticket |

---

## LLM Query Endpoint

### `GET /main/api/llm/query/`

A read-only data endpoint designed for LLMs to query the current state of attendees and their meal history. Requires a valid JWT token.

**Authentication**: Open

---

### Query Parameters (all optional)

| Parameter | Type | Description |
|-----------|------|-------------|
| `first_name` | string | Filter by first name (case-insensitive) |
| `last_name` | string | Filter by last name (case-insensitive) |

Both filters can be combined to narrow results to a specific person.  
When **no filters are provided**, results are capped at the **50 most recent meal logs** to avoid large payloads.  
When **either filter is set**, all matching users and all their meal logs are returned (no cap).

---

### Example Requests

**All data (latest 50 logs)**
```
GET /main/api/llm/query/
Authorization: Bearer <token>
```

**Filter by first name only**
```
GET /main/api/llm/query/?first_name=Charles
Authorization: Bearer <token>
```

**Filter by full name (exact person)**
```
GET /main/api/llm/query/?first_name=Charles&last_name=Odaga
Authorization: Bearer <token>
```

---

### Response `200`

```json
{
  "users": [
    {
      "id": 42,
      "ticket_id": "uuid...",
      "first_name": "Charles",
      "last_name": "Odaga",
      "full_name": "Charles Odaga",
      "lunches_remaining": 2,
      "dinners_remaining": 3,
      "drinks_remaining": 15,
      "rotary_club": "Kampala",
      "membership": "active",
      "delegate_reg_id": "REG001",
      "has_friday_lunch": false,
      "has_saturday_lunch": false,
      "has_bbq": true
    }
  ],
  "meal_logs": [
    {
      "id": 101,
      "user": 42,
      "meal_type": "lunch",
      "consumed_at": "2026-03-01T12:30:00Z",
      "scanned_by_username": "scanner_user"
    },
    {
      "id": 99,
      "user": 42,
      "meal_type": "dinner",
      "consumed_at": "2026-02-28T19:45:00Z",
      "scanned_by_username": "scanner_user"
    }
  ]
}
```

### Response Fields

| Field | Description |
|-------|-------------|
| `users` | List of matched user objects (see User Object Reference above) |
| `meal_logs` | List of meal log entries for the matched users, ordered newest first |

### `meal_logs` entry fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Log entry ID |
| `user` | int | ID of the user this log belongs to |
| `meal_type` | string | `lunch`, `dinner`, `drink`, or `bbq` |
| `consumed_at` | datetime | Timestamp when the meal was logged (UTC) |
| `scanned_by_username` | string | Username of the scanner who recorded it |

---

### Behaviour Summary

| Scenario | Users returned | Logs returned |
|----------|---------------|---------------|
| No filters | All users | Latest 50 logs (any user) |
| `first_name` only | All users with that first name | All logs for those users |
| `last_name` only | All users with that last name | All logs for those users |
| `first_name` + `last_name` | Exact name match | All logs for that person |

> **Tip for LLMs**: use `first_name` + `last_name` together to pin down a specific person, then read `lunches_remaining`, `dinners_remaining` in the `users` array alongside their `meal_logs` to understand their full consumption history.
