# Frontend API Guide (New Routes)

This document covers only the new API routes and auth changes needed for frontend screens.

## Base Notes

- Base path examples assume backend root, e.g. `/main/api/...`
- Content type: `application/json`
- All consume routes now require a Bearer token.

---

## 1) API Login (Get Tokens)

### Route
`POST /main/api/auth/login/`

### Request Body
```json
{
  "username": "scanner_admin_1",
  "password": "your-password"
}
```

### Success Response (200)
```json
{
  "access": "<jwt-access-token>",
  "refresh": "<jwt-refresh-token>",
  "user": {
    "id": 12,
    "username": "scanner_admin_1",
    "is_staff": false
  }
}
```

### Error Responses
- `400` → missing username/password
- `401` → invalid credentials
- `403` → account not allowed for scanner API

---

## 2) Auth Change for All Consume Routes

The following routes **must** include:

`Authorization: Bearer <access-token>`

Routes:
- `POST /main/api/lunch/`
- `POST /main/api/dinner/`
- `POST /main/api/bbq/`
- `POST /main/api/drink/`

If token is missing/invalid, DRF returns unauthorized/forbidden response.

---

## 3) Consume Lunch

### Route
`POST /main/api/lunch/`

### Request Body
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "gender": "M"
}
```

### Success Response (200)
Returns serialized user data (remaining allowances and user fields), example:
```json
{
  "id": 101,
  "first_name": "John",
  "last_name": "Doe",
  "full_name": "John Doe",
  "gender": "M",
  "lunches_remaining": 2,
  "dinners_remaining": 3,
  "drinks_remaining": 15,
  "rotary_club": "Kampala North",
  "membership": "ROTARY",
  "delegate_reg_id": "D-1001",
  "has_friday_lunch": true,
  "has_saturday_lunch": false,
  "has_bbq": true
}
```

### Common Errors
- `400` required fields missing / no lunches remaining
- `403` not allowed account / wrong lunch day for user
- `404` user not found

---

## 4) Consume Dinner

### Route
`POST /main/api/dinner/`

### Request Body
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "gender": "M"
}
```

### Success Response (200)
Same user payload shape as lunch endpoint.

### Common Errors
- `400` required fields missing / no dinners remaining
- `403` not allowed account
- `404` user not found

---

## 5) Consume BBQ (One-Time)

### Route
`POST /main/api/bbq/`

### Request Body
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "gender": "M"
}
```

### Success Response (200)
Same user payload shape as lunch endpoint.

### Common Errors
- `400` required fields missing
- `403` not allowed account / user has no BBQ access
- `404` user not found
- `409` user already consumed BBQ

---

## 6) Consume Drink (Now Supports Multiple Drinks)

### Route
`POST /main/api/drink/`

### Request Body (New Multi-Item Format)
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "gender": "M",
  "serving_point": "Main Bar",
  "items": [
    { "drink_name": "Water", "quantity": 2 },
    { "drink_name": "Soda", "quantity": 1 }
  ]
}
```

### Success Response (202)
```json
{
  "message": "Drink order submitted for approval",
  "status": "pending",
  "user": {
    "id": 101,
    "first_name": "John",
    "last_name": "Doe",
    "full_name": "John Doe",
    "gender": "M",
    "lunches_remaining": 2,
    "dinners_remaining": 3,
    "drinks_remaining": 15,
    "rotary_club": "Kampala North",
    "membership": "ROTARY",
    "delegate_reg_id": "D-1001",
    "has_friday_lunch": true,
    "has_saturday_lunch": false,
    "has_bbq": true
  },
  "transactions": [
    {
      "id": 901,
      "user_name": "John Doe",
      "drink_name": "Water",
      "quantity": 2,
      "serving_point": "Main Bar",
      "status": "pending",
      "served_at": "2026-02-22T15:09:10.120Z",
      "approved_at": null,
      "scanned_by_username": "scanner_admin_1"
    },
    {
      "id": 902,
      "user_name": "John Doe",
      "drink_name": "Soda",
      "quantity": 1,
      "serving_point": "Main Bar",
      "status": "pending",
      "served_at": "2026-02-22T15:09:10.221Z",
      "approved_at": null,
      "scanned_by_username": "scanner_admin_1"
    }
  ],
  "total_requested": 3
}
```

### Backward Compatibility
Legacy format is still accepted:
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "gender": "M",
  "serving_point": "Main Bar",
  "drink_name": "Water",
  "quantity": 2
}
```

### Common Errors
- `400` missing required fields / invalid quantity / insufficient allowance / insufficient stock
- `403` not allowed account
- `404` user not found / drink type not found

---

## Frontend Flow Summary

1. Call login route once with username/password.
2. Save `access` token (and `refresh` if your app uses refresh flow).
3. Send `Authorization: Bearer <access-token>` on every consume route call.
4. For drink screen, send multiple selections in `items`.
