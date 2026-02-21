from datetime import timedelta

from django.contrib.auth.models import User as AuthUser
from django.db import models
from django.utils import timezone


# Create your models here.
class User(models.Model):
    WEEKLY_LUNCHES = 3
    WEEKLY_DINNERS = 3
    WEEKLY_DRINKS = 15

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(
        max_length=10,
        choices=[("M", "Male"), ("F", "Female"), ("UNKNOWN", "Unknown")],
        default="UNKNOWN",
    )
    lunches_remaining = models.IntegerField(default=WEEKLY_LUNCHES)
    dinners_remaining = models.IntegerField(default=WEEKLY_DINNERS)
    drinks_remaining = models.IntegerField(default=WEEKLY_DRINKS)
    rotary_club = models.CharField(max_length=100, null=True, blank=True)
    delegate_reg_id = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    external_uuid = models.CharField(max_length=36, null=True, blank=True, db_index=True)
    membership = models.CharField(max_length=20, null=True, blank=True)
    district = models.CharField(max_length=50, null=True, blank=True)
    dietary_requirements = models.CharField(max_length=200, null=True, blank=True)
    has_friday_lunch = models.BooleanField(default=False)
    has_saturday_lunch = models.BooleanField(default=False)
    has_bbq = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    week_start = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ["first_name", "last_name", "gender"]

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
        ("lunch", "Lunch"),
        ("dinner", "Dinner"),
        ("drink", "Drink"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="meal_logs")
    meal_type = models.CharField(max_length=10, choices=MEAL_TYPES)
    consumed_at = models.DateTimeField(auto_now_add=True)
    serving_point = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ["-consumed_at"]

    def __str__(self):
        return f"{self.user.full_name} - {self.meal_type} - {self.consumed_at}"


class Conversation(models.Model):
    """Track chatbot conversation sessions"""

    title = models.CharField(max_length=200, default="New Conversation")
    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(
        max_length=100, null=True, blank=True, db_index=True,
        help_text="Client-generated ID for public (unauthenticated) conversations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class ChatMessage(models.Model):
    """Individual messages within a conversation"""

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class DrinkType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    available_quantity = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.available_quantity} available)"


class DrinkTransaction(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("denied", "Denied"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="drink_transactions"
    )
    drink_type = models.ForeignKey(
        DrinkType, on_delete=models.CASCADE, related_name="transactions"
    )
    quantity = models.IntegerField(default=1)
    serving_point = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    served_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.full_name} - {self.drink_type.name} x{self.quantity} at {self.serving_point} [{self.status}]"
