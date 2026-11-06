"""The in-app survey behind the sidebar's Feedback button.

Three questions: a 1-5 rating, what the app should include, and any other
feedback. A signed-in answer goes to the `app_feedback` table (migration 009),
which the app can write to but never read back - the team reads it in the
Supabase dashboard. The demo has nowhere to send it, and says so rather than
pretending it was saved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MAX_FEEDBACK_CHARS = 1000


@dataclass(frozen=True)
class FeedbackOutcome:
    saved: bool
    message: str
    # How the dialog shows it: "success", "info" (the demo) or "error".
    level: str = "error"


def problem(rating: Optional[int], suggestion: str, comments: str) -> Optional[str]:
    """What is wrong with an answer, in the student's words, or None."""
    if rating is None:
        return "Pick a rating from 1 to 5 stars."
    if not 1 <= rating <= 5:
        return "The rating must be between 1 and 5."
    if len(suggestion) > MAX_FEEDBACK_CHARS or len(comments) > MAX_FEEDBACK_CHARS:
        return f"Keep each answer under {MAX_FEEDBACK_CHARS} characters."
    return None


def submit(rating: Optional[int], suggestion: str, comments: str) -> FeedbackOutcome:
    """Validate one survey answer and save it when somebody is signed in."""
    suggestion = (suggestion or "").strip()
    comments = (comments or "").strip()
    issue = problem(rating, suggestion, comments)
    if issue:
        return FeedbackOutcome(False, issue)

    from services.auth_service import authenticated_client, current_role

    client = authenticated_client()
    if client is None:
        return FeedbackOutcome(
            False,
            "Thanks! This is the demo, so your answers were not sent. "
            "Sign in to send feedback to the Camp Prep AI team.",
            level="info",
        )

    from postgrest import ReturnMethod

    role = current_role()
    row = {
        "rating": rating,
        "suggestion": suggestion or None,
        "comments": comments or None,
        "role": role.value if role else None,
    }
    try:
        # Minimal return: the table has no read policy, so asking for the
        # inserted row back would be refused.
        client.table("app_feedback").insert(row, returning=ReturnMethod.minimal).execute()
    except Exception:  # noqa: BLE001 - the student gets a plain message instead
        return FeedbackOutcome(
            False, "We couldn't send your feedback just now. Please try again later."
        )
    return FeedbackOutcome(True, "Thanks for your feedback!", level="success")
