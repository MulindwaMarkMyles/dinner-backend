from rest_framework import serializers
from .models import User, MealLog, DrinkType, DrinkTransaction

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'full_name', 'gender', 'lunches_remaining', 'dinners_remaining', 'drinks_remaining']

class MealLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MealLog
        fields = ['id', 'user', 'meal_type', 'consumed_at']

class DrinkTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DrinkType
        fields = ['id', 'name', 'available_quantity']


class DrinkTransactionSerializer(serializers.ModelSerializer):
    drink_name = serializers.CharField(source='drink_type.name', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = DrinkTransaction
        fields = ['id', 'user_name', 'drink_name', 'quantity', 'serving_point', 'served_at']
