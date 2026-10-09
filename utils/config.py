"""Application configuration.

Credentials are read from environment variables (optionally via a local .env
file). Nothing here is ever rendered to the UI or written to logs - only the
boolean "is this configured?" flags are exposed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Set

from dotenv import load_dotenv

load_dotenv(override=False)

APP_NAME = "Camp Prep AI"
# The strapline under the wordmark in assets/logo_full.svg and logo_dark.svg.
APP_SLOGAN = "Persistent Diagnostics & Intensive Mastery"
APP_TAGLINE = "Teacher-reviewed AI assessment support for IGCSE maths (Years 10–11)"

# Upload guardrails
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_PDF_EXTRACTION_SECONDS = 10
ALLOWED_UPLOAD_EXTENSIONS: Set[str] = {".txt", ".pdf"}

# The short notice at the foot of every page and in the sidebar. It has to be
# true in both modes: a signed-in account really does store a name and an
# email, and the demo stores nothing beyond the browser session. The older
# wording ("do not upload real names") stopped being true the day sign-up began
# asking for one, and a privacy notice that contradicts the form above it is
# worse than none.
PRIVACY_NOTICE = (
    "Privacy: accounts store your name and email so you can sign in and your "
    "teacher can recognise your work. Only you and your own teacher can see "
    "them. Delete your account any time from Profile. Keep other people's "
    "personal details out of anything you upload."
)

# The longer version, shown where somebody is deciding whether to make an
# account (the landing page and Sign In). One sentence per question a careful
# parent would ask: what, why, who, how long, how to get rid of it.
PRIVACY_DETAILS = (
    "**What we store.** Your full name, your email address, your year group "
    "if you add one, an optional profile photo, and the work you save.",
    "**Why.** Your email is how you sign in. Your name is how your teacher "
    "tells your work apart from everyone else's.",
    "**Who can see it.** You can see your own details. A teacher can see the "
    "names and work of students on their own class list, and nobody else's. "
    "Other students cannot see your name or details; a question set you "
    "choose to share to the library is shown without your name. Your email "
    "is shown only to you, on your Profile page.",
    "**What we never do.** Passwords are handled by our sign-in provider, "
    "kept only as a one-way hash, and cannot be read by the app or your "
    "teacher. Emails, passwords and sign-in tokens are never written to logs "
    "or shown on screen.",
    "**AI marking.** When AI marking is switched on, the text of your answer "
    "and the question (never your name or email) is sent to Google's Gemini "
    "service to be marked. On Gemini's free tier, Google may use that text to "
    "improve its products.",
    "**Deleting it.** Profile > Delete account removes your account, photo and "
    "profile. A teacher's assessment is retained in an archived state when a "
    "student has submitted work to it, so that student's history remains. Your "
    "unused assessments are deleted. A student's own saved work is deleted, "
    "except a shared set used by another student, which is archived for that "
    "student's history. This cannot be undone.",
    "**The demo.** Exploring the demo creates no account and stores nothing "
    "once you close the tab.",
)

AI_DISCLAIMER = (
    "All scores and feedback below are AI recommendations. "
    "Nothing is final until you review and approve it."
)


@dataclass(frozen=True)
class Settings:
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)

    @property
    def llm_configured(self) -> bool:
        """True when an AI grading key is set (see services/ai_grading_service.py)."""
        return bool(self.llm_api_key)

    @property
    def demo_mode(self) -> bool:
        """Demo mode = no Supabase persistence; session state is the store."""
        return not self.supabase_configured

    def missing_supabase_vars(self) -> List[str]:
        missing = []
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_publishable_key:
            missing.append("SUPABASE_PUBLISHABLE_KEY")
        return missing


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        supabase_url=os.getenv("SUPABASE_URL", "").strip(),
        supabase_publishable_key=os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip(),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "").strip(),
    )
