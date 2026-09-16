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

APP_NAME = "AssessAI"
APP_TAGLINE = "Teacher-reviewed AI assessment support for Grades 7-9"

# Upload guardrails
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_UPLOAD_EXTENSIONS: Set[str] = {".txt", ".pdf"}

PRIVACY_NOTICE = (
    "Prototype notice: use anonymised or synthetic student work only. "
    "Do not upload real student names or identifying information."
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
        """Placeholder only - Phase 1 never calls an LLM."""
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


def _publishable_key() -> str:
    """The Supabase publishable key (`sb_publishable_...`).

    SUPABASE_ANON_KEY is still read as a fallback, so a .env written before the
    rename keeps working. Supabase treats the two keys the same way: both are
    safe in a client, and Row Level Security decides what either can do.
    """
    for name in ("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        supabase_url=os.getenv("SUPABASE_URL", "").strip(),
        supabase_publishable_key=_publishable_key(),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "").strip(),
    )
