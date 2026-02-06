from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings
from django.core.cache import cache
from .models import User, MealLog, DrinkType, DrinkTransaction
from .serializers import UserSerializer, DrinkTypeSerializer, DrinkTransactionSerializer
import requests
import csv
from io import StringIO

# Fetch data from Google Sheets as CSV with caching
def get_google_sheet_data():
    """Fetch data from Google Sheets as CSV with 5-minute cache"""
    cached_data = cache.get('google_sheet_data')
    if cached_data is not None:
        return cached_data
    
    try:
        response = requests.get(settings.GOOGLE_SHEETS_CSV_URL, timeout=10)
        response.raise_for_status()
        
        csv_data = StringIO(response.text)
        reader = csv.DictReader(csv_data)
        data = list(reader)
        
        # Cache for 5 minutes
        cache.set('google_sheet_data', data, 300)
        return data
    except Exception as e:
        print(f"Error fetching from Google Sheets: {e}")
        return None

def normalize_gender(gender):
    """Normalize gender input to handle F/M and FEMALE/MALE formats"""
    gender = gender.strip().upper()
    
    # Map full names to single letters
    gender_map = {
        'FEMALE': 'F',
        'MALE': 'M',
        'F': 'F',
        'M': 'M'
    }
    
    return gender_map.get(gender, gender)

def find_user_in_sheet(first_name, last_name, gender):
    """Search for user in Google Sheet by firstName, lastName, and gender"""
    data = get_google_sheet_data()
    if not data:
        print("No data from Google Sheets")
        return None
    
    # Normalize search terms
    search_first = first_name.lower().strip()
    search_last = last_name.lower().strip()
    search_gender = normalize_gender(gender)
    
    for row in data:
        sheet_first_name = row.get('firstName', '').strip()
        sheet_last_name = row.get('lastName', '').strip()
        sheet_gender = normalize_gender(row.get('gender', ''))
        
        # Debug print
        if sheet_first_name.lower() == search_first:
            print(f"Found first name match: {sheet_first_name} {sheet_last_name} gender={sheet_gender} (searching for {search_gender})")
        
        if (sheet_first_name.lower() == search_first and 
            sheet_last_name.lower() == search_last and 
            sheet_gender == search_gender):
            print(f"✓ User found: {first_name} {last_name} {search_gender}")
            return row
    
    print(f"✗ User not found: {first_name} {last_name} {search_gender}")
    return None

def verify_user_exists(first_name, last_name, gender):
    """Fast check if user exists - checks DB first, then sheet"""
    # Normalize gender
    normalized_gender = normalize_gender(gender)
    
    # First check if user already exists in DB
    try:
        user = User.objects.get(
            first_name__iexact=first_name,
            last_name__iexact=last_name,
            gender__iexact=normalized_gender
        )
        return True, user
    except User.DoesNotExist:
        # Check Google Sheet
        sheet_user = find_user_in_sheet(first_name, last_name, normalized_gender)
        if sheet_user:
            return True, None
        return False, None

@api_view(['POST'])
def consume_lunch(request):
    first_name = request.data.get('first_name')
    last_name = request.data.get('last_name')
    gender = request.data.get('gender')
    
    if not first_name or not last_name or not gender:
        return Response({'error': 'first_name, last_name and gender are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Normalize gender
    normalized_gender = normalize_gender(gender)
    
    # Quick verification
    exists, existing_user = verify_user_exists(first_name, last_name, normalized_gender)
    if not exists:
        return Response({'error': 'User was not found in registry'}, status=status.HTTP_404_NOT_FOUND)
    
    # Get or create user
    if existing_user:
        user = existing_user
    else:
        user, created = User.objects.get_or_create(
            first_name=first_name,
            last_name=last_name,
            gender=normalized_gender
        )
    
    user.reset_weekly_allowance()
    
    if user.lunches_remaining <= 0:
        return Response({'error': 'No lunches remaining'}, status=status.HTTP_400_BAD_REQUEST)
    
    user.lunches_remaining -= 1
    user.save()
    MealLog.objects.create(user=user, meal_type='lunch')
    
    return Response(UserSerializer(user).data, status=status.HTTP_200_OK)

@api_view(['POST'])
def consume_dinner(request):
    first_name = request.data.get('first_name')
    last_name = request.data.get('last_name')
    gender = request.data.get('gender')
    
    if not first_name or not last_name or not gender:
        return Response({'error': 'first_name, last_name and gender are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Normalize gender
    normalized_gender = normalize_gender(gender)
    
    # Quick verification
    exists, existing_user = verify_user_exists(first_name, last_name, normalized_gender)
    if not exists:
        return Response({'error': 'User was not found in registry'}, status=status.HTTP_404_NOT_FOUND)
    
    # Get or create user
    if existing_user:
        user = existing_user
    else:
        user, created = User.objects.get_or_create(
            first_name=first_name,
            last_name=last_name,
            gender=normalized_gender
        )
    
    user.reset_weekly_allowance()
    
    if user.dinners_remaining <= 0:
        return Response({'error': 'No dinners remaining'}, status=status.HTTP_400_BAD_REQUEST)
    
    user.dinners_remaining -= 1
    user.save()
    MealLog.objects.create(user=user, meal_type='dinner')
    
    return Response(UserSerializer(user).data, status=status.HTTP_200_OK)

@api_view(['POST'])
def consume_drink(request):
    first_name = request.data.get('first_name')
    last_name = request.data.get('last_name')
    gender = request.data.get('gender')
    serving_point = request.data.get('serving_point')
    drink_name = request.data.get('drink_name')
    quantity = request.data.get('quantity', '1')

    if not first_name or not last_name or not gender:
        return Response({'error': 'first_name, last_name and gender are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not serving_point:
        return Response({'error': 'serving_point is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not drink_name:
        return Response({'error': 'drink_name is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        quantity = int(quantity)
        if quantity < 1:
            raise ValueError
    except ValueError:
        return Response({'error': 'quantity must be a positive integer'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Normalize gender
    normalized_gender = normalize_gender(gender)
    
    # Quick verification
    exists, existing_user = verify_user_exists(first_name, last_name, normalized_gender)
    if not exists:
        return Response({'error': 'User was not found in registry'}, status=status.HTTP_404_NOT_FOUND)
    
    # Check if drink type exists
    try:
        drink_type = DrinkType.objects.get(name__iexact=drink_name)
    except DrinkType.DoesNotExist:
        return Response({'error': f'Drink type "{drink_name}" not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Check drink availability
    if drink_type.available_quantity < quantity:
        return Response({
            'error': f'Insufficient stock. Only {drink_type.available_quantity} {drink_name} available'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get or create user
    if existing_user:
        user = existing_user
    else:
        user, created = User.objects.get_or_create(
            first_name=first_name,
            last_name=last_name,
            gender=normalized_gender
        )
    
    user.reset_weekly_allowance()
    
    if user.drinks_remaining < quantity:
        return Response({
            'error': f'Insufficient allowance. Only {user.drinks_remaining} drinks remaining'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Create pending drink transaction (waiting for approval)
    transaction = DrinkTransaction.objects.create(
        user=user,
        drink_type=drink_type,
        quantity=quantity,
        serving_point=serving_point
    )
    
    return Response({
        'message': 'Drink order submitted for approval',
        'status': 'pending',
        'user': UserSerializer(user).data,
        'transaction': DrinkTransactionSerializer(transaction).data,
    }, status=status.HTTP_202_ACCEPTED)

@api_view(['GET'])
def get_user_status(request):
    first_name = request.query_params.get('first_name')
    last_name = request.query_params.get('last_name')
    gender = request.query_params.get('gender')
    
    if not first_name or not last_name or not gender:
        return Response({'error': 'first_name, last_name and gender are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = User.objects.get(
            first_name=first_name,
            last_name=last_name,
            gender=gender
        )
        user.reset_weekly_allowance()
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['GET'])
def list_drinks(request):
    """List all available drink types with their quantities"""
    drinks = DrinkType.objects.all()
    return Response(DrinkTypeSerializer(drinks, many=True).data, status=status.HTTP_200_OK)


@api_view(['POST'])
def add_drink_stock(request):
    """Add or update drink stock"""
    drink_name = request.data.get('drink_name')
    quantity = request.data.get('quantity')
    
    if not drink_name or quantity is None:
        return Response({'error': 'drink_name and quantity are required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        quantity = int(quantity)
        if quantity < 0:
            raise ValueError
    except ValueError:
        return Response({'error': 'quantity must be a non-negative integer'}, status=status.HTTP_400_BAD_REQUEST)
    
    drink_type, created = DrinkType.objects.get_or_create(name=drink_name)
    drink_type.available_quantity = quantity
    drink_type.save()
    
    return Response({
        'message': f'{"Created" if created else "Updated"} {drink_name}',
        'drink': DrinkTypeSerializer(drink_type).data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
def drink_transactions(request):
    """Get all drink transactions with optional filters"""
    transactions = DrinkTransaction.objects.all().order_by('-served_at')
    
    # Filter by serving point
    serving_point = request.query_params.get('serving_point')
    if serving_point:
        transactions = transactions.filter(serving_point__iexact=serving_point)
    
    # Filter by user
    first_name = request.query_params.get('first_name')
    last_name = request.query_params.get('last_name')
    if first_name and last_name:
        transactions = transactions.filter(
            user__first_name__iexact=first_name,
            user__last_name__iexact=last_name
        )
    
    return Response(DrinkTransactionSerializer(transactions, many=True).data, status=status.HTTP_200_OK)
