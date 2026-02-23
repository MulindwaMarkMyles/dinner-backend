from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken

from .models import DrinkTransaction, DrinkType, MealLog, User
from .serializers import DrinkTransactionSerializer, DrinkTypeSerializer, UserSerializer


def is_api_scanner(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name="API_SCANNER_ADMIN").exists()


def get_or_create_user_by_ticket(ticket_id):
    """Get or create a user by their ticket ID."""
    if not ticket_id:
        return None
    ticket_id = str(ticket_id).strip()
    user, created = User.objects.get_or_create(ticket_id=ticket_id)
    return user


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
    ticket_id = request.data.get("ticket_id")

    if not ticket_id:
        return Response(
            {"error": "ticket_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not is_api_scanner(request.user):
        return Response(
            {"error": "Account is not allowed to consume meals"},
            status=status.HTTP_403_FORBIDDEN,
        )

    user = get_or_create_user_by_ticket(ticket_id)
    user.reset_weekly_allowance()

    if user.lunches_remaining <= 0:
        return Response(
            {"error": "No lunches remaining"}, status=status.HTTP_400_BAD_REQUEST
        )

    user.lunches_remaining -= 1
    user.save()
    MealLog.objects.create(user=user, meal_type="lunch", scanned_by=request.user)

    return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def consume_dinner(request):
    ticket_id = request.data.get("ticket_id")

    if not ticket_id:
        return Response(
            {"error": "ticket_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not is_api_scanner(request.user):
        return Response(
            {"error": "Account is not allowed to consume meals"},
            status=status.HTTP_403_FORBIDDEN,
        )

    user = get_or_create_user_by_ticket(ticket_id)
    user.reset_weekly_allowance()

    if user.dinners_remaining <= 0:
        return Response(
            {"error": "No dinners remaining"}, status=status.HTTP_400_BAD_REQUEST
        )

    user.dinners_remaining -= 1
    user.save()
    MealLog.objects.create(user=user, meal_type="dinner", scanned_by=request.user)

    return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def consume_bbq(request):
    ticket_id = request.data.get("ticket_id")

    if not ticket_id:
        return Response(
            {"error": "ticket_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not is_api_scanner(request.user):
        return Response(
            {"error": "Account is not allowed to consume meals"},
            status=status.HTTP_403_FORBIDDEN,
        )

    user = get_or_create_user_by_ticket(ticket_id)
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
    ticket_id = request.data.get("ticket_id")
    serving_point = request.data.get("serving_point")
    items = request.data.get("items")

    if not ticket_id:
        return Response(
            {"error": "ticket_id is required"},
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
        drink_name = request.data.get("drink_name")
        quantity = request.data.get("quantity", 1)
        items = [{"drink_name": drink_name, "quantity": quantity}]

    if not isinstance(items, list) or not items:
        return Response(
            {"error": "items must be a non-empty list"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    normalized_items = []
    total_requested = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return Response(
                {"error": f"items[{index}] must be an object"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        drink_name = item.get("drink_name")
        quantity = item.get("quantity", 1)
        if not drink_name:
            return Response(
                {"error": f"items[{index}].drink_name is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            quantity = int(quantity)
            if quantity < 1:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": f"items[{index}].quantity must be a positive integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_requested += quantity
        normalized_items.append({"drink_name": drink_name, "quantity": quantity})

    user = get_or_create_user_by_ticket(ticket_id)
    user.reset_weekly_allowance()

    if user.drinks_remaining < total_requested:
        return Response(
            {
                "error": f"Insufficient allowance. Only {user.drinks_remaining} drinks remaining"
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

    messages = list(
        conversation.messages.values("role", "content", "created_at")
    )
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
        .values("id", "title", "created_at", "updated_at")[:20]
    )
    return Response(
        {"conversations": list(conversations)},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def get_user_status(request):
    ticket_id = request.query_params.get("ticket_id")

    if not ticket_id:
        return Response(
            {"error": "ticket_id is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = User.objects.get(ticket_id=ticket_id.strip())
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
    ticket_id = request.query_params.get("ticket_id")
    if ticket_id:
        transactions = transactions.filter(user__ticket_id=ticket_id.strip())

    return Response(
        DrinkTransactionSerializer(transactions, many=True).data,
        status=status.HTTP_200_OK,
    )
