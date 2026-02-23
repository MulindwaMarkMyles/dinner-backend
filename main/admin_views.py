from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import Group, User as AuthUser
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from main.serializers import UserSerializer

from .models import DrinkTransaction, DrinkType, MealLog, User


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
    today = timezone.now().date()
    context = {
        "total_users": User.objects.count(),
        "total_drinks": DrinkType.objects.count(),
        "pending_orders_count": DrinkTransaction.objects.count(),
        "total_meals_today": MealLog.objects.filter(consumed_at__date=today).count(),
        "recent_orders": DrinkTransaction.objects.select_related(
            "user", "drink_type"
        ).order_by("-served_at")[:5],
        "low_stock_drinks": DrinkType.objects.filter(
            available_quantity__lt=50
        ).order_by("available_quantity"),
        "current_time": timezone.now(),
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
        raw_ticket_id = (request.POST.get("ticket_id") or "").strip()
        if raw_ticket_id:
            user.ticket_id = raw_ticket_id
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

            # Generate smart context based on query
            users_name = request.user.username
            context = _build_smart_context(users_name, user_message, messages)
            
            # Log context size for monitoring
            context_size = len(context)
            estimated_tokens = len(context.split()) * 1.3  # Rough estimate
            print(f"[Chatbot] Context size: {context_size} chars, ~{int(estimated_tokens)} tokens")

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
        messages = list(conversation.messages.values("role", "content", "created_at"))
        return JsonResponse(
            {
                "conversation_id": conversation.id,
                "title": conversation.title,
                "messages": messages,
            }
        )

    return JsonResponse({"error": "Invalid request"}, status=400)


def _classify_query_intent(message: str, conversation_history: list = None) -> dict:
    """Classify what data the query needs and try to detect user names via DB lookup.
    
    If the current message looks like a follow-up (pronouns, no name found),
    scan recent conversation messages for names mentioned earlier.
    """
    from main.models import User

    message_lower = message.lower()

    intent = {
        "needs_stats": False,
        "needs_users": False,
        "needs_specific_user": False,
        "needs_drinks": False,
        "needs_transactions": False,
        "needs_meal_logs": False,
        "specific_user_name": None,
        "matched_user_ids": [],
    }

    # Stats keywords
    stats_keywords = ["how many", "total", "count", "statistics", "overview", "summary", "report"]
    if any(kw in message_lower for kw in stats_keywords):
        intent["needs_stats"] = True

    # User-related keywords
    user_keywords = ["user", "people", "delegate", "registered", "attendee", "member"]
    if any(kw in message_lower for kw in user_keywords):
        intent["needs_users"] = True

    # Drink-related keywords
    drink_keywords = ["drink", "beverage", "stock", "inventory", "bottle"]
    if any(kw in message_lower for kw in drink_keywords):
        intent["needs_drinks"] = True

    # Transaction keywords
    transaction_keywords = ["order", "transaction", "pending", "approval", "approved", "denied"]
    if any(kw in message_lower for kw in transaction_keywords):
        intent["needs_transactions"] = True

    # Meal log keywords
    meal_keywords = ["meal", "lunch", "dinner", "bbq", "consumed", "eaten", "supper"]
    if any(kw in message_lower for kw in meal_keywords):
        intent["needs_meal_logs"] = True

    # --- DB-backed ticket detection ---
    # Look for ticket-like patterns (e.g. RMB101-L0245) in the message.
    import re
    ticket_pattern = re.compile(r"[A-Z0-9]+-[A-Z0-9]+", re.IGNORECASE)
    ticket_matches = ticket_pattern.findall(message)

    for ticket_candidate in ticket_matches:
        users_found = _search_users_flexible(ticket_candidate)
        if users_found:
            intent["needs_specific_user"] = True
            intent["specific_user_name"] = ticket_candidate
            intent["matched_user_ids"] = [u.id for u in users_found]
            break

    # --- Follow-up detection ---
    # If no ticket found in current message, check if this looks like a
    # follow-up referencing a ticket mentioned earlier in the conversation.
    if not intent["matched_user_ids"] and conversation_history:
        followup_cues = [
            "them", "they", "this ticket", "that ticket", "this user", "that user",
            "details", "more info", "more about", "elaborate",
            "tell me more", "give me details", "what about",
        ]
        is_followup = any(cue in message_lower for cue in followup_cues)

        if is_followup:
            recent_user_msgs = [
                msg["content"]
                for msg in reversed(conversation_history)
                if msg.get("role") == "user" and msg["content"].strip() != message.strip()
            ][:5]

            for prev_msg in recent_user_msgs:
                prev_intent = _classify_query_intent(prev_msg)  # No history — avoid recursion
                if prev_intent["matched_user_ids"]:
                    intent["needs_specific_user"] = True
                    intent["specific_user_name"] = prev_intent["specific_user_name"]
                    intent["matched_user_ids"] = prev_intent["matched_user_ids"]
                    break

    # Also flag specific user if message contains person-related trigger words
    person_triggers = ["ticket", "find", "about", "search", "check on", "look up", "allowance"]
    if any(kw in message_lower for kw in person_triggers):
        intent["needs_specific_user"] = True

    return intent


def _search_users_flexible(ticket_query: str):
    """Search users by ticket_id fragment. Returns QuerySet or empty."""
    from main.models import User

    ticket_query = ticket_query.strip()
    if not ticket_query:
        return User.objects.none()

    # Exact match first
    users = User.objects.filter(ticket_id__iexact=ticket_query)
    if users.exists():
        return users[:10]

    # Partial/contains match
    users = User.objects.filter(ticket_id__icontains=ticket_query)
    if users.exists():
        return users[:10]

    return User.objects.none()


def _build_smart_context(users_name: str, user_message: str, conversation_history: list = None):
    """Build full database context so the LLM can answer any question."""
    from django.utils import timezone

    from main.models import DrinkTransaction, DrinkType, MealLog, User

    intent = _classify_query_intent(user_message, conversation_history)
    today = timezone.now().date()
    now = timezone.now()

    context_parts = [
        f"SYSTEM DATA (Generated: {now.strftime('%Y-%m-%d %H:%M:%S')})",
        f"Current Day: {now.strftime('%A, %d %B %Y')}",
        f"Admin User: {users_name}",
        "",
        "RULES:",
        "- Users are identified by ticket ID only (e.g. RMB101-L0245)",
        "- Each ticket gets 1 lunch and 1 drink allowance by default",
        "- New tickets are auto-created on first scan",
        "- Dinners default to 0 allowance",
        "",
    ]

    # ── OVERVIEW ──────────────────────────────────────────────────────────
    total_users = User.objects.count()
    total_meals_today = MealLog.objects.filter(consumed_at__date=today).count()
    no_lunches = User.objects.filter(lunches_remaining=0).count()
    no_drinks = User.objects.filter(drinks_remaining=0).count()
    pending_count = DrinkTransaction.objects.filter(status="pending").count()
    approved_today = DrinkTransaction.objects.filter(status="approved", approved_at__date=today).count()

    meals_today_qs = MealLog.objects.filter(consumed_at__date=today)
    lunch_today = meals_today_qs.filter(meal_type="lunch").count()
    dinner_today = meals_today_qs.filter(meal_type="dinner").count()
    drink_today = meals_today_qs.filter(meal_type="drink").count()
    bbq_today = meals_today_qs.filter(meal_type="bbq").count()

    context_parts += [
        "=== OVERVIEW ===",
        f"Total registered tickets: {total_users}",
        f"Tickets with no lunches left: {no_lunches}",
        f"Tickets with no drinks left: {no_drinks}",
        f"Total meals consumed today: {total_meals_today}  "
        f"(Lunch={lunch_today}, Dinner={dinner_today}, Drink={drink_today}, BBQ={bbq_today})",
        f"Pending drink orders: {pending_count}",
        f"Drink orders approved today: {approved_today}",
        "",
    ]

    # ── HIGHLIGHTED MATCH (if ticket detected in query) ───────────────────
    if intent["matched_user_ids"]:
        search_ticket = intent.get("specific_user_name", "")
        matched_users = User.objects.filter(id__in=intent["matched_user_ids"])
        context_parts.append(f"=== TICKET MATCH: '{search_ticket}' ({matched_users.count()} result(s)) ===")
        for u in matched_users:
            meal_count = MealLog.objects.filter(user=u).count()
            last_meal = MealLog.objects.filter(user=u).order_by("-consumed_at").first()
            context_parts.append(
                f"  Ticket:          {u.ticket_id}\n"
                f"  Lunches left:    {u.lunches_remaining}/{u.WEEKLY_LUNCHES}\n"
                f"  Dinners left:    {u.dinners_remaining}/{u.WEEKLY_DINNERS}\n"
                f"  Drinks left:     {u.drinks_remaining}/{u.WEEKLY_DRINKS}\n"
                f"  Total meals:     {meal_count}\n"
                f"  Last meal:       {last_meal.meal_type + ' at ' + last_meal.consumed_at.strftime('%Y-%m-%d %H:%M') if last_meal else 'None'}\n"
                f"  First scanned:   {u.created_at.strftime('%Y-%m-%d %H:%M')}"
            )
        context_parts.append("")

    # ── ALL USERS ─────────────────────────────────────────────────────────
    context_parts.append("=== ALL REGISTERED TICKETS ===")
    all_users = User.objects.order_by("ticket_id")
    for u in all_users:
        context_parts.append(
            f"  {u.ticket_id} | L={u.lunches_remaining}/{u.WEEKLY_LUNCHES}"
            f" D={u.dinners_remaining}/{u.WEEKLY_DINNERS}"
            f" Dk={u.drinks_remaining}/{u.WEEKLY_DRINKS}"
            f" | since {u.created_at.strftime('%Y-%m-%d')}"
        )
    context_parts.append("")

    # ── DRINK INVENTORY ───────────────────────────────────────────────────
    context_parts.append("=== DRINK INVENTORY ===")
    for drink in DrinkType.objects.order_by("name"):
        flag = " ⚠️ LOW" if drink.available_quantity < 30 else ""
        context_parts.append(f"  {drink.name}: {drink.available_quantity} units{flag}")
    context_parts.append("")

    # ── PENDING ORDERS (all) ──────────────────────────────────────────────
    if pending_count > 0:
        context_parts.append("=== PENDING DRINK ORDERS (ALL) ===")
        for order in DrinkTransaction.objects.filter(status="pending").select_related("user", "drink_type").order_by("-served_at"):
            context_parts.append(
                f"  #{order.id} | {order.user.ticket_id} → {order.quantity}x {order.drink_type.name}"
                f" @ {order.serving_point} | {order.served_at.strftime('%Y-%m-%d %H:%M')}"
            )
        context_parts.append("")

    # ── TRANSACTION HISTORY (last 100) ────────────────────────────────────
    context_parts.append("=== TRANSACTION HISTORY (last 100) ===")
    for order in DrinkTransaction.objects.select_related("user", "drink_type").order_by("-served_at")[:100]:
        context_parts.append(
            f"  {order.served_at.strftime('%Y-%m-%d %H:%M')} | {order.user.ticket_id}"
            f" | {order.quantity}x {order.drink_type.name} [{order.status}] @ {order.serving_point}"
        )
    context_parts.append("")

    # ── MEAL LOG (last 200) ───────────────────────────────────────────────
    context_parts.append("=== MEAL LOG (last 200) ===")
    for log in MealLog.objects.select_related("user").order_by("-consumed_at")[:200]:
        context_parts.append(
            f"  {log.consumed_at.strftime('%Y-%m-%d %H:%M')} | {log.user.ticket_id}"
            f" | {log.meal_type}"
            f"{' @ ' + log.serving_point if log.serving_point else ''}"
        )
    context_parts.append("")

    return "\n".join(context_parts)
