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
    """Describe the current backend without leaking any credential values.

    Whether the CREDENTIALS work is a property of the process and is worked out
    once. Whether anyone is SIGNED IN is a property of the browser session and
    is re-checked on every call - memoising it would mean one visitor signing in
    changed what the sidebar said for everybody else on the same server.
    """
    if _status is None:
        get_supabase_client()
    status = _status  # type: ignore[assignment]

    if not status.connected:
        return status

    if _has_session(_client):
        return ConnectionStatus(
            connected=True,
            demo_mode=False,
            message="Connected to Supabase.",
        )
    return ConnectionStatus(
        connected=True,
        demo_mode=True,
        signed_out=True,
        message=(
            "Connected to Supabase, but you are not signed in - running on "
            "local sample data. Row Level Security allows no reads or writes "
            "until you authenticate."
        ),
    )


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
        #
        # The signed-in half of that judgement is made per call in
        # get_connection_status, because it varies by browser session. What is
        # settled here, once, is only that the credentials themselves work.
        _status = ConnectionStatus(
            connected=True,
            demo_mode=True,
            signed_out=True,
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


def _has_session(_client: Any) -> bool:
    """Is there a signed-in user in THIS browser session?

    Note the client argument is ignored. Sign-in happens on the per-session
    client in `services.auth_service`, not on the module-level one this file
    builds to probe connectivity - so asking that client would always answer
    "signed out", however many people were actually signed in.
    """
    try:
        from services.auth_service import is_signed_in

        return is_signed_in()
    except Exception:  # noqa: BLE001 - absence of a session is not an error
        return False


def get_authenticated_client() -> Optional[Any]:
    """Deprecated: use `services.auth_service.authenticated_client()`.

    Kept as a thin forwarder because the per-session client is the only correct
    answer now, and two ways of asking would eventually disagree.
    """
    from services.auth_service import authenticated_client

    return authenticated_client()


def reset_client_cache() -> None:
    """Test hook: forget the memoised client and status."""
    global _client, _status
    _client = None
    _status = None
