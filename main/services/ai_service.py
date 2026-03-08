import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone
from openai import OpenAI
from openai.types.chat import ChatCompletion

logger = logging.getLogger(__name__)

ChatMessage = Dict[str, str]
ToolResult = Dict[str, Any]


class AIService:
    """
    Lightweight abstraction for interacting with LLM providers so views and
    Django templates can request chatbot responses without duplicating client setup.
    """

    def __init__(
        self, provider: Optional[str] = None, model: Optional[str] = None
    ) -> None:
        self.provider = (
            (provider or getattr(settings, "AI_PROVIDER", "groq")).lower().strip()
        )
        self.model: Optional[str] = model
        self.client: Optional[OpenAI] = None
        self._initialize_client()

        logger.info(
            "AIService ready (provider=%s, model=%s)", self.provider, self.model
        )
        self.max_tool_rounds = 6

    # --------------------------------------------------------------------- #
    # Client setup
    # --------------------------------------------------------------------- #
    def _initialize_client(self) -> None:
        """
        Configure the OpenAI client against the selected provider.  Each provider
        uses the same API surface but different base URLs and credentials.
        """
        if self.provider == "openai":
            api_key = getattr(settings, "OPENAI_API_KEY", None)
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not configured in settings.")
            self.client = OpenAI(api_key=api_key)
            self.model = self.model or getattr(
                settings, "OPENAI_MODEL_NAME", "gpt-4o-mini"
            )
            return

        if self.provider == "github":
            api_key = getattr(settings, "GITHUB_TOKEN", None)
            endpoint = getattr(settings, "GITHUB_MODELS_ENDPOINT", None)
            if not api_key or not endpoint:
                raise ValueError(
                    "GITHUB_TOKEN and GITHUB_MODELS_ENDPOINT must be configured for GitHub provider."
                )
            self.client = OpenAI(base_url=endpoint, api_key=api_key)
            self.model = self.model or getattr(
                settings, "GITHUB_MODEL_NAME", "gpt-4o-mini"
            )
            return

        # Default to Groq
        api_key = getattr(settings, "GROQ_API_KEY", None)
        endpoint = getattr(settings, "GROQ_ENDPOINT", None)
        if not api_key or not endpoint:
            raise ValueError(
                "GROQ_API_KEY and GROQ_ENDPOINT must be configured for Groq provider."
            )
        self.client = OpenAI(base_url=endpoint, api_key=api_key)
        self.model = self.model or getattr(
            settings, "GROQ_MODEL_NAME", "openai/gpt-oss-20b"
        )

    # --------------------------------------------------------------------- #
    # Prompt helpers
    # --------------------------------------------------------------------- #
    def _get_system_prompt(self) -> str:
        """
        Attempt to fetch an active prompt from an optional dashboard app.
        Fall back to a default assistant instruction if the app is unavailable.
        """
        try:
            from dashboard.models import SystemPrompt  # type: ignore

            prompt = SystemPrompt.get_active_prompt()
        except Exception:  # noqa: BLE001
            logger.debug(
                "Dashboard SystemPrompt not available; using default system prompt."
            )

        prompt = prompt if "prompt" in locals() and prompt else (
            "You are Amani, the AI assistant for the dinner backend operations team. "
            "You can answer questions about attendees, meal allowances, meal logs, drinks, "
            "inventory, and drink transactions."
        )

        tool_rules = (
            "\n\nTOOL USAGE RULES:\n"
            "- For factual questions about people, meals, drinks, registrations, logs, counts, or approvals, use the available tools to inspect live data before answering.\n"
            "- You may call multiple tools when needed and then synthesize the result.\n"
            "- Never claim you lack access to records when tool access is available.\n"
            "- If a tool returns no matching records, say that clearly.\n"
            "- Be concise, accurate, and avoid guessing.\n"
        )
        return prompt + tool_rules

    def _build_context_block(self, context: str) -> str:
        if not context:
            return ""
        return (
            "\n\n--- RUNTIME CONTEXT ---\n"
            f"{context.strip()}\n"
            "--- END RUNTIME CONTEXT ---\n"
        )

    # ------------------------------------------------------------------ #
    # Tool definitions and execution
    # ------------------------------------------------------------------ #
    def _get_mcp_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_people",
                    "description": "Search attendees by name, registration ID, club, membership, or UUID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "first_name": {"type": "string"},
                            "last_name": {"type": "string"},
                            "registration_id": {"type": "string"},
                            "external_uuid": {"type": "string"},
                            "club": {"type": "string"},
                            "membership": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 25},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_user_meal_status",
                    "description": "Get detailed allowance, recent meals, and recent drink activity for one or more attendees.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {"type": "integer"},
                            "query": {"type": "string"},
                            "first_name": {"type": "string"},
                            "last_name": {"type": "string"},
                            "registration_id": {"type": "string"},
                            "include_recent_logs": {"type": "boolean"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_meal_logs",
                    "description": "Search meal consumption logs by attendee, meal type, date window, or recency.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "first_name": {"type": "string"},
                            "last_name": {"type": "string"},
                            "meal_type": {
                                "type": "string",
                                "enum": ["lunch", "dinner", "drink", "bbq"],
                            },
                            "today_only": {"type": "boolean"},
                            "since_days": {"type": "integer", "minimum": 1, "maximum": 90},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_drink_inventory",
                    "description": "Inspect drink stock levels and low-stock items.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "low_stock_only": {"type": "boolean"},
                            "low_stock_threshold": {"type": "integer", "minimum": 0, "maximum": 1000},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_drink_transactions",
                    "description": "Search drink orders and approvals by attendee, status, serving point, or date window.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "first_name": {"type": "string"},
                            "last_name": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "approved", "denied"],
                            },
                            "serving_point": {"type": "string"},
                            "today_only": {"type": "boolean"},
                            "since_days": {"type": "integer", "minimum": 1, "maximum": 90},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_event_overview",
                    "description": "Get aggregate event stats: attendee counts, meals consumed today, pending drink orders, and optionally recent activity.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "include_recent_activity": {"type": "boolean"},
                            "recent_limit": {"type": "integer", "minimum": 1, "maximum": 20},
                        },
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def _serialize_datetime(self, value: Any) -> Optional[str]:
        if not value:
            return None
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S %Z")

    def _user_summary(self, user: Any) -> Dict[str, Any]:
        return {
            "id": user.id,
            "full_name": user.full_name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "registration_id": user.registration_id,
            "external_uuid": user.external_uuid,
            "club": user.club,
            "membership": user.membership,
            "lunches_remaining": user.lunches_remaining,
            "dinners_remaining": user.dinners_remaining,
            "drinks_remaining": user.drinks_remaining,
            "week_start": self._serialize_datetime(user.week_start),
            "updated_at": self._serialize_datetime(user.updated_at),
        }

    def _safe_json_loads(self, raw_arguments: str) -> Dict[str, Any]:
        if not raw_arguments:
            return {}
        try:
            data = json.loads(raw_arguments)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            logger.warning("Invalid tool arguments JSON: %s", raw_arguments)
            return {}

    def _resolve_users(self, args: Dict[str, Any], default_limit: int = 10) -> Any:
        from main.models import User

        limit = max(1, min(int(args.get("limit", default_limit)), 25))
        users = User.objects.all()

        user_id = args.get("user_id")
        if user_id:
            return users.filter(id=user_id)[:limit]

        registration_id = args.get("registration_id")
        if registration_id:
            users = users.filter(registration_id__iexact=registration_id)

        external_uuid = args.get("external_uuid")
        if external_uuid:
            users = users.filter(external_uuid__iexact=external_uuid)

        first_name = (args.get("first_name") or "").strip()
        last_name = (args.get("last_name") or "").strip()
        club = (args.get("club") or "").strip()
        membership = (args.get("membership") or "").strip()
        query = (args.get("query") or "").strip()

        if first_name:
            users = users.filter(first_name__icontains=first_name)
        if last_name:
            users = users.filter(last_name__icontains=last_name)
        if club:
            users = users.filter(club__icontains=club)
        if membership:
            users = users.filter(membership__iexact=membership)

        if query:
            parts = [part for part in query.split() if part.strip()]
            if len(parts) >= 2:
                users = users.filter(
                    Q(first_name__icontains=parts[0], last_name__icontains=parts[-1])
                    | Q(first_name__icontains=parts[-1], last_name__icontains=parts[0])
                    | Q(registration_id__icontains=query)
                    | Q(external_uuid__icontains=query)
                    | Q(club__icontains=query)
                )
            else:
                users = users.filter(
                    Q(first_name__icontains=query)
                    | Q(last_name__icontains=query)
                    | Q(registration_id__icontains=query)
                    | Q(external_uuid__icontains=query)
                    | Q(club__icontains=query)
                    | Q(membership__icontains=query)
                )

        return users.order_by("first_name", "last_name", "id")[:limit]

    def _tool_search_people(self, args: Dict[str, Any]) -> ToolResult:
        users = list(self._resolve_users(args))
        return {
            "count": len(users),
            "results": [self._user_summary(user) for user in users],
        }

    def _tool_get_user_meal_status(self, args: Dict[str, Any]) -> ToolResult:
        from main.models import DrinkTransaction, MealLog

        include_recent_logs = args.get("include_recent_logs", True)
        users = list(self._resolve_users(args, default_limit=5))
        results: List[Dict[str, Any]] = []

        for user in users:
            user.reset_weekly_allowance()
            payload = self._user_summary(user)

            if include_recent_logs:
                meal_logs = MealLog.objects.filter(user=user).order_by("-consumed_at")[:10]
                drink_transactions = (
                    DrinkTransaction.objects.filter(user=user)
                    .select_related("drink_type")
                    .order_by("-served_at")[:10]
                )
                payload["recent_meal_logs"] = [
                    {
                        "meal_type": log.meal_type,
                        "consumed_at": self._serialize_datetime(log.consumed_at),
                        "serving_point": log.serving_point,
                    }
                    for log in meal_logs
                ]
                payload["recent_drink_transactions"] = [
                    {
                        "drink": transaction.drink_type.name,
                        "quantity": transaction.quantity,
                        "status": transaction.status,
                        "serving_point": transaction.serving_point,
                        "served_at": self._serialize_datetime(transaction.served_at),
                        "approved_at": self._serialize_datetime(transaction.approved_at),
                    }
                    for transaction in drink_transactions
                ]

            results.append(payload)

        return {"count": len(results), "results": results}

    def _tool_search_meal_logs(self, args: Dict[str, Any]) -> ToolResult:
        from main.models import MealLog

        limit = max(1, min(int(args.get("limit", 20)), 50))
        logs = MealLog.objects.select_related("user", "scanned_by").all()
        users = list(self._resolve_users(args, default_limit=25))
        if users:
            logs = logs.filter(user__in=users)

        meal_type = args.get("meal_type")
        if meal_type:
            logs = logs.filter(meal_type=meal_type)

        if args.get("today_only"):
            start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
            logs = logs.filter(consumed_at__gte=start)

        since_days = args.get("since_days")
        if since_days:
            logs = logs.filter(consumed_at__gte=timezone.now() - timedelta(days=int(since_days)))

        logs = logs.order_by("-consumed_at")[:limit]
        results = [
            {
                "user_id": log.user_id,
                "full_name": log.user.full_name,
                "meal_type": log.meal_type,
                "consumed_at": self._serialize_datetime(log.consumed_at),
                "serving_point": log.serving_point,
                "scanned_by": log.scanned_by.username if log.scanned_by else None,
            }
            for log in logs
        ]
        return {"count": len(results), "results": results}

    def _tool_get_drink_inventory(self, args: Dict[str, Any]) -> ToolResult:
        from main.models import DrinkType

        limit = max(1, min(int(args.get("limit", 50)), 50))
        threshold = int(args.get("low_stock_threshold", 30))
        drinks = DrinkType.objects.all()
        query = (args.get("query") or "").strip()
        if query:
            drinks = drinks.filter(name__icontains=query)
        if args.get("low_stock_only"):
            drinks = drinks.filter(available_quantity__lt=threshold)

        drinks = drinks.order_by("available_quantity", "name")[:limit]
        results = [
            {
                "id": drink.id,
                "name": drink.name,
                "available_quantity": drink.available_quantity,
                "updated_at": self._serialize_datetime(drink.updated_at),
                "is_low_stock": drink.available_quantity < threshold,
            }
            for drink in drinks
        ]
        return {
            "count": len(results),
            "low_stock_threshold": threshold,
            "total_stock_units": DrinkType.objects.aggregate(total=Sum("available_quantity"))["total"] or 0,
            "results": results,
        }

    def _tool_search_drink_transactions(self, args: Dict[str, Any]) -> ToolResult:
        from main.models import DrinkTransaction

        limit = max(1, min(int(args.get("limit", 20)), 50))
        transactions = DrinkTransaction.objects.select_related(
            "user", "drink_type", "scanned_by"
        ).all()
        users = list(self._resolve_users(args, default_limit=25))
        if users:
            transactions = transactions.filter(user__in=users)

        status_value = args.get("status")
        if status_value:
            transactions = transactions.filter(status=status_value)

        serving_point = (args.get("serving_point") or "").strip()
        if serving_point:
            transactions = transactions.filter(serving_point__icontains=serving_point)

        query = (args.get("query") or "").strip()
        if query:
            transactions = transactions.filter(
                Q(drink_type__name__icontains=query)
                | Q(serving_point__icontains=query)
                | Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
            )

        if args.get("today_only"):
            start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
            transactions = transactions.filter(served_at__gte=start)

        since_days = args.get("since_days")
        if since_days:
            transactions = transactions.filter(served_at__gte=timezone.now() - timedelta(days=int(since_days)))

        transactions = transactions.order_by("-served_at")[:limit]
        results = [
            {
                "id": transaction.id,
                "user_id": transaction.user_id,
                "full_name": transaction.user.full_name,
                "drink": transaction.drink_type.name,
                "quantity": transaction.quantity,
                "status": transaction.status,
                "serving_point": transaction.serving_point,
                "served_at": self._serialize_datetime(transaction.served_at),
                "approved_at": self._serialize_datetime(transaction.approved_at),
                "scanned_by": transaction.scanned_by.username if transaction.scanned_by else None,
            }
            for transaction in transactions
        ]
        return {"count": len(results), "results": results}

    def _tool_get_event_overview(self, args: Dict[str, Any]) -> ToolResult:
        from main.models import DrinkTransaction, DrinkType, MealLog, User

        include_recent_activity = args.get("include_recent_activity", False)
        recent_limit = max(1, min(int(args.get("recent_limit", 10)), 20))
        today_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)

        membership_breakdown = {
            (row["membership"] or "Unknown"): row["count"]
            for row in User.objects.values("membership")
            .order_by("membership")
            .annotate(count=Count("id"))
        }

        result: ToolResult = {
            "generated_at": self._serialize_datetime(timezone.now()),
            "total_users": User.objects.count(),
            "membership_breakdown": membership_breakdown,
            "meals_consumed_today": MealLog.objects.filter(consumed_at__gte=today_start).count(),
            "meal_breakdown_today": {
                "lunch": MealLog.objects.filter(consumed_at__gte=today_start, meal_type="lunch").count(),
                "dinner": MealLog.objects.filter(consumed_at__gte=today_start, meal_type="dinner").count(),
                "drink": MealLog.objects.filter(consumed_at__gte=today_start, meal_type="drink").count(),
                "bbq": MealLog.objects.filter(consumed_at__gte=today_start, meal_type="bbq").count(),
            },
            "drink_orders": {
                "pending": DrinkTransaction.objects.filter(status="pending").count(),
                "approved_today": DrinkTransaction.objects.filter(
                    status="approved", approved_at__gte=today_start
                ).count(),
                "denied_today": DrinkTransaction.objects.filter(
                    status="denied", approved_at__gte=today_start
                ).count(),
            },
            "drink_inventory": {
                "types": DrinkType.objects.count(),
                "total_units": DrinkType.objects.aggregate(total=Sum("available_quantity"))["total"] or 0,
                "low_stock": [
                    {
                        "name": drink.name,
                        "available_quantity": drink.available_quantity,
                    }
                    for drink in DrinkType.objects.filter(available_quantity__lt=30).order_by("available_quantity", "name")[:10]
                ],
            },
        }

        if include_recent_activity:
            result["recent_meal_logs"] = [
                {
                    "full_name": log.user.full_name,
                    "meal_type": log.meal_type,
                    "consumed_at": self._serialize_datetime(log.consumed_at),
                }
                for log in MealLog.objects.select_related("user").order_by("-consumed_at")[:recent_limit]
            ]
            result["recent_drink_transactions"] = [
                {
                    "full_name": transaction.user.full_name,
                    "drink": transaction.drink_type.name,
                    "quantity": transaction.quantity,
                    "status": transaction.status,
                    "served_at": self._serialize_datetime(transaction.served_at),
                }
                for transaction in DrinkTransaction.objects.select_related("user", "drink_type").order_by("-served_at")[:recent_limit]
            ]

        return result

    def _execute_mcp_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        tool_map = {
            "search_people": self._tool_search_people,
            "get_user_meal_status": self._tool_get_user_meal_status,
            "search_meal_logs": self._tool_search_meal_logs,
            "get_drink_inventory": self._tool_get_drink_inventory,
            "search_drink_transactions": self._tool_search_drink_transactions,
            "get_event_overview": self._tool_get_event_overview,
        }

        handler = tool_map.get(name)
        if not handler:
            return {"error": f"Unknown tool: {name}"}

        try:
            return handler(arguments)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Tool execution failed for %s: %s", name, exc)
            return {"error": str(exc), "tool": name}

    def _assistant_message_payload(self, message: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "role": "assistant",
            "content": message.content or "",
        }
        tool_calls = getattr(message, "tool_calls", None) or []
        if tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in tool_calls
            ]
        return payload

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def generate_response(
        self,
        messages: List[ChatMessage],
        *,
        context: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """
        Ask the configured LLM for a response.  Messages should already be in the
        OpenAI-compatible format: [{"role": "user", "content": "Hello"}].
        """
        if not self.client or not self.model:
            raise RuntimeError("AI client is not initialized correctly.")

        system_prompt = self._get_system_prompt() + self._build_context_block(context)
        full_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ] + messages
        tools = self._get_mcp_tools()

        logger.debug(
            "Dispatching %d messages to provider=%s model=%s",
            len(full_messages),
            self.provider,
            self.model,
        )

        for attempt in range(self.max_tool_rounds):
            try:
                response: ChatCompletion = self.client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    tool_choice="auto",
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("AI provider request failed: %s", exc)
                raise

            message = response.choices[0].message if response.choices else None
            if not message:
                break

            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                content = message.content or ""
                logger.debug("AI response length: %d characters", len(content))
                return content or "I’m sorry, I don’t have a response at the moment."

            logger.debug(
                "AI requested %d tool call(s) on round %d",
                len(tool_calls),
                attempt + 1,
            )
            full_messages.append(self._assistant_message_payload(message))

            for tool_call in tool_calls:
                arguments = self._safe_json_loads(tool_call.function.arguments)
                result = self._execute_mcp_tool(tool_call.function.name, arguments)
                full_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        logger.warning("AI tool loop reached max rounds without final answer.")
        fallback_response: ChatCompletion = self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = fallback_response.choices[0].message.content if fallback_response.choices else ""
        return content or "I’m sorry, I don’t have a response at the moment."

    def generate_title(self, first_user_message: str) -> str:
        """
        Generate a short title to label a conversation.  Useful for conversation lists.
        """
        trimmed = first_user_message.strip()
        if not trimmed:
            return "New Conversation"

        prompt = (
            "Generate a concise (max 6 words) conversation title. "
            "Return ONLY the title text without punctuation or quotation marks."
        )

        try:
            response: ChatCompletion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": trimmed},
                ],
                temperature=0.5,
                max_tokens=20,
            )
            title = response.choices[0].message.content.strip()
        except Exception:  # noqa: BLE001
            logger.debug(
                "Title generation failed; falling back to first message snippet."
            )
            title = trimmed.split("\n", 1)[0][:50]

        return title.strip('"').strip("'").strip() or "New Conversation"
