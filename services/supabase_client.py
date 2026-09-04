"""Supabase client wrapper.

Phase 1 runs entirely on Streamlit session state. This module exists so that
Phase 2 can swap the storage backend without touching the pages.

Rules honoured here:
  * Credentials are optional - the app runs in demo mode without them.
  * A missing credential is a normal, reported condition (demo mode).
  * A *present but broken* credential is surfaced loudly, never swallowed.
  * Credential values are never returned, logged, or rendered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from utils.config import get_settings


@dataclass(frozen=True)
class ConnectionStatus:
    connected: bool
    demo_mode: bool
    message: str
    is_error: bool = False


_client: Optional[Any] = None
_status: Optional[ConnectionStatus] = None


def get_connection_status() -> ConnectionStatus:
    """Describe the current backend without leaking any credential values."""
    if _status is None:
        get_supabase_client()
    return _status  # type: ignore[return-value]


def get_supabase_client() -> Optional[Any]:
    """Return a Supabase client, or None when running in demo mode.

    Never raises: the caller gets None plus an explanatory ConnectionStatus.
    """
    global _client, _status
    if _status is not None:
        return _client

    settings = get_settings()

    if not settings.supabase_configured:
        missing = ", ".join(settings.missing_supabase_vars())
        _client = None
        _status = ConnectionStatus(
            connected=False,
            demo_mode=True,
            message=(
                f"Demo mode - running on local sample data. "
                f"Set {missing} in a .env file to enable Supabase persistence."
            ),
        )
        return None

    try:
        from supabase import create_client  # imported lazily; optional at runtime
    except ImportError:
        _client = None
        _status = ConnectionStatus(
            connected=False,
            demo_mode=True,
            message=(
                "Supabase credentials were found, but the 'supabase' package is "
                "not installed. Run: pip install -r requirements.txt"
            ),
            is_error=True,
        )
        return None

    try:
        _client = create_client(settings.supabase_url, settings.supabase_anon_key)
        _status = ConnectionStatus(
            connected=True,
            demo_mode=False,
            message="Connected to Supabase.",
        )
    except Exception as exc:  # noqa: BLE001 - reported to the user, not hidden
        _client = None
        _status = ConnectionStatus(
            connected=False,
            demo_mode=True,
            message=(
                "Supabase credentials were found but the connection failed "
                f"({type(exc).__name__}). Falling back to local demo mode - "
                "changes will not be persisted."
            ),
            is_error=True,
        )
    return _client


def reset_client_cache() -> None:
    """Test hook: forget the memoised client and status."""
    global _client, _status
    _client = None
    _status = None
