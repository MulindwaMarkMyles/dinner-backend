from datetime import datetime

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import DrinkTransaction, DrinkType, MealLog, User
from .serializers import DrinkTransactionSerializer, DrinkTypeSerializer, UserSerializer


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


def verify_user_exists(first_name, last_name, gender):
    """Fast check if user exists in DB only."""
    normalized_gender = normalize_gender(gender)
    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)
    print(
        f"[verify] raw=({first_name}, {last_name}, {gender}) normalized=({normalized_first}, {normalized_last}, {normalized_gender})"
    )

    # Check in DB (name-first, then gender match, then name fallback)
    try:
        print("[verify] checking DB")
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

    # User must already exist in DB (imported from CSV)
    user = existing_user

    user.reset_weekly_allowance()

    # Check lunch day restrictions
    current_day = datetime.now().weekday()  # 0=Monday, 4=Friday, 5=Saturday
    has_specific_lunch = user.has_friday_lunch or user.has_saturday_lunch
    
    if has_specific_lunch:
        # User registered for specific day(s) only
        allowed_days = []
        if user.has_friday_lunch:
            allowed_days.append("Friday")
        if user.has_saturday_lunch:
            allowed_days.append("Saturday")
        
        is_friday = current_day == 4
        is_saturday = current_day == 5
        
        if user.has_friday_lunch and not is_friday:
            return Response(
                {"error": "You are only registered for Friday lunch"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        if user.has_saturday_lunch and not user.has_friday_lunch and not is_saturday:
            return Response(
                {"error": "You are only registered for Saturday lunch"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        if user.has_friday_lunch and user.has_saturday_lunch:
            if not (is_friday or is_saturday):
                return Response(
                    {"error": f"You are only registered for {' and '.join(allowed_days)} lunch"},
                    status=status.HTTP_403_FORBIDDEN,
                )
    # else: User has no specific lunch flags, they paid for all meals - allow any day

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

    # User must already exist in DB (imported from CSV)
    user = existing_user

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

    # User must already exist in DB (imported from CSV)
    user = existing_user

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
    first_name = request.query_params.get("first_name")
    last_name = request.query_params.get("last_name")
    gender = request.query_params.get("gender")

    if not first_name or not last_name or not gender:
        return Response(
            {"error": "first_name, last_name and gender are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    normalized_first = normalize_name(first_name)
    normalized_last = normalize_name(last_name)
    normalized_gender = normalize_gender(gender)

    try:
        users = User.objects.filter(
            first_name__iexact=normalized_first,
            last_name__iexact=normalized_last,
        )
        if not users.exists():
            raise User.DoesNotExist

        user = users.filter(gender__iexact=normalized_gender).first() or users.first()
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
