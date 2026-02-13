import csv
from io import StringIO

import requests
from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import DrinkTransaction, DrinkType, MealLog, User
from .serializers import DrinkTransactionSerializer, DrinkTypeSerializer, UserSerializer


# Fetch data from Google Sheets as CSV with caching
def get_google_sheet_data():
    """Fetch data from Google Sheets as CSV with 5-minute cache"""
    cached_data = cache.get("google_sheet_data")
    if cached_data is not None:
        return cached_data

    try:
        response = requests.get(settings.GOOGLE_SHEETS_CSV_URL, timeout=10)
        response.raise_for_status()

        csv_data = StringIO(response.text)
        reader = csv.DictReader(csv_data)
        data = list(reader)

        # Cache for 5 minutes
        cache.set("google_sheet_data", data, 300)
        return data
    except Exception as e:
        print(f"Error fetching from Google Sheets: {e}")
        return None


def normalize_gender(gender):
    """Normalize gender input to handle F/M and FEMALE/MALE formats"""
    if not gender:
        return "UNKNOWN"

    gender = gender.strip().upper()

    # Map common gender values
    gender_map = {
        "FEMALE": "F",
        "MALE": "M",
        "F": "F",
        "M": "M",
        "UNKNOWN": "UNKNOWN",
    }

    return gender_map.get(gender, "UNKNOWN")


def normalize_name(name):
    """Normalize names by trimming and collapsing whitespace (preserve titles)."""
    if not name:
        return ""
    return " ".join(name.strip().split())


def find_user_in_sheet(first_name, last_name, gender):
    """Search for user in Google Sheet by FULLNAME (new sheet structure has FULLNAME, PHONE NUMBER, EMAIL, CLUB)"""
    data = get_google_sheet_data()
    if not data:
        print("No data from Google Sheets")
        return None

    # Normalize search terms
    search_first = normalize_name(first_name).lower()
    search_last = normalize_name(last_name).lower()
    search_gender = normalize_gender(gender)
    search_full = (
        f"{normalize_name(first_name)} {normalize_name(last_name)}".strip().lower()
    )
    print(
        f"[sheet-search] raw=({first_name}, {last_name}, {gender}) normalized=({search_first}, {search_last}, {search_gender}) full={search_full}"
    )

    for row in data:
        # New sheet has FULLNAME column
        sheet_fullname = normalize_name(row.get("FULLNAME", "")).strip().lower()
        print(f"[sheet-row] fullname={sheet_fullname}")

        # Match by full name (ignore gender since sheet doesn't have it)
        if sheet_fullname == search_full:
            print(f"✓ User found: {first_name} {last_name}")
            return row

        # Also try matching just by comparing the names
        # Split the sheet fullname and compare
        sheet_parts = sheet_fullname.split()
        search_parts = search_full.split()

        if len(sheet_parts) >= 2 and len(search_parts) >= 2:
            # Compare first and last names flexibly
            if (
                sheet_parts[0] == search_parts[0]
                and sheet_parts[-1] == search_parts[-1]
            ):
                print(f"✓ User found (flexible match): {first_name} {last_name}")
                return row

    print(f"✗ User not found: {first_name} {last_name}")
    return None


def verify_user_exists(first_name, last_name, gender):
    """Fast check if user exists - checks DB first, then sheet"""
    # Normalize gender
    normalized_gender = normalize_gender(gender)
    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)
    print(
        f"[verify] raw=({first_name}, {last_name}, {gender}) normalized=({normalized_first}, {normalized_last}, {normalized_gender})"
    )

    # First check if user already exists in DB (check by name, ignore gender for matching)
    try:
        print("[verify] checking DB")
        # Try to find by first_name and last_name, regardless of gender
        users = User.objects.filter(
            first_name__iexact=normalized_first, last_name__iexact=normalized_last
        )

        if users.exists():
            # If we have an exact match with gender, use it
            user = users.filter(gender__iexact=normalized_gender).first()
            if user:
                print("[verify] DB exact match found")
                return True, user
            # Otherwise use the first match (name matches, different gender)
            user = users.first()
            print("[verify] DB name match found (different gender)")
            return True, user

        print("[verify] DB miss")
    except Exception as e:
        print(f"[verify] DB error: {e}")

    # Check sheet
    print("[verify] checking sheet")
    sheet_user = find_user_in_sheet(
        normalized_first, normalized_last, normalized_gender
    )
    if sheet_user:
        print("[verify] sheet match found")
        return True, None
    print("[verify] sheet miss")
    return False, None


@api_view(["POST"])
def consume_lunch(request):
    first_name = request.data.get("first_name")
    last_name = request.data.get("last_name")
    gender = request.data.get("gender")

    if not first_name or not last_name or not gender:
        return Response(
            {"error": "first_name, last_name and gender are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Normalize gender
    normalized_gender = normalize_gender(gender)
    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)
    print(
        f"Received lunch request for: {normalized_first} {normalized_last} gender={normalized_gender}"
    )

    # Quick verification
    exists, existing_user = verify_user_exists(
        normalized_first, normalized_last, normalized_gender
    )
    if not exists:
        return Response(
            {"error": "User was not found in registry"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Get or create user
    if existing_user:
        user = existing_user
    else:
        user, created = User.objects.get_or_create(
            first_name=normalized_first,
            last_name=normalized_last,
            gender=normalized_gender,
        )

    user.reset_weekly_allowance()

    if user.lunches_remaining <= 0:
        return Response(
            {"error": "No lunches remaining"}, status=status.HTTP_400_BAD_REQUEST
        )

    user.lunches_remaining -= 1
    user.save()
    MealLog.objects.create(user=user, meal_type="lunch")

    return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


@api_view(["POST"])
def consume_dinner(request):
    first_name = request.data.get("first_name")
    last_name = request.data.get("last_name")
    gender = request.data.get("gender")

    if not first_name or not last_name or not gender:
        return Response(
            {"error": "first_name, last_name and gender are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Normalize gender
    normalized_gender = normalize_gender(gender)
    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)

    # Quick verification
    exists, existing_user = verify_user_exists(
        normalized_first, normalized_last, normalized_gender
    )
    if not exists:
        return Response(
            {"error": "User was not found in registry"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Get or create user
    if existing_user:
        user = existing_user
    else:
        user, created = User.objects.get_or_create(
            first_name=normalized_first,
            last_name=normalized_last,
            gender=normalized_gender,
        )

    user.reset_weekly_allowance()

    if user.dinners_remaining <= 0:
        return Response(
            {"error": "No dinners remaining"}, status=status.HTTP_400_BAD_REQUEST
        )

    user.dinners_remaining -= 1
    user.save()
    MealLog.objects.create(user=user, meal_type="dinner")

    return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


@api_view(["POST"])
def consume_drink(request):
    first_name = request.data.get("first_name")
    last_name = request.data.get("last_name")
    gender = request.data.get("gender")
    serving_point = request.data.get("serving_point")
    drink_name = request.data.get("drink_name")
    quantity = request.data.get("quantity", "1")

    if not first_name or not last_name or not gender:
        return Response(
            {"error": "first_name, last_name and gender are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not serving_point:
        return Response(
            {"error": "serving_point is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    if not drink_name:
        return Response(
            {"error": "drink_name is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        quantity = int(quantity)
        if quantity < 1:
            raise ValueError
    except ValueError:
        return Response(
            {"error": "quantity must be a positive integer"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Normalize gender
    normalized_gender = normalize_gender(gender)
    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)
    print(
        f"Received drink request for: {normalized_first} {normalized_last} gender={normalized_gender} drink={drink_name} quantity={quantity}"
    )

    # Quick verification
    exists, existing_user = verify_user_exists(
        normalized_first, normalized_last, normalized_gender
    )
    if not exists:
        return Response(
            {"error": "User was not found in registry"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check if drink type exists
    try:
        drink_type = DrinkType.objects.get(name__iexact=drink_name)
    except DrinkType.DoesNotExist:
        return Response(
            {"error": f'Drink type "{drink_name}" not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check drink availability
    if drink_type.available_quantity < quantity:
        return Response(
            {
                "error": f"Insufficient stock. Only {drink_type.available_quantity} {drink_name} available"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get or create user
    if existing_user:
        user = existing_user
    else:
        user, created = User.objects.get_or_create(
            first_name=normalized_first,
            last_name=normalized_last,
            gender=normalized_gender,
        )

    user.reset_weekly_allowance()

    if user.drinks_remaining < quantity:
        return Response(
            {
                "error": f"Insufficient allowance. Only {user.drinks_remaining} drinks remaining"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create pending drink transaction (waiting for approval)
    transaction = DrinkTransaction.objects.create(
        user=user, drink_type=drink_type, quantity=quantity, serving_point=serving_point
    )

    return Response(
        {
            "message": "Drink order submitted for approval",
            "status": "pending",
            "user": UserSerializer(user).data,
            "transaction": DrinkTransactionSerializer(transaction).data,
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["GET"])
def get_user_status(request):
    first_name = request.query_params.get("first_name")
    last_name = request.query_params.get("last_name")
    gender = request.query_params.get("gender")

    if not first_name or not last_name or not gender:
        return Response(
            {"error": "first_name, last_name and gender are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = User.objects.get(
            first_name=normalize_name(first_name),
            last_name=normalize_name(last_name),
            gender=normalize_gender(gender),
        )
        user.reset_weekly_allowance()
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
def list_drinks(request):
    """List all available drink types with their quantities"""
    drinks = DrinkType.objects.all()
    return Response(
        DrinkTypeSerializer(drinks, many=True).data, status=status.HTTP_200_OK
    )


@api_view(["POST"])
def add_drink_stock(request):
    """Add or update drink stock"""
    drink_name = request.data.get("drink_name")
    quantity = request.data.get("quantity")

    if not drink_name or quantity is None:
        return Response(
            {"error": "drink_name and quantity are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        quantity = int(quantity)
        if quantity < 0:
            raise ValueError
    except ValueError:
        return Response(
            {"error": "quantity must be a non-negative integer"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    drink_type, created = DrinkType.objects.get_or_create(name=drink_name)
    drink_type.available_quantity = quantity
    drink_type.save()

    return Response(
        {
            "message": f"{'Created' if created else 'Updated'} {drink_name}",
            "drink": DrinkTypeSerializer(drink_type).data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def drink_transactions(request):
    """Get all drink transactions with optional filters"""
    transactions = DrinkTransaction.objects.all().order_by("-served_at")

    # Filter by serving point
    serving_point = request.query_params.get("serving_point")
    if serving_point:
        transactions = transactions.filter(serving_point__iexact=serving_point)

    # Filter by user
    first_name = request.query_params.get("first_name")
    last_name = request.query_params.get("last_name")
    if first_name and last_name:
        transactions = transactions.filter(
            user__first_name__iexact=first_name, user__last_name__iexact=last_name
        )

    return Response(
        DrinkTransactionSerializer(transactions, many=True).data,
        status=status.HTTP_200_OK,
    )
