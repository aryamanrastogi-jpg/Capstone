"""Keep the suite offline, whatever the developer's .env says.

`utils.config` loads .env at import time, so a real Gemini key or Supabase
project there would otherwise send test traffic to live services. Every test
starts from demo mode with no AI provider; tests that need one build their own
`Settings` or pass a fake model explicitly.
"""

from __future__ import annotations

import os

import pytest

_LIVE_SERVICE_VARS = (
    "LLM_API_KEY",
    "LLM_MODEL",
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
)

# Set before any test module imports utils.config, so load_dotenv(override=False)
# keeps these blanks instead of filling them from .env.
for _name in _LIVE_SERVICE_VARS:
    os.environ[_name] = ""


@pytest.fixture(autouse=True)
def _fresh_settings():
    from services import llm_service
    from utils.config import get_settings

    get_settings.cache_clear()
    llm_service.clear_cache()
    yield
    get_settings.cache_clear()
    llm_service.clear_cache()


@pytest.fixture(autouse=True)
def _fresh_sign_in_lockouts():
    # The per-email lockout is process-wide (BUG-017), so it would otherwise
    # carry failed sign-ins from one test into the next.
    from services import auth_service

    auth_service._reset_process_lockouts()
    yield
    auth_service._reset_process_lockouts()
