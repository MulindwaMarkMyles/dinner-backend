from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import Group, User as AuthUser
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from main.serializers import UserSerializer

from .models import DrinkTransaction, DrinkType, MealLog, User


EAST_AFRICA_TIMEZONE = ZoneInfo("Africa/Nairobi")


def to_eat(dt):
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, EAST_AFRICA_TIMEZONE)
    return timezone.localtime(dt, EAST_AFRICA_TIMEZONE)


def get_eat_now():
    return to_eat(timezone.now())


def get_eat_day_bounds(reference_dt=None):
    eat_reference = to_eat(reference_dt or timezone.now())
    day_start = eat_reference.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    return day_start, day_end


def format_eat_datetime(dt, fmt="%Y-%m-%d %H:%M:%S EAT"):
    return to_eat(dt).strftime(fmt)


def serialize_chat_messages(messages):
    return [
        {
            "role": message.role,
            "content": message.content,
            "created_at": format_eat_datetime(message.created_at),
        }
        for message in messages
    ]


def serialize_chat_conversations(conversations):
    return [
        {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": format_eat_datetime(conversation.created_at),
            "updated_at": format_eat_datetime(conversation.updated_at),
        }
        for conversation in conversations
    ]


def is_admin(user):
    return user.is_staff or user.is_superuser


def ensure_api_scanner_group():
    group, _ = Group.objects.get_or_create(name="API_SCANNER_ADMIN")
    return group


def custom_admin_login(request):
    next_url = request.GET.get("next") or request.POST.get("next")

    if request.user.is_authenticated and is_admin(request.user):
        return redirect(next_url or "admin_dashboard")

    error = None
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user and is_admin(user):
            login(request, user)
            return redirect(next_url or "admin_dashboard")
        error = "Invalid credentials or insufficient permissions."

    return render(request, "admin_login.html", {"error": error, "next": next_url})


@login_required
def custom_admin_logout(request):
    logout(request)
    return redirect("custom_admin_login")


@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    today_start, tomorrow_start = get_eat_day_bounds()
    context = {
        "total_users": User.objects.count(),
        "total_drinks": DrinkType.objects.count(),
        "pending_orders_count": DrinkTransaction.objects.filter(status="pending").count(),
        "total_meals_today": MealLog.objects.filter(
            consumed_at__gte=today_start,
            consumed_at__lt=tomorrow_start,
        ).count(),
        "recent_orders": DrinkTransaction.objects.select_related(
            "user", "drink_type"
        ).order_by("-served_at")[:5],
        "low_stock_drinks": DrinkType.objects.filter(
            available_quantity__lt=50
        ).order_by("available_quantity"),
        "current_time": get_eat_now(),
    }
    return render(request, "admin_dashboard.html", context)


@login_required
@user_passes_test(is_admin)
def admin_inventory(request):
    drinks = DrinkType.objects.all().order_by("-updated_at")
    return render(request, "admin_inventory.html", {"drinks": drinks})


@login_required
@user_passes_test(is_admin)
def add_drink(request):
    if request.method == "POST":
        name = request.POST.get("name")
        quantity = request.POST.get("quantity")
        DrinkType.objects.create(name=name, available_quantity=int(quantity))
        return redirect("admin_inventory")
    return redirect("admin_inventory")


@login_required
@user_passes_test(is_admin)
def edit_drink(request, drink_id):
    drink = get_object_or_404(DrinkType, id=drink_id)
    if request.method == "POST":
        drink.name = request.POST.get("name", drink.name)
        drink.available_quantity = int(
            request.POST.get("quantity", drink.available_quantity)
        )
        drink.save()
        return redirect("admin_inventory")
    return render(request, "admin_inventory.html", {"edit_drink": drink})


@login_required
@user_passes_test(is_admin)
def delete_drink(request, drink_id):
    drink = get_object_or_404(DrinkType, id=drink_id)
    drink.delete()
    return redirect("admin_inventory")


@login_required
@user_passes_test(is_admin)
def admin_approvals(request):
    pending_orders = (
        DrinkTransaction.objects.filter(status="pending")
        .select_related("user", "drink_type")
        .order_by("-served_at")
    )
    return render(request, "admin_approvals.html", {"pending_orders": pending_orders})


@login_required
@user_passes_test(is_admin)
def approve_order(request, order_id):
    if request.method == "POST":
        order = get_object_or_404(DrinkTransaction, id=order_id, status="pending")
        user = order.user
        drink_type = order.drink_type

        # Check if user still has drinks remaining
        if user.drinks_remaining < order.quantity:
            return JsonResponse(
                {"error": f"User only has {user.drinks_remaining} drinks remaining"},
                status=400,
            )

        # Check if drink is still available
        if drink_type.available_quantity < order.quantity:
            return JsonResponse(
                {
                    "error": f"Only {drink_type.available_quantity} {drink_type.name} available"
                },
                status=400,
            )

        # Deduct from user allowance
        user.drinks_remaining -= order.quantity
        user.save()

        # Deduct from drink inventory
        drink_type.available_quantity -= order.quantity
        drink_type.save()

        # Update transaction status
        order.status = "approved"
        order.approved_at = timezone.now()
        order.save()

        # Create meal log
        MealLog.objects.create(
            user=user,
            meal_type="drink",
            serving_point=order.serving_point,
            scanned_by=order.scanned_by,
        )

    return redirect("admin_approvals")


@login_required
@user_passes_test(is_admin)
def deny_order(request, order_id):
    if request.method == "POST":
        order = get_object_or_404(DrinkTransaction, id=order_id, status="pending")
        order.status = "denied"
        order.approved_at = timezone.now()
        order.save()
    return redirect("admin_approvals")


@login_required
@user_passes_test(is_admin)
def admin_users(request):
    users = User.objects.all().order_by("-created_at")
    return render(request, "admin_users.html", {"users": users})


@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        user.lunches_remaining = int(
            request.POST.get("lunches", user.lunches_remaining)
        )
        user.dinners_remaining = int(
            request.POST.get("dinners", user.dinners_remaining)
        )
        user.drinks_remaining = int(request.POST.get("drinks", user.drinks_remaining))
        user.save()
        return redirect("admin_users")
    return render(request, "admin_users.html", {"edit_user": user})


@login_required
@user_passes_test(is_admin)
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.delete()
    return redirect("admin_users")


@login_required
@user_passes_test(is_admin)
def meal_logs(request):
    logs = MealLog.objects.select_related("user", "scanned_by").order_by("-consumed_at")[:100]
    return render(request, "admin_meal_logs.html", {"meal_logs": logs})


@login_required
@user_passes_test(is_admin)
def admin_api_admins(request):
    scanner_group = ensure_api_scanner_group()

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = (request.POST.get("password") or "").strip()
        first_name = (request.POST.get("first_name") or "").strip()
        last_name = (request.POST.get("last_name") or "").strip()

        if not username or not password:
            messages.error(request, "Username and password are required.")
            return redirect("admin_api_admins")

        if AuthUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("admin_api_admins")

        api_admin = AuthUser.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
        )
        api_admin.groups.add(scanner_group)
        messages.success(request, f"API admin '{username}' created successfully.")
        return redirect("admin_api_admins")

    api_admins = (
        AuthUser.objects.filter(groups=scanner_group)
        .order_by("-date_joined")
    )
    return render(
        request,
        "admin_api_admins.html",
        {"api_admins": api_admins},
    )


@login_required
@user_passes_test(is_admin)
def chatbot_view(request):
    """Main chatbot interface"""
    from main.models import Conversation

    conversations = Conversation.objects.filter(user=request.user).order_by(
        "-updated_at"
    )[:10]
    return render(request, "admin_chatbot.html", {"conversations": conversations})


@login_required
@user_passes_test(is_admin)
def chatbot_conversation(request, conversation_id=None):
    """Handle chatbot conversation - create new or load existing"""
    import json

    from main.models import ChatMessage, Conversation
    from main.services.ai_service import AIService

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_message = data.get("message", "").strip()

            if not user_message:
                return JsonResponse(
                    {"error": "Message cannot be empty"},
                    status=400,
                )

            # Get or create conversation
            if conversation_id:
                conversation = get_object_or_404(
                    Conversation, id=conversation_id, user=request.user
                )
            else:
                conversation = Conversation.objects.create(user=request.user)

            # Save user message
            ChatMessage.objects.create(
                conversation=conversation, role="user", content=user_message
            )

            # Build conversation history
            messages = []
            for msg in conversation.messages.all():
                if msg.role != "system":
                    messages.append({"role": msg.role, "content": msg.content})

            context = (
                f"Channel: admin chatbot. Admin user: {request.user.username}. "
                f"Current server time: {timezone.localtime().strftime('%Y-%m-%d %H:%M:%S %Z')}."
            )

            # Get AI response
            ai_service = AIService()
            assistant_response = ai_service.generate_response(
                messages=messages, context=context
            )

            # Save assistant response
            ChatMessage.objects.create(
                conversation=conversation, role="assistant", content=assistant_response
            )

            # Generate title if first message
            if conversation.messages.count() == 2:  # user + assistant
                title = ai_service.generate_title(user_message)
                conversation.title = title
                conversation.save()

            return JsonResponse(
                {
                    "conversation_id": conversation.id,
                    "title": conversation.title,
                    "message": assistant_response,
                },
                status=200,
            )

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    # GET request - load conversation
    if conversation_id:
        conversation = get_object_or_404(
            Conversation, id=conversation_id, user=request.user
        )
        messages = serialize_chat_messages(
            conversation.messages.order_by("created_at")
        )
        return JsonResponse(
            {
                "conversation_id": conversation.id,
                "title": conversation.title,
                "messages": messages,
            }
        )

    return JsonResponse({"error": "Invalid request"}, status=400)


