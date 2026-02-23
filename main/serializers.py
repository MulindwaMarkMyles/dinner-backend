from rest_framework import serializers
from .models import User, MealLog, DrinkType, DrinkTransaction


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'ticket_id',
            'lunches_remaining', 'dinners_remaining', 'drinks_remaining',
            'week_start', 'created_at', 'updated_at',
        ]


class MealLogSerializer(serializers.ModelSerializer):
    scanned_by_username = serializers.CharField(source='scanned_by.username', read_only=True)

    class Meta:
        model = MealLog
        fields = ['id', 'user', 'meal_type', 'consumed_at', 'scanned_by_username']


class DrinkTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DrinkType
        fields = ['id', 'name', 'available_quantity']


class DrinkTransactionSerializer(serializers.ModelSerializer):
    ticket_id = serializers.CharField(source='user.ticket_id', read_only=True)
    drink_name = serializers.CharField(source='drink_type.name', read_only=True)
    scanned_by_username = serializers.CharField(source='scanned_by.username', read_only=True)

    class Meta:
        model = DrinkTransaction
        fields = ['id', 'ticket_id', 'drink_name', 'quantity', 'serving_point', 'status', 'served_at', 'approved_at', 'scanned_by_username']

