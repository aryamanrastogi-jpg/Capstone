"""Sign in, sign out, and who the signed-in user is.

WHAT REPLACES WHAT
  Demo mode identifies you with a dropdown in the sidebar. That is a convenience
  for showing both journeys, and it is not authentication: you pick a role and
  the app believes you. This module is the real thing - the role comes back from
  `profiles`, written by a database trigger at sign-up (db/migrations/002), and
  there is no code path here or anywhere else that can set it directly. The
  one route to teacher is `redeem_teacher_invite`, which hands a code to a
  database function (db/migrations/005) - the operator decides who gets a code,
  the database decides whether it is good, and the client decides nothing.

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
import math
import re
import time
from typing import Any, Dict, Optional, Tuple

import streamlit as st

from models import Role, User
from services import mappers
from utils.config import get_settings

# Session-state keys. The client itself is held here, not the credentials.
CLIENT = "_auth_client"
PROFILE = "_auth_profile"
FAILED_SIGN_INS = "_auth_failed_sign_ins"
LOCKED_UNTIL = "_auth_locked_until"

# Input limits. Every field a visitor can type into is bounded, so a pasted
# megabyte cannot travel to Supabase or sit in session state.
MAX_EMAIL_CHARS = 254  # the RFC 5321 limit on a forward path
MAX_PASSWORD_CHARS = 128
MAX_NAME_CHARS = 60  # matches left(..., 60) in the 004 trigger
MAX_INVITE_CODE_CHARS = 64
MIN_PASSWORD_CHARS = 8

# Failed sign-ins per browser session before the form locks, and for how long.
# This is a speed bump against somebody guessing at a keyboard, not the real
# defence against credential stuffing - that is Supabase Auth's own per-IP rate
# limit, which opening a new browser session cannot reset. This one it can.
MAX_FAILED_SIGN_INS = 5
LOCKOUT_SECONDS = 60

INVALID_INVITE_MESSAGE = "That invite code is not valid."


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
        return create_client(settings.supabase_url, settings.supabase_publishable_key)
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
def password_problem(password: str) -> Optional[str]:
    """Why a new password is not acceptable, or None if it is.

    Deliberately modest: length does most of the work, and the letter-and-number
    rule only stops the very worst choices ("password", "12345678"). Supabase
    enforces its own minimum too; this is the one the person meets first, with a
    message that says exactly what to change.
    """
    if len(password) < MIN_PASSWORD_CHARS:
        return f"Your password must be at least {MIN_PASSWORD_CHARS} characters."
    if len(password) > MAX_PASSWORD_CHARS:
        return f"Your password must be at most {MAX_PASSWORD_CHARS} characters."
    if not any(ch.isalpha() for ch in password):
        return "Your password must include at least one letter."
    if not any(ch.isdigit() for ch in password):
        return "Your password must include at least one number."
    return None


def sign_in_locked_for() -> int:
    """Seconds until this session may try to sign in again; 0 if it may now."""
    try:
        until = float(st.session_state.get(LOCKED_UNTIL) or 0)
    except Exception:  # noqa: BLE001 - no session state available
        return 0
    remaining = until - time.time()
    return math.ceil(remaining) if remaining > 0 else 0


def _record_failed_sign_in() -> None:
    try:
        failures = int(st.session_state.get(FAILED_SIGN_INS) or 0) + 1
        if failures >= MAX_FAILED_SIGN_INS:
            st.session_state[LOCKED_UNTIL] = time.time() + LOCKOUT_SECONDS
            failures = 0
        st.session_state[FAILED_SIGN_INS] = failures
    except Exception:  # noqa: BLE001 - no session state available
        pass


def _reset_failed_sign_ins() -> None:
    try:
        st.session_state.pop(FAILED_SIGN_INS, None)
        st.session_state.pop(LOCKED_UNTIL, None)
    except Exception:  # noqa: BLE001 - no session state available
        pass


def sign_in(email: str, password: str) -> AuthOutcome:
    locked = sign_in_locked_for()
    if locked:
        # Checked before the client is touched, so a locked session sends
        # nothing to Supabase at all.
        return AuthOutcome(
            False, f"Too many failed attempts. Try again in {locked} seconds."
        )
    if len(email) > MAX_EMAIL_CHARS or len(password) > MAX_PASSWORD_CHARS:
        # Same wording as a wrong password: an over-long input is just another
        # way of not matching an account.
        _record_failed_sign_in()
        return AuthOutcome(False, "That email and password do not match an account.")

    client = session_client()
    if client is None:
        return AuthOutcome(False, "Supabase is not configured on this instance.")

    try:
        client.auth.sign_in_with_password(
            {"email": email.strip(), "password": password}
        )
    except Exception as exc:  # noqa: BLE001 - shown to the user
        _record_failed_sign_in()
        return AuthOutcome(False, _readable_auth_error(exc))

    _reset_failed_sign_ins()
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


def sign_up(email: str, password: str, full_name: str = "") -> AuthOutcome:
    """Create an account. The profile is created by the database, not here.

    Only the name travels, as sign-up metadata; the trigger in
    db/migrations/004_profile_details.sql makes it the display name. The role is
    never sent - the trigger writes role='student' whatever a client asks for.
    """
    if len(email.strip()) > MAX_EMAIL_CHARS:
        return AuthOutcome(False, "That email address is too long.")
    if len(full_name.strip()) > MAX_NAME_CHARS:
        return AuthOutcome(
            False, f"Your name must be at most {MAX_NAME_CHARS} characters."
        )
    problem = password_problem(password)
    if problem:
        return AuthOutcome(False, problem)

    client = session_client()
    if client is None:
        return AuthOutcome(False, "Supabase is not configured on this instance.")

    try:
        credentials: Dict[str, Any] = {"email": email.strip(), "password": password}
        if full_name.strip():
            credentials["options"] = {"data": {"full_name": full_name.strip()}}
        response = client.auth.sign_up(credentials)
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


# --------------------------------------------------------------------------
# Your own profile: edit, photo, delete
# --------------------------------------------------------------------------
AVATAR_BUCKET = "avatars"
MAX_AVATAR_BYTES = 2 * 1024 * 1024
AVATAR_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def current_email() -> Optional[str]:
    client = authenticated_client()
    if client is None:
        return None
    try:
        response = client.auth.get_user()
        return getattr(response.user, "email", None) if response else None
    except Exception:  # noqa: BLE001 - shown as blank
        return None


def update_profile(display_name: str, year_group: Optional[int]) -> AuthOutcome:
    """Change your name and year group. The role is not writable (see 004)."""
    name = display_name.strip()
    if not 1 <= len(name) <= 60:
        return AuthOutcome(False, "Your name must be between 1 and 60 characters.")
    if year_group is not None and not 7 <= year_group <= 11:
        return AuthOutcome(False, "Year group must be between 7 and 11.")
    return _write_profile(
        {"display_name": name, "year_group": year_group}, "Profile saved."
    )


def upload_avatar(data: bytes, filename: str) -> AuthOutcome:
    """Store a photo at avatars/<auth id>/avatar.<ext> and point the profile at it."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in AVATAR_TYPES:
        return AuthOutcome(False, "Use a PNG, JPG or WEBP image.")
    if len(data) > MAX_AVATAR_BYTES:
        return AuthOutcome(False, "That image is larger than 2 MB.")

    client, auth_id = _signed_in_client_and_id()
    if client is None:
        return AuthOutcome(False, "Sign in first.")

    path = f"{auth_id}/avatar.{ext}"
    try:
        _remove_avatar_files(client, auth_id)
        bucket = client.storage.from_(AVATAR_BUCKET)
        bucket.upload(
            path, data, {"content-type": AVATAR_TYPES[ext], "upsert": "true"}
        )
        url = bucket.get_public_url(path)
    except Exception as exc:  # noqa: BLE001 - shown to the user
        return AuthOutcome(False, f"The photo could not be uploaded ({_redacted(exc)}).")

    # A fresh query string, so browsers do not keep showing the old photo.
    url = f"{url.split('?')[0]}?v={int(time.time())}"
    return _write_profile({"avatar_url": url}, "Photo updated.")


def remove_avatar() -> AuthOutcome:
    client, auth_id = _signed_in_client_and_id()
    if client is None:
        return AuthOutcome(False, "Sign in first.")
    try:
        _remove_avatar_files(client, auth_id)
    except Exception as exc:  # noqa: BLE001 - shown to the user
        return AuthOutcome(False, f"The photo could not be removed ({_redacted(exc)}).")
    return _write_profile({"avatar_url": None}, "Photo removed.")


def delete_account() -> AuthOutcome:
    """Delete the signed-in account, its photo and (by cascade) its profile."""
    client, auth_id = _signed_in_client_and_id()
    if client is None:
        return AuthOutcome(False, "Sign in first.")
    try:
        _remove_avatar_files(client, auth_id)
    except Exception:  # noqa: BLE001 - a missing photo must not block deletion
        pass
    try:
        client.rpc("delete_my_account").execute()
    except Exception as exc:  # noqa: BLE001 - shown to the user
        return AuthOutcome(
            False,
            "The account could not be deleted. Check that "
            f"db/migrations/004_profile_details.sql is applied ({_redacted(exc)}).",
        )
    sign_out()
    return AuthOutcome(True, "Your account has been deleted.")


def redeem_teacher_invite(code: str) -> AuthOutcome:
    """Exchange an operator-issued invite code for the teacher role.

    Everything that matters happens in Postgres
    (db/migrations/005_teacher_invites.sql): the function promotes auth.uid()
    and nobody else, checks the hashed code, its use count and its expiry, and
    clears teacher_id. This side only tidies the input and never sends a role -
    there is no argument it could send one in.

    Every refusal from the database is reported with the same sentence, so the
    page cannot become an oracle for which codes exist, were used or expired.
    """
    cleaned = "".join(code.split()).upper()
    if not cleaned or len(cleaned) > MAX_INVITE_CODE_CHARS:
        return AuthOutcome(False, INVALID_INVITE_MESSAGE)

    user = current_user()
    client = authenticated_client()
    if user is None or client is None:
        return AuthOutcome(False, "Sign in first.")
    if user.role is Role.TEACHER:
        return AuthOutcome(True, "You already have teacher access.")

    try:
        client.rpc("redeem_teacher_invite", {"code": cleaned}).execute()
    except Exception as exc:  # noqa: BLE001 - collapsed to one message below
        if "could not find the function" in str(exc).lower():
            return AuthOutcome(
                False,
                "Invite codes are not set up on this instance. Apply "
                "db/migrations/005_teacher_invites.sql.",
            )
        return AuthOutcome(False, INVALID_INVITE_MESSAGE)

    _clear_cached_profile()
    return AuthOutcome(True, "Invite accepted. You now have teacher access.")


def _signed_in_client_and_id() -> Tuple[Optional[Any], Optional[str]]:
    client = authenticated_client()
    if client is None:
        return None, None
    try:
        response = client.auth.get_user()
        auth_id = response.user.id if response and response.user else None
    except Exception:  # noqa: BLE001 - treated as signed out
        auth_id = None
    return (client, auth_id) if auth_id else (None, None)


def _remove_avatar_files(client: Any, auth_id: str) -> None:
    bucket = client.storage.from_(AVATAR_BUCKET)
    existing = bucket.list(auth_id) or []
    paths = [f"{auth_id}/{item['name']}" for item in existing if item.get("name")]
    if paths:
        bucket.remove(paths)


def _write_profile(changes: Dict[str, Any], success: str) -> AuthOutcome:
    user = current_user()
    client = authenticated_client()
    if user is None or client is None:
        return AuthOutcome(False, "Sign in first.")
    try:
        client.table("profiles").update(changes).eq("id", user.id).execute()
    except Exception as exc:  # noqa: BLE001 - shown to the user
        return AuthOutcome(
            False,
            "Your profile could not be saved. Check that "
            f"db/migrations/004_profile_details.sql is applied ({_redacted(exc)}).",
        )
    _clear_cached_profile()
    return AuthOutcome(True, success)


def current_role() -> Optional[Role]:
    user = current_user()
    return user.role if user else None


def _clear_cached_profile() -> None:
    try:
        st.session_state.pop(PROFILE, None)
    except Exception:  # noqa: BLE001 - no session state available
        pass


_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
# A JWT is three base64url segments; a bearer header or an API key in a URL is
# a long run of token characters after a recognisable prefix.
_TOKEN_PATTERN = re.compile(
    r"eyJ[\w-]+\.[\w-]+\.[\w-]*"
    r"|(?i:bearer)\s+[\w.~+/=-]+"
    r"|(?i:(?:apikey|access_token|refresh_token|token|key)=)[\w.~+/=-]+"
    r"|sb_(?:publishable|secret)_[\w-]+"
)
_MAX_DETAIL_CHARS = 200


def _redacted(exc: Exception) -> str:
    """An exception's text, safe to put on the page.

    Storage and PostgREST errors are useful to show - "bucket not found" tells
    the operator which migration is missing - but they are free text from
    another service, and nothing guarantees they leave out the request that
    failed. So emails and anything token-shaped are blanked before display, and
    the whole thing is capped, whatever the library decided to include.
    """
    text = _TOKEN_PATTERN.sub("[redacted]", str(exc))
    text = _EMAIL_PATTERN.sub("[email]", text)
    if len(text) > _MAX_DETAIL_CHARS:
        text = text[:_MAX_DETAIL_CHARS] + "..."
    return text or type(exc).__name__


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
    if "rate limit" in lowered or "too many" in lowered:
        return "Too many attempts. Wait a minute and try again."
    # Anything else is summarised, never echoed. A raw gotrue message can carry
    # the email that was typed, and this string is rendered on the page.
    return "Authentication failed. Please try again."
