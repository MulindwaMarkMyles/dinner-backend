import logging
from typing import Dict, List, Optional

from django.conf import settings
from openai import OpenAI
from openai.types.chat import ChatCompletion

logger = logging.getLogger(__name__)

ChatMessage = Dict[str, str]


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
            if prompt:
                return prompt
        except Exception:  # noqa: BLE001
            logger.debug(
                "Dashboard SystemPrompt not available; using default system prompt."
            )

        return (
            "You are a Amani. A helpful assistant supporting the 101 Rotary District Conference. "
            "Answer questions accurately, concisely, and with a professional tone."
        )

    def _build_context_block(self, context: str) -> str:
        if not context:
            return ""
        return (
            "\n\nCONVERSATION CONTEXT (use when relevant):\n"
            f"{context.strip()}\n"
            "If the context is unrelated, answer using your general reasoning.\n"
        )

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
        full_messages: List[ChatMessage] = [
            {"role": "system", "content": system_prompt}
        ] + messages

        logger.debug(
            "Dispatching %d messages to provider=%s model=%s",
            len(full_messages),
            self.provider,
            self.model,
        )

        try:
            response: ChatCompletion = self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI provider request failed: %s", exc)
            raise

        content = response.choices[0].message.content if response.choices else ""
        logger.debug("AI response length: %d characters", len(content))
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
