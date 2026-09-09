"""Sign in, sign out, and who the signed-in user is.

WHAT REPLACES WHAT
  Demo mode identifies you with a dropdown in the sidebar. That is a convenience
  for showing both journeys, and it is not authentication: you pick a role and
  the app believes you. This module is the real thing - the role comes back from
  `profiles`, written by a database trigger at sign-up (db/migrations/002), and
  there is no code path here or anywhere else that can change it.

  Both live side by side on purpose. Without credentials the app still runs on
  sample data, which is what makes it demonstrable; with credentials and a
  signed-in user it runs on Postgres.

WHY THE CLIENT IS PER SESSION AND NOT PER PROCESS
  A Supabase client holds the signed-in user's access token. One Streamlit
  server process serves every browser that connects to it, so a module-level
  client would be shared across all of them - and the second person to sign in
  would be talking to the database as the first. That is not a subtle race; it
  is the whole confidentiality model gone.

  So the authenticated client lives in `st.session_state`, which Streamlit keeps
  per browser session, and `services.repository` asks for it per run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import streamlit as st

from models import Role, User
from services import mappers
from utils.config import get_settings

# Session-state keys. The client itself is held here, not the credentials.
CLIENT = "_auth_client"
PROFILE = "_auth_profile"


@dataclass(frozen=True)
class AuthOutcome:
    """The result of an attempt to sign in or sign up."""

    ok: bool
    message: str = ""
    needs_confirmation: bool = False


# --------------------------------------------------------------------------
# The per-session client
# --------------------------------------------------------------------------
def _new_client() -> Optional[Any]:
    """A fresh, unauthenticated Supabase client, or None if unconfigured."""
    settings = get_settings()
    if not settings.supabase_configured:
        return None
    try:
        from supabase import create_client
    except ImportError:
        return None
    try:
        return create_client(settings.supabase_url, settings.supabase_anon_key)
    except Exception:  # noqa: BLE001 - reported by services.supabase_client
        return None


def session_client() -> Optional[Any]:
    """This browser session's Supabase client, created on first use.

    Falls back to a plain local client when there is no Streamlit session to
    hang it on, which is what happens in a bare `python -c` or a unit test.
    """
    try:
        if CLIENT not in st.session_state:
            st.session_state[CLIENT] = _new_client()
        return st.session_state[CLIENT]
    except Exception:  # noqa: BLE001 - no session state available
        return _new_client()


def is_signed_in() -> bool:
    client = session_client()
    if client is None:
        return False
    try:
        return client.auth.get_session() is not None
    except Exception:  # noqa: BLE001 - "no session" is a normal state
        return False


def authenticated_client() -> Optional[Any]:
    """The client to talk to Postgres with, or None if nobody is signed in.

    `services.repository` uses this to decide between the Supabase and the
    session-state backend. None is returned for "not configured" and for "not
    signed in" alike, because both mean the same thing downstream: every policy
    grants to `authenticated`, so an anonymous client can do nothing at all.
    """
    return session_client() if is_signed_in() else None


# --------------------------------------------------------------------------
# Sign in / up / out
# --------------------------------------------------------------------------
def sign_in(email: str, password: str) -> AuthOutcome:
    client = session_client()
    if client is None:
        return AuthOutcome(False, "Supabase is not configured on this instance.")

    try:
        client.auth.sign_in_with_password(
            {"email": email.strip(), "password": password}
        )
    except Exception as exc:  # noqa: BLE001 - shown to the user
        return AuthOutcome(False, _readable_auth_error(exc))

    _clear_cached_profile()
    if current_user() is None:
        # Authentication worked but there is no profile row. That means the
        # sign-up trigger from db/migrations/002 is not installed - worth saying
        # plainly, because every page would otherwise look mysteriously empty.
        return AuthOutcome(
            False,
            "Signed in, but this account has no profile. Apply "
            "db/migrations/002_auth_profiles.sql, then sign in again.",
        )
    return AuthOutcome(True, "Signed in.")


def sign_up(email: str, password: str) -> AuthOutcome:
    """Create an account. The profile is created by the database, not here.

    Nothing about the role, the display name or the roster is sent: the trigger
    assigns an anonymous code and role='student' regardless of what a client
    asks for. See db/migrations/002_auth_profiles.sql.
    """
    client = session_client()
    if client is None:
        return AuthOutcome(False, "Supabase is not configured on this instance.")

    try:
        response = client.auth.sign_up(
            {"email": email.strip(), "password": password}
        )
    except Exception as exc:  # noqa: BLE001 - shown to the user
        return AuthOutcome(False, _readable_auth_error(exc))

    _clear_cached_profile()
    if getattr(response, "session", None) is None:
        return AuthOutcome(
            True,
            "Account created. Check your email to confirm it, then sign in.",
            needs_confirmation=True,
        )
    return AuthOutcome(True, "Account created and signed in.")


def sign_out() -> None:
    client = session_client()
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:  # noqa: BLE001 - signing out must always succeed
            pass
    _clear_cached_profile()
    # Drop the client too, so the next sign-in starts from a clean session
    # rather than inheriting anything from the last one.
    try:
        st.session_state.pop(CLIENT, None)
    except Exception:  # noqa: BLE001 - no session state available
        pass


# --------------------------------------------------------------------------
# Who is signed in
# --------------------------------------------------------------------------
def current_user() -> Optional[User]:
    """The signed-in user's profile, or None.

    The role on the returned User comes from the `profiles` row. It is not
    derived from anything the client said, and it cannot be changed from the
    application - db/policies.sql grants UPDATE on display_name and year_group
    only.
    """
    try:
        cached = st.session_state.get(PROFILE)
        if cached is not None:
            return cached
    except Exception:  # noqa: BLE001 - no session state available
        cached = None

    client = authenticated_client()
    if client is None:
        return None

    try:
        auth_user = client.auth.get_user()
        auth_id = auth_user.user.id if auth_user and auth_user.user else None
    except Exception:  # noqa: BLE001 - treated as signed out
        return None
    if auth_id is None:
        return None

    try:
        rows = (
            client.table("profiles")
            .select("*")
            .eq("auth_user_id", auth_id)
            .execute()
            .data
            or []
        )
    except Exception:  # noqa: BLE001 - treated as no profile
        return None
    if not rows:
        return None

    user = mappers.user_from_row(rows[0])
    try:
        st.session_state[PROFILE] = user
    except Exception:  # noqa: BLE001 - no session state available
        pass
    return user


def current_role() -> Optional[Role]:
    user = current_user()
    return user.role if user else None


def _clear_cached_profile() -> None:
    try:
        st.session_state.pop(PROFILE, None)
    except Exception:  # noqa: BLE001 - no session state available
        pass


def _readable_auth_error(exc: Exception) -> str:
    """Turn a gotrue exception into something worth showing a person.

    The wrong-password case is deliberately not distinguished from the
    no-such-account case: telling an anonymous visitor which emails have
    accounts is a disclosure, not a courtesy.
    """
    text = str(exc)
    lowered = text.lower()
    if "invalid login credentials" in lowered:
        return "That email and password do not match an account."
    if "email not confirmed" in lowered:
        return "Confirm your email address first - check your inbox."
    if "already registered" in lowered or "already been registered" in lowered:
        return "An account with that email already exists. Try signing in."
    if "password" in lowered and "least" in lowered:
        return "That password is too short."
    return text or "Authentication failed."
