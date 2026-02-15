# Migration Guide: Google Sheets → Local CSV Import

## What Changed

The system has been migrated from runtime Google Sheets fetching to a **local CSV import workflow**. All user verification now happens against the local database only.

## New Architecture

### Before
- API endpoints fetched user data from Google Sheets at runtime (with caching)
- Users were created on-the-fly if found in the sheet
- Required network access to Google Sheets API

### After
- All users are pre-imported from local CSV files into the database
- API endpoints verify users against the local database only
- No runtime network dependencies for user verification
- More reliable and faster user lookups

## Setup Steps

### 1. Place CSV Files in Project Root

Ensure these files exist:
```
/Users/mulindwa/Documents/projects/dinner_backend/lunch_bbq_data.csv
/Users/mulindwa/Documents/projects/dinner_backend/other_data.csv
```

**lunch_bbq_data.csv** should contain:
- `Delegate Reg ID`
- `Delegate Name`
- `Membership`
- `Club Name`
- `Extra Name` (Friday Lunch | Saturday Lunch | Meat & Greet BBQ)
- `UUID`

**other_data.csv** should contain:
- `Delegate Reg ID`
- `Delegate Name`
- `Membership`
- `Club Name`
- `Extra Name` (Female Bag | Male Bag | Blouse | Shirt | etc.)
- `Size`
- `UUID`

### 2. Run Migrations

```bash
python manage.py migrate
```

This creates new database fields:
- `delegate_reg_id`
- `external_uuid`
- `membership`
- `has_friday_lunch`
- `has_saturday_lunch`
- `has_bbq`

### 3. Import Data

```bash
python manage.py import_event_data
```

Optional flags:
- `--reset-users`: Delete all existing users before import
- `--lunch-csv <path>`: Custom path to lunch/bbq CSV
- `--other-csv <path>`: Custom path to other registrations CSV

Example with custom paths:
```bash
python manage.py import_event_data \
  --lunch-csv ~/Downloads/lunch_data.csv \
  --other-csv ~/Downloads/other_data.csv \
  --reset-users
```

### 4. Verify Import

Check user count:
```bash
python manage.py shell -c "from main.models import User; print(f'Total users: {User.objects.count()}')"
```

Check event registrations:
```bash
python manage.py shell -c "from main.models import User; print(f'Friday Lunch: {User.objects.filter(has_friday_lunch=True).count()}'); print(f'Saturday Lunch: {User.objects.filter(has_saturday_lunch=True).count()}'); print(f'BBQ: {User.objects.filter(has_bbq=True).count()}')"
```

## Import Logic

### User Matching Priority
1. Match by `external_uuid` (if present)
2. Match by `delegate_reg_id` (if present)
3. Match by name (`first_name` + `last_name`)

### Gender Inference
Since the CSV files don't have explicit gender fields, gender is inferred from merchandise orders:
- "Female Bag" or "Blouse" → Female (F)
- "Male Bag" or "Shirt" → Male (M)
- Otherwise → Unknown (UNKNOWN)

### Meal Entitlements
- `Friday Lunch` → `has_friday_lunch=True`, `lunches_remaining += 1`
- `Saturday Lunch` → `has_saturday_lunch=True`, `lunches_remaining += 1`
- `Meat & Greet BBQ` → `has_bbq=True`, `dinners_remaining += 1`

### Drinks
All users get default `drinks_remaining = 15` (User.WEEKLY_DRINKS)

## API Changes

### Endpoint Behavior
All API endpoints now require users to exist in the database:

**Before:**
- User not in DB → Check Google Sheet → Create user if found
- User in DB → Use DB record

**After:**
- User not in DB → Return 404 error
- User in DB → Use DB record

### Error Messages
```json
{
  "error": "User was not found in registry"
}
```

This means the user needs to be imported via `import_event_data` command.

## Updated API Response

User objects now include event metadata:

```json
{
  "id": 1,
  "first_name": "Elizabeth",
  "last_name": "Ongom",
  "full_name": "Elizabeth Ongom",
  "gender": "F",
  "lunches_remaining": 2,
  "dinners_remaining": 1,
  "drinks_remaining": 15,
  "rotary_club": "Bulindo",
  "membership": "ROTARY",
  "delegate_reg_id": "7406",
  "has_friday_lunch": true,
  "has_saturday_lunch": true,
  "has_bbq": true
}
```

## Removed Dependencies

- **Google Sheets API configuration** (removed from settings.py)
- **Cache configuration** for Google Sheets data (removed)
- **requests library** (no longer needed for Google Sheets fetching)

## Troubleshooting

### "User was not found in registry"
**Solution:** Import the user data:
```bash
python manage.py import_event_data
```

### Import creates 0 users
**Causes:**
- CSV files not found in project root
- CSV files have incorrect format or encoding

**Solution:**
- Verify file paths match the expected locations
- Ensure CSV files use UTF-8 encoding
- Check CSV headers match expected column names

### Gender shows as "UNKNOWN" for all users
**Cause:** The `other_data.csv` doesn't contain merchandise orders for those users

**Solution:** This is expected behavior. Gender can be manually updated in Django admin if needed.

### Duplicate users after re-import
**Solution:** Use `--reset-users` flag to clear existing users first:
```bash
python manage.py import_event_data --reset-users
```

## Testing the Setup

### 1. Start the server
```bash
python manage.py runserver
```

### 2. Test user lookup
```bash
curl -X GET "http://localhost:8000/main/api/user/?first_name=Elizabeth&last_name=Ongom&gender=F"
```

### 3. Test meal consumption
```bash
curl -X POST http://localhost:8000/main/api/lunch/ \
  -H "Content-Type: application/json" \
  -d '{"first_name": "Elizabeth", "last_name": "Ongom", "gender": "F"}'
```

### 4. Test admin dashboard
Visit: `http://localhost:8000/administrator/`

## Rollback (if needed)

If you need to restore the old Google Sheets behavior:

1. Restore original `views.py` from git history
2. Restore original `settings.py` with Google Sheets config
3. Re-add `requests` to requirements.txt
4. Run `pip install -r requirements.txt`

Note: The new database fields are harmless and can remain even if you rollback.
