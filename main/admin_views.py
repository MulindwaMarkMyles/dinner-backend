from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from main.serializers import UserSerializer

from .models import DrinkTransaction, DrinkType, MealLog, User


def is_admin(user):
    return user.is_staff or user.is_superuser


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
            user=user, meal_type="drink", serving_point=order.serving_point
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
    logs = MealLog.objects.select_related("user").order_by("-consumed_at")[:100]
    return render(request, "admin_meal_logs.html", {"meal_logs": logs})


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

    # --- DB-backed name detection ---
    # Instead of regex, extract candidate words and search the DB directly.
    # Strip common filler words to isolate potential name tokens.
    filler_words = {
        "did", "does", "has", "have", "is", "was", "were", "are",
        "the", "a", "an", "for", "to", "of", "and", "or", "in", "on",
        "how", "about", "what", "who", "where", "when", "why",
        "many", "much", "find", "search", "show", "tell", "me",
        "pay", "paid", "register", "registered", "check",
        "can", "could", "would", "should", "will", "do",
        "their", "his", "her", "my", "your", "our",
        "please", "thanks", "thank", "you", "i", "we", "they",
        "not", "no", "yes", "any", "all", "some",
        "this", "that", "these", "those", "it",
        "with", "from", "at", "by", "up", "out",
        "if", "but", "so", "then", "also", "just",
        "get", "got", "know", "see", "look",
        "meals", "meal", "lunch", "dinner", "bbq", "drinks", "drink",
        "remaining", "left", "allowance", "status",
    }

    # Clean message: remove punctuation, split into words
    import re
    clean_msg = re.sub(r"[^\w\s]", "", message)
    words = clean_msg.split()
    name_tokens = [w for w in words if w.lower() not in filler_words and len(w) > 1]

    if name_tokens:
        # Try progressively: full token string, then pairs, then singles
        # Strategy 1: All tokens as a single name search
        full_candidate = " ".join(name_tokens)
        users_found = _search_users_flexible(full_candidate)

        if not users_found and len(name_tokens) >= 2:
            # Strategy 2: Try first + last token
            candidate = f"{name_tokens[0]} {name_tokens[-1]}"
            users_found = _search_users_flexible(candidate)

        if not users_found and len(name_tokens) >= 1:
            # Strategy 3: Try each token as a single-name search
            for token in name_tokens:
                if len(token) >= 3:  # Skip very short tokens like initials
                    users_found = _search_users_flexible(token)
                    if users_found:
                        break

        if users_found:
            intent["needs_specific_user"] = True
            intent["specific_user_name"] = full_candidate
            intent["matched_user_ids"] = [u.id for u in users_found]

    # --- Follow-up detection ---
    # If no names found in current message, check if this looks like a
    # follow-up referencing someone from earlier in the conversation.
    if not intent["matched_user_ids"] and conversation_history:
        followup_cues = [
            "them", "they", "her", "him", "she", "he",
            "this person", "that person", "those", "these people",
            "details", "more info", "more about", "elaborate",
            "tell me more", "give me details", "what about",
        ]
        is_followup = any(cue in message_lower for cue in followup_cues)

        if is_followup:
            # Walk backwards through recent user messages to find names
            recent_user_msgs = [
                msg["content"]
                for msg in reversed(conversation_history)
                if msg.get("role") == "user" and msg["content"].strip() != message.strip()
            ][:5]  # Last 5 previous user messages

            for prev_msg in recent_user_msgs:
                prev_intent = _classify_query_intent(prev_msg)  # No history — avoid recursion
                if prev_intent["matched_user_ids"]:
                    intent["needs_specific_user"] = True
                    intent["specific_user_name"] = prev_intent["specific_user_name"]
                    intent["matched_user_ids"] = prev_intent["matched_user_ids"]
                    break

    # Also flag specific user if message contains person-related trigger words
    person_triggers = ["pay", "paid", "who is", "find", "about", "search",
                       "how about", "check on", "look up", "allowance"]
    if any(kw in message_lower for kw in person_triggers):
        intent["needs_specific_user"] = True

    return intent


def _search_users_flexible(name_query: str):
    """Search users flexibly by name fragments. Returns QuerySet or empty."""
    from django.db.models import Q
    from main.models import User

    name_query = name_query.strip()
    if not name_query:
        return User.objects.none()

    parts = name_query.split()

    if len(parts) >= 3:
        # Multi-part name (e.g. "Irene T Tinka") — try first + last
        first = parts[0]
        last = parts[-1]
        users = User.objects.filter(
            Q(first_name__icontains=first) & Q(last_name__icontains=last)
        )
        if users.exists():
            return users[:10]

    if len(parts) >= 2:
        first = parts[0]
        last = parts[-1]
        # Try exact first+last
        users = User.objects.filter(
            first_name__iexact=first, last_name__iexact=last
        )
        if users.exists():
            return users[:10]
        # Try contains
        users = User.objects.filter(
            Q(first_name__icontains=first) & Q(last_name__icontains=last)
        )
        if users.exists():
            return users[:10]

    if len(parts) == 1:
        token = parts[0]
        users = User.objects.filter(
            Q(first_name__icontains=token) | Q(last_name__icontains=token)
        )
        if users.exists():
            return users[:10]

    return User.objects.none()


def _build_smart_context(users_name: str, user_message: str, conversation_history: list = None):
    """Build lean, query-aware context based on what the user is asking"""
    from django.db.models import Count, Sum, Q
    from django.utils import timezone

    from main.models import DrinkTransaction, DrinkType, MealLog, User

    intent = _classify_query_intent(user_message, conversation_history)
    today = timezone.now().date()
    
    context_parts = [
        f"SYSTEM DATA (Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')})",
        f"Current Day: {timezone.now().strftime('%A')}",
        f"Admin User: {users_name}\n"
    ]
    
    # Always include basic stats (lightweight)
    context_parts.append("=== OVERVIEW ===")
    total_users = User.objects.count()
    context_parts.append(f"Total users: {total_users}")
    context_parts.append(f"Meals consumed today: {MealLog.objects.filter(consumed_at__date=today).count()}")
    
    # Event registrations (lightweight)
    if intent["needs_stats"] or intent["needs_meal_logs"]:
        friday_count = User.objects.filter(has_friday_lunch=True).count()
        saturday_count = User.objects.filter(has_saturday_lunch=True).count()
        bbq_count = User.objects.filter(has_bbq=True).count()
        all_meals = User.objects.filter(has_friday_lunch=False, has_saturday_lunch=False).count()
        context_parts.append(f"Friday lunch registrations: {friday_count}")
        context_parts.append(f"Saturday lunch registrations: {saturday_count}")
        context_parts.append(f"BBQ registrations: {bbq_count}")
        context_parts.append(f"All-meals access users: {all_meals}")
        
        # Membership breakdown
        rotary = User.objects.filter(membership='ROTARY').count()
        rotaract = User.objects.filter(membership='ROTARACT').count()
        context_parts.append(f"ROTARY: {rotary}, ROTARACT: {rotaract}")
    
    context_parts.append("")
    
    # Drink inventory (only if needed)
    if intent["needs_drinks"]:
        context_parts.append("=== DRINK INVENTORY ===")
        drinks = DrinkType.objects.all()
        for drink in drinks:
            context_parts.append(f"{drink.name}: {drink.available_quantity} units")
        
        # Low stock alerts
        low_stock = DrinkType.objects.filter(available_quantity__lt=30)
        if low_stock.exists():
            context_parts.append("\n⚠️ LOW STOCK:")
            for drink in low_stock:
                context_parts.append(f"  {drink.name}: {drink.available_quantity} units")
        context_parts.append("")
    
    # Transactions (only if needed, limit to recent)
    if intent["needs_transactions"]:
        context_parts.append("=== DRINK TRANSACTIONS ===")
        pending_count = DrinkTransaction.objects.filter(status="pending").count()
        approved_today = DrinkTransaction.objects.filter(status="approved", approved_at__date=today).count()
        context_parts.append(f"Pending orders: {pending_count}")
        context_parts.append(f"Approved today: {approved_today}")
        
        if pending_count > 0:
            context_parts.append("\nPending Orders (Last 15):")
            pending = DrinkTransaction.objects.filter(status="pending").select_related("user", "drink_type").order_by("-served_at")[:15]
            for order in pending:
                context_parts.append(
                    f"  - {order.user.full_name}: {order.quantity}x {order.drink_type.name} at {order.serving_point}"
                )
        
        context_parts.append("\nRecent Transactions (Last 20):")
        recent = DrinkTransaction.objects.select_related("user", "drink_type").order_by("-served_at")[:20]
        for order in recent:
            context_parts.append(
                f"  - {order.user.full_name}: {order.quantity}x {order.drink_type.name} [{order.status}]"
            )
        context_parts.append("")
    
    # Users (only if specifically needed, with limits)
    if intent["needs_users"] or intent["needs_specific_user"]:
        # If we already matched users from the classifier, use those directly
        if intent["matched_user_ids"]:
            search_name = intent.get("specific_user_name", "")
            matched_users = User.objects.filter(id__in=intent["matched_user_ids"])
            context_parts.append(f"=== USER FOUND: '{search_name}' ({matched_users.count()} match(es)) ===")

            for user in matched_users:
                # Determine payment/registration status
                paid_for = []
                if user.has_friday_lunch:
                    paid_for.append("Friday Lunch")
                if user.has_saturday_lunch:
                    paid_for.append("Saturday Lunch")
                if user.has_bbq:
                    paid_for.append("Meat & Greet BBQ")

                if paid_for:
                    payment_status = f"PAID FOR: {', '.join(paid_for)}"
                elif user.lunches_remaining > 0 or user.dinners_remaining > 0:
                    payment_status = "ALL MEALS ACCESS (paid for full package)"
                else:
                    payment_status = "DID NOT PAY for any meals (merchandise/registration only)"

                context_parts.append(
                    f"\nName: {user.full_name}\n"
                    f"Gender: {user.gender}\n"
                    f"Payment Status: {payment_status}\n"
                    f"Lunches Remaining: {user.lunches_remaining}\n"
                    f"Dinners Remaining: {user.dinners_remaining}\n"
                    f"Drinks Remaining: {user.drinks_remaining}\n"
                    f"Club: {user.rotary_club or 'N/A'}\n"
                    f"Membership: {user.membership or 'N/A'}\n"
                    f"Friday Lunch: {'Yes' if user.has_friday_lunch else 'No'}\n"
                    f"Saturday Lunch: {'Yes' if user.has_saturday_lunch else 'No'}\n"
                    f"BBQ: {'Yes' if user.has_bbq else 'No'}"
                )

        elif intent["needs_specific_user"] and not intent["matched_user_ids"]:
            # Tried to find someone but no match
            context_parts.append(
                f"=== USER SEARCH: No matching user found in the database ===\n"
                f"The name queried does not match any registered delegate."
            )
        elif intent["needs_users"]:
            # If looking for specific user but no name extracted, show more detail
            context_parts.append("=== USER SEARCH (Showing 50 users) ===")
            users_list = list(User.objects.all()[:50])
            for user in users_list:
                flags = []
                if user.has_friday_lunch:
                    flags.append("Fri")
                if user.has_saturday_lunch:
                    flags.append("Sat")
                if user.has_bbq:
                    flags.append("BBQ")
                flag_str = f" [{','.join(flags)}]" if flags else " [All-Meals]"
                context_parts.append(
                    f"  - {user.full_name} ({user.gender}): "
                    f"L={user.lunches_remaining}, D={user.dinners_remaining}, "
                    f"Dk={user.drinks_remaining}, Club={user.rotary_club or 'N/A'}{flag_str}"
                )
            if total_users > len(users_list):
                context_parts.append(f"... and {total_users - len(users_list)} more users in database")
        context_parts.append("")
    
    # Meal logs (only recent, only if needed)
    if intent["needs_meal_logs"]:
        context_parts.append("=== RECENT MEAL CONSUMPTION (Last 20) ===")
        logs = MealLog.objects.select_related("user").order_by("-consumed_at")[:20]
        for log in logs:
            context_parts.append(
                f"  - {log.consumed_at.strftime('%Y-%m-%d %H:%M')} | "
                f"{log.user.full_name}: {log.meal_type}"
                f"{' at ' + log.serving_point if log.serving_point else ''}"
            )
        
        # Today's breakdown
        meals_today = MealLog.objects.filter(consumed_at__date=today)
        lunch_today = meals_today.filter(meal_type='lunch').count()
        dinner_today = meals_today.filter(meal_type='dinner').count()
        drink_today = meals_today.filter(meal_type='drink').count()
        context_parts.append(f"\nToday's consumption: {lunch_today} lunches, {dinner_today} dinners, {drink_today} drinks")
        context_parts.append("")
    
    # Add capabilities
    context_parts.append("=== WHAT YOU CAN DO ===")
    context_parts.append("Answer questions about:")
    context_parts.append("- User registrations and meal allowances")
    context_parts.append("- Drink inventory and stock levels")
    context_parts.append("- Transaction history and pending orders")
    context_parts.append("- Meal consumption patterns")
    context_parts.append("- Event statistics (Friday/Saturday lunch, BBQ)")
    context_parts.append("")
    context_parts.append("IMPORTANT:")
    context_parts.append("- 'How many users registered/scanned?' = Total user count")
    context_parts.append("- Users with Friday/Saturday flags can ONLY eat lunch on those days")
    context_parts.append("- Users with NO lunch flags can eat lunch ANY day (paid for all meals)")
    context_parts.append("- Everyone can access dinner and drinks regardless of lunch restrictions")
    
    return "\n".join(context_parts)
