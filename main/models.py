from django.db import models
from datetime import timedelta
from django.utils import timezone

# Create your models here.
class User(models.Model):
    WEEKLY_LUNCHES = 5
    WEEKLY_DINNERS = 5
    WEEKLY_DRINKS = 10

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, choices=[('M', 'Male'), ('F', 'Female')])
    lunches_remaining = models.IntegerField(default=WEEKLY_LUNCHES)
    dinners_remaining = models.IntegerField(default=WEEKLY_DINNERS)
    drinks_remaining = models.IntegerField(default=WEEKLY_DRINKS)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    week_start = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ['first_name', 'last_name', 'gender']

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @classmethod
    def default_allowances(cls):
        return {
            "lunches": cls.WEEKLY_LUNCHES,
            "dinners": cls.WEEKLY_DINNERS,
            "drinks": cls.WEEKLY_DRINKS,
        }

    def reset_weekly_allowance(self):
        """Reset allowances if a week has passed"""
        if timezone.now() - self.week_start > timedelta(days=7):
            self.lunches_remaining = self.WEEKLY_LUNCHES
            self.dinners_remaining = self.WEEKLY_DINNERS
            self.drinks_remaining = self.WEEKLY_DRINKS
            self.week_start = timezone.now()
            self.save()


class MealLog(models.Model):
    MEAL_TYPES = [
        ('lunch', 'Lunch'),
        ('dinner', 'Dinner'),
        ('drink', 'Drink'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meal_logs')
    meal_type = models.CharField(max_length=10, choices=MEAL_TYPES)
    consumed_at = models.DateTimeField(auto_now_add=True)
    serving_point = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        unique_together = ['user', 'meal_type', 'consumed_at']

    def __str__(self):
        return f"{self.user.full_name} - {self.meal_type} - {self.consumed_at}"


class DrinkType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    available_quantity = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.available_quantity} available)"


class DrinkTransaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='drink_transactions')
    drink_type = models.ForeignKey(DrinkType, on_delete=models.CASCADE, related_name='transactions')
    quantity = models.IntegerField(default=1)
    serving_point = models.CharField(max_length=100)
    served_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.full_name} - {self.drink_type.name} x{self.quantity} at {self.serving_point}"
