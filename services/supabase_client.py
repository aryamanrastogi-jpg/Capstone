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
    # True when the credentials work but nobody has signed in. This is its own
    # state on purpose: it is neither "no backend" nor "working backend", and
    # conflating it with either produces a misleading sidebar.
    signed_out: bool = False


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
        # Reaching Supabase is not the same as being able to use it. Every
        # policy in db/policies.sql grants to `authenticated`, so until somebody
        # signs in this connection can read nothing and write nothing. Saying
        # "Connected" here would be true and useless; the app would appear to
        # be persisting and would in fact be discarding every write.
        if _has_session(_client):
            _status = ConnectionStatus(
                connected=True,
                demo_mode=False,
                message="Connected to Supabase.",
            )
        else:
            _status = ConnectionStatus(
                connected=True,
                demo_mode=True,
                signed_out=True,
                message=(
                    "Connected to Supabase, but nobody is signed in - running on "
                    "local sample data. Row Level Security allows no reads or "
                    "writes until a user authenticates."
                ),
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


def _has_session(client: Any) -> bool:
    """Is there a signed-in user on this client?

    Wrapped in a try because gotrue raises rather than returning None when no
    session has ever been stored, and "no session" is a normal state here, not
    a failure worth surfacing.
    """
    try:
        return client.auth.get_session() is not None
    except Exception:  # noqa: BLE001 - absence of a session is not an error
        return False


def get_authenticated_client() -> Optional[Any]:
    """A Supabase client that can actually do something, or None.

    This is what `services.repository` asks for. It returns None both when there
    are no credentials and when there is no signed-in user, because those two
    states have the same consequence: the Supabase backend would be useless, so
    the app should stay on session state and say so.
    """
    client = get_supabase_client()
    if client is None:
        return None
    status = get_connection_status()
    return client if not status.demo_mode else None


def reset_client_cache() -> None:
    """Test hook: forget the memoised client and status."""
    global _client, _status
    _client = None
    _status = None
