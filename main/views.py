from django.contrib.auth import authenticate
from django.db import models as db_models
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken

from .models import DrinkTransaction, DrinkType, MealLog, User
from .serializers import (
    DrinkTransactionSerializer,
    DrinkTypeSerializer,
    MealLogSerializer,
    UserSerializer,
)


def is_api_scanner(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name="API_SCANNER_ADMIN").exists()


def normalize_name(name):
    """Normalize names by trimming and collapsing whitespace (preserve titles)."""
    if not name:
        return ""
    return " ".join(name.strip().split())


def verify_user_exists(first_name, last_name):
    """Fast check if user exists in DB only."""
    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)
    print(
        f"[verify] raw=({first_name}, {last_name}) normalized=({normalized_first}, {normalized_last})"
    )

    try:
        print("[verify] checking DB")
        user = (
            User.objects.filter(
                first_name__iexact=normalized_first,
                last_name__iexact=normalized_last,
            )
            .order_by("-updated_at", "-id")
            .first()
        )

        if user:
            print("[verify] DB name match found")
            return True, user

        print("[verify] DB miss")
    except Exception as e:
        print(f"[verify] DB error: {e}")

    return False, None


@api_view(["POST"])
def api_login(request):
    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return Response(
            {"error": "username and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=username, password=password)
    if not user:
        return Response(
            {"error": "Invalid credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not is_api_scanner(user):
        return Response(
            {"error": "Account is not allowed to access scanner API"},
            status=status.HTTP_403_FORBIDDEN,
        )

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "username": user.username,
                "is_staff": user.is_staff,
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def consume_lunch(request):
    first_name = request.data.get("first_name")
    last_name = request.data.get("last_name")

    if not first_name or not last_name:
        return Response(
            {"error": "first_name, last_name are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not is_api_scanner(request.user):
        return Response(
            {"error": "Account is not allowed to consume meals"},
            status=status.HTTP_403_FORBIDDEN,
        )

    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)

    exists, existing_user = verify_user_exists(
        normalized_first, normalized_last
    )
    if not exists:
        return Response(
            {"error": "User was not found in registry"},
            status=status.HTTP_404_NOT_FOUND,
        )

    user = existing_user
    user.reset_weekly_allowance()

    if user.lunches_remaining <= 0:
        return Response(
            {"error": "No lunches remaining"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Check if user has already consumed lunch today
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if MealLog.objects.filter(
        user=user, meal_type="lunch", consumed_at__gte=today_start
    ).exists():
        return Response(
            {"error": "User has already consumed lunch today"},
            status=status.HTTP_409_CONFLICT,
        )

    user.lunches_remaining -= 1
    user.save()
    MealLog.objects.create(user=user, meal_type="lunch", scanned_by=request.user)

    return Response(
        {
            "message": "Lunch consumed successfully",
            "user": UserSerializer(user).data,
            "lunches_remaining": user.lunches_remaining,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def consume_dinner(request):
    first_name = request.data.get("first_name")
    last_name = request.data.get("last_name")

    if not first_name or not last_name:
        return Response(
            {"error": "first_name, last_name are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not is_api_scanner(request.user):
        return Response(
            {"error": "Account is not allowed to consume meals"},
            status=status.HTTP_403_FORBIDDEN,
        )

    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)

    exists, existing_user = verify_user_exists(
        normalized_first, normalized_last
    )
    if not exists:
        return Response(
            {"error": "User was not found in registry"},
            status=status.HTTP_404_NOT_FOUND,
        )

    user = existing_user
    user.reset_weekly_allowance()

    if user.dinners_remaining <= 0:
        return Response(
            {"error": "No dinners remaining"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Check if user has already consumed dinner today
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if MealLog.objects.filter(
        user=user, meal_type="dinner", consumed_at__gte=today_start
    ).exists():
        return Response(
            {"error": "User has already consumed dinner today"},
            status=status.HTTP_409_CONFLICT,
        )

    user.dinners_remaining -= 1
    user.save()
    MealLog.objects.create(user=user, meal_type="dinner", scanned_by=request.user)

    return Response(
        {
            "message": "Dinner consumed successfully",
            "user": UserSerializer(user).data,
            "dinners_remaining": user.dinners_remaining,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def consume_bbq(request):
    first_name = request.data.get("first_name")
    last_name = request.data.get("last_name")

    if not first_name or not last_name:
        return Response(
            {"error": "first_name, last_name are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not is_api_scanner(request.user):
        return Response(
            {"error": "Account is not allowed to consume meals"},
            status=status.HTTP_403_FORBIDDEN,
        )

    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)

    exists, existing_user = verify_user_exists(
        normalized_first, normalized_last
    )
    if not exists:
        return Response(
            {"error": "User was not found in registry"},
            status=status.HTTP_404_NOT_FOUND,
        )

    user = existing_user
    user.reset_weekly_allowance()

    if MealLog.objects.filter(user=user, meal_type="bbq").exists():
        return Response(
            {"error": "User has already consumed BBQ ticket"},
            status=status.HTTP_409_CONFLICT,
        )

    MealLog.objects.create(user=user, meal_type="bbq", scanned_by=request.user)
    return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def consume_drink(request):
    first_name = request.data.get("first_name")
    last_name = request.data.get("last_name")
    serving_point = request.data.get("serving_point")
    items = request.data.get("items")

    if not first_name or not last_name:
        return Response(
            {"error": "first_name, last_name are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not is_api_scanner(request.user):
        return Response(
            {"error": "Account is not allowed to consume meals"},
            status=status.HTTP_403_FORBIDDEN,
        )

    if not serving_point:
        return Response(
            {"error": "serving_point is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    if items is None:
        return Response(
            {"error": "items is required (e.g. {'Sparkling Water': 2, 'Iced Tea': 1})"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not isinstance(items, dict) or not items:
        return Response(
            {"error": "items must be a non-empty object mapping drink names to quantities"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    normalized_items = []
    total_requested = 0
    for drink_name, quantity in items.items():
        if not drink_name:
            return Response(
                {"error": "Drink name key must not be empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": f"Quantity for '{drink_name}' must be a positive integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_requested += quantity
        normalized_items.append({"drink_name": drink_name, "quantity": quantity})

    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)

    exists, existing_user = verify_user_exists(
        normalized_first, normalized_last
    )
    if not exists:
        return Response(
            {"error": "User was not found in registry"},
            status=status.HTTP_404_NOT_FOUND,
        )

    user = existing_user
    user.reset_weekly_allowance()

    DAILY_DRINK_LIMIT = 5

    # Count drinks already consumed today (pending + approved)
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    drinks_today = DrinkTransaction.objects.filter(
        user=user,
        served_at__gte=today_start,
        status__in=["pending", "approved"],
    ).aggregate(total=db_models.Sum("quantity"))["total"] or 0

    drinks_available_today = DAILY_DRINK_LIMIT - drinks_today

    if drinks_available_today <= 0:
        return Response(
            {"error": "Daily drink limit of 5 reached"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if total_requested > drinks_available_today:
        return Response(
            {
                "error": f"Request exceeds daily limit. You can have at most {drinks_available_today} more drink(s) today"
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


    transactions = []
    for item in normalized_items:
        try:
            drink_type = DrinkType.objects.get(name__iexact=item["drink_name"])
        except DrinkType.DoesNotExist:
            return Response(
                {"error": f'Drink type "{item["drink_name"]}" not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if drink_type.available_quantity < item["quantity"]:
            return Response(
                {
                    "error": f"Insufficient stock. Only {drink_type.available_quantity} {drink_type.name} available"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        transactions.append(
            DrinkTransaction.objects.create(
                user=user,
                drink_type=drink_type,
                quantity=item["quantity"],
                serving_point=serving_point,
                scanned_by=request.user,
            )
        )

    return Response(
        {
            "message": "Drink order submitted for approval",
            "status": "pending",
            "user": UserSerializer(user).data,
            "transactions": DrinkTransactionSerializer(transactions, many=True).data,
            "total_requested": total_requested,
            "drinks_remaining_today": drinks_available_today - total_requested,
        },
        status=status.HTTP_202_ACCEPTED,
    )


# ────────────────────────────────────────────────────────────
# Public Chatbot API
# ────────────────────────────────────────────────────────────

@api_view(["POST"])
def chatbot_send(request):
    """Send a message and get an AI response.

    Body (JSON):
        message            – (required) the user's message text
        conversation_id    – (optional) existing conversation ID to continue
        session_id         – (optional) client-generated UUID to group conversations

    Returns 200 with:
        conversation_id, title, message (assistant reply)
    """
    from main.admin_views import _build_smart_context
    from main.models import ChatMessage, Conversation
    from main.services.ai_service import AIService

    user_message = request.data.get("message", "").strip()
    conversation_id = request.data.get("conversation_id")
    session_id = request.data.get("session_id")

    if not user_message:
        return Response(
            {"error": "message is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # Get or create conversation
        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id)
                # If session_id provided, verify it matches
                if session_id and conversation.session_id and conversation.session_id != session_id:
                    return Response(
                        {"error": "session_id does not match this conversation"},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except Conversation.DoesNotExist:
                return Response(
                    {"error": "Conversation not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            conversation = Conversation.objects.create(session_id=session_id)

        # Save user message
        ChatMessage.objects.create(
            conversation=conversation, role="user", content=user_message
        )

        # Build conversation history for follow-up support
        messages = []
        for msg in conversation.messages.all():
            if msg.role != "system":
                messages.append({"role": msg.role, "content": msg.content})

        # Build smart context (same pipeline as admin chatbot)
        context = _build_smart_context("Guest", user_message, messages)

        # Get AI response
        ai_service = AIService()
        assistant_response = ai_service.generate_response(
            messages=messages, context=context
        )

        # Save assistant response
        ChatMessage.objects.create(
            conversation=conversation, role="assistant", content=assistant_response
        )

        # Auto-generate title on first exchange
        if conversation.messages.count() == 2:
            title = ai_service.generate_title(user_message)
            conversation.title = title
            conversation.save()

        return Response(
            {
                "conversation_id": conversation.id,
                "title": conversation.title,
                "message": assistant_response,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
def chatbot_history(request, conversation_id):
    """Retrieve full message history for a conversation.

    Query params:
        session_id – (optional) must match if the conversation was created with one

    Returns 200 with:
        conversation_id, title, messages [{role, content, created_at}, ...]
    """
    from main.admin_views import serialize_chat_messages
    from main.models import Conversation

    session_id = request.query_params.get("session_id")

    try:
        conversation = Conversation.objects.get(id=conversation_id)
    except Conversation.DoesNotExist:
        return Response(
            {"error": "Conversation not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # If session_id guard is present, enforce it
    if session_id and conversation.session_id and conversation.session_id != session_id:
        return Response(
            {"error": "session_id does not match this conversation"},
            status=status.HTTP_403_FORBIDDEN,
        )

    messages = serialize_chat_messages(conversation.messages.order_by("created_at"))
    return Response(
        {
            "conversation_id": conversation.id,
            "title": conversation.title,
            "messages": messages,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def chatbot_conversations(request):
    """List recent conversations for a session.

    Query params:
        session_id – (required) the client session UUID

    Returns 200 with:
        conversations [{id, title, created_at, updated_at}, ...]
    """
    from main.admin_views import serialize_chat_conversations
    from main.models import Conversation

    session_id = request.query_params.get("session_id")
    if not session_id:
        return Response(
            {"error": "session_id query param is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conversations = (
        Conversation.objects.filter(session_id=session_id)
        .order_by("-updated_at")
        [:20]
    )
    return Response(
        {"conversations": serialize_chat_conversations(conversations)},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def get_user_status(request):
    first_name = request.query_params.get("first_name")
    last_name = request.query_params.get("last_name")

    if not first_name or not last_name:
        return Response(
            {"error": "first_name, last_name are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)

    user = (
        User.objects.filter(
            first_name__iexact=normalized_first,
            last_name__iexact=normalized_last,
        )
        .order_by("-updated_at", "-id")
        .first()
    )
    if not user:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    user.reset_weekly_allowance()
    return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


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


@api_view(["GET"])
# @authentication_classes([JWTAuthentication])
@permission_classes([AllowAny])
def llm_query_data(request):
    """
    Endpoint for LLM to query user meal statuses and logs.
    Supports optional filtering by first_name and last_name.
    """
    first_name = request.query_params.get("first_name")
    last_name = request.query_params.get("last_name")

    users = User.objects.all()
    logs = MealLog.objects.all().order_by("-consumed_at")

    if first_name:
        users = users.filter(first_name__iexact=first_name)
        logs = logs.filter(user__first_name__iexact=first_name)
    if last_name:
        users = users.filter(last_name__iexact=last_name)
        logs = logs.filter(user__last_name__iexact=last_name)

    # Limit logs to latest 50 if no specific user filter to avoid huge responses
    if not first_name and not last_name:
        logs = logs[:50]

    return Response(
        {
            "users": UserSerializer(users, many=True).data,
            "meal_logs": MealLogSerializer(logs, many=True).data,
        },
        status=status.HTTP_200_OK,
    )
