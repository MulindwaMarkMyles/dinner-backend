from django.contrib import admin
from .models import User, MealLog, DrinkType, DrinkTransaction

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'gender', 'lunches_remaining', 'dinners_remaining', 'drinks_remaining', 'week_start']
    search_fields = ['first_name', 'last_name']

@admin.register(MealLog)
class MealLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'meal_type', 'serving_point', 'consumed_at']
    list_filter = ['meal_type', 'serving_point']
    search_fields = ['user__first_name', 'user__last_name']

@admin.register(DrinkType)
class DrinkTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'available_quantity', 'updated_at']
    search_fields = ['name']

@admin.register(DrinkTransaction)
class DrinkTransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'drink_type', 'quantity', 'serving_point', 'served_at']
    list_filter = ['serving_point', 'drink_type']
    search_fields = ['user__first_name', 'user__last_name', 'serving_point']
