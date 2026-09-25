"""Shared plumbing for the AI features other than grading: hints and practice.

They use the same provider as grading (LLM_API_KEY / LLM_MODEL, Gemini by
default), and follow the same contract:

  * **Optional.** No key, a failed call or output that breaks a rule means the
    caller falls back to its rule-based version. A student never sees an error
    because the AI was unavailable.
  * **Pointers, not answers.** Every prompt asks the model for its own final
    answer in a separate field. That answer is used for one thing - checking
    that nothing shown to the student contains it - and then thrown away.
  * **Cached.** Streamlit reruns the whole page on every click, and the free
    tier is rate-limited, so each distinct request is sent once per process.
    Only successes are cached, so a rate-limited call is retried next time.

No provider SDK is imported here; `ai_grading_service` owns the registry.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from typing import Any, Iterable, List, Optional

from utils.config import Settings

_CACHE_LIMIT = 512
_CACHE: "OrderedDict[str, Any]" = OrderedDict()

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


# --------------------------------------------------------------------------
# Model access
# --------------------------------------------------------------------------
def get_model(settings: Optional[Settings] = None):
    """The configured model, or None when AI is off or cannot be set up."""
    from services.ai_grading_service import get_grading_model

    try:
        return get_grading_model(settings)
    except Exception:  # e.g. the provider SDK is not installed
        return None


def ai_enabled(settings: Optional[Settings] = None) -> bool:
    return get_model(settings) is not None


def ask_json(model, system: str, user: str) -> Optional[dict]:
    """One model call parsed as a JSON object, or None on any failure."""
    from services.ai_grading_service import AIOutputError, _extract_json

    try:
        raw = model.complete(system, user)
    except Exception:  # provider failures must never reach the page
        return None
    try:
        return _extract_json(raw)
    except AIOutputError:
        return None


# --------------------------------------------------------------------------
# Cache (successes only)
# --------------------------------------------------------------------------
def cache_key(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def cache_get(key: str) -> Any:
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    return None


def cache_put(key: str, value: Any) -> None:
    _CACHE[key] = value
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_LIMIT:
        _CACHE.popitem(last=False)


def clear_cache() -> None:
    _CACHE.clear()


# --------------------------------------------------------------------------
# Output checks
# --------------------------------------------------------------------------
def _numbers(text: str) -> set:
    """Numbers in `text`, normalised so "5", "5.0" and "-5" compare equal."""
    return {format(float(n), "g") for n in _NUMBER.findall(text or "")}


def leaked_values(shown: Iterable[str], hidden_answer: str, allowed: Iterable[str]) -> List[str]:
    """Values from the hidden answer that appear in text a student will see.

    Numbers the student already has - from the question, or their own attempt
    - are allowed; anything else from the answer is a leak.
    """
    known = set()
    for text in allowed:
        known |= _numbers(text)
    secret = _numbers(hidden_answer) - known
    seen = set()
    for text in shown:
        seen |= _numbers(text)
    return sorted(secret & seen)


def clean_lines(value: Any, low: int, high: int, max_chars: int = 400) -> Optional[List[str]]:
    """A list of `low`..`high` non-blank strings, or None if it is not one."""
    if not isinstance(value, list):
        return None
    lines = [str(v).strip() for v in value if isinstance(v, str) and v.strip()]
    if not low <= len(lines) <= high or any(len(line) > max_chars for line in lines):
        return None
    return lines


def clean_text(value: Any, max_chars: int = 600) -> Optional[str]:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_chars:
        return None
    return value.strip()


__all__ = [
    "ai_enabled",
    "ask_json",
    "cache_get",
    "cache_key",
    "cache_put",
    "clean_lines",
    "clean_text",
    "clear_cache",
    "get_model",
    "leaked_values",
]
