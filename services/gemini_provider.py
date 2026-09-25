"""Google Gemini as a `GradingModel` for the AI grading pipeline.

Selected with LLM_MODEL="gemini:<model id>" plus LLM_API_KEY (a Google AI
Studio key). The free tier is enough for a class: it is rate-limited, so a
burst of answers can hit HTTP 429, which is retried briefly and otherwise
left to `grade_with_ai` - a failed call falls back to the rule-based grader
rather than breaking a student's submission.

The SDK is imported lazily so the app, the tests and demo mode all run
without `google-genai` installed; only choosing this provider needs it.

What leaves the app: the grading prompt only - question, model answer,
marking criteria and the student's answer text. Never a name, email or id.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from utils.config import Settings

DEFAULT_MODEL = "gemini-2.5-flash"

# Free-tier limits are per minute, so a short back-off usually clears a 429.
# Kept small: a student is waiting, and a daily quota will not clear at all.
_RETRY_ATTEMPTS = 3
_RETRY_MAX_DELAY_S = 8.0
_TIMEOUT_MS = 60_000


@lru_cache(maxsize=4)
def _client(api_key: str) -> Any:
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=_TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(
                attempts=_RETRY_ATTEMPTS,
                initial_delay=1.0,
                max_delay=_RETRY_MAX_DELAY_S,
                http_status_codes=[429, 500, 503],
            ),
        ),
    )


class GeminiGradingModel:
    """Answers the grading prompt with one Gemini `generate_content` call."""

    def __init__(self, api_key: str, model_id: str = DEFAULT_MODEL, client: Optional[Any] = None):
        if not api_key:
            raise ValueError("A Gemini API key is required.")
        self.model_id = model_id or DEFAULT_MODEL
        self.name = f"gemini:{self.model_id}"
        self._client = client if client is not None else _client(api_key)

    @classmethod
    def from_settings(cls, settings: Settings) -> "GeminiGradingModel":
        _, _, model_id = settings.llm_model.partition(":")
        return cls(settings.llm_api_key, model_id.strip() or DEFAULT_MODEL)

    def complete(self, system: str, user: str) -> str:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self.model_id,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        # None when the response was blocked or empty; the validator turns
        # that into an AIOutputError and the caller falls back.
        return response.text or ""


__all__ = ["DEFAULT_MODEL", "GeminiGradingModel"]
