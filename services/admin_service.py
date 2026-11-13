"""Admin actions: teacher invite codes and teachers.

HOW THE ADMIN PAGE IS OPENED
  With a passkey, not an account: whoever types the ADMIN_PASSKEY secret
  unlocks the page for their browser session, for UNLOCK_SECONDS. Nobody has
  to be signed in. The database cannot see that secret, so once the passkey
  checks out the calls go to Supabase with the service-role key
  (SUPABASE_SERVICE_ROLE_KEY), and db/migrations/011_admin_passkey.sql makes
  every admin function executable by `service_role` only.

WHAT KEEPS THAT SAFE ENOUGH
  * The passkey is compared in constant time, must be at least
    MIN_PASSKEY_CHARS long or admin stays switched off, and wrong guesses are
    counted across every session: MAX_FAILURES within LOCKOUT_SECONDS locks the
    form for everybody until the window passes.
  * The service-role client is built per call, only after `is_unlocked()`,
    and never stored in session state, a cache or a log. Nothing else in the
    app can reach it: the repository and auth_service never import this module.
  * Database messages are passed on only when they are one of the sentences
    the migration raises on purpose; anything else becomes one plain sentence.

The trade-off, chosen deliberately: anybody holding ADMIN_PASSKEY has full
admin. Keep it long and random, and rotate it if it might have leaked.
"""

from __future__ import annotations

import hmac
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

import streamlit as st

PASSKEY_ENV = "ADMIN_PASSKEY"
SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"

MIN_PASSKEY_CHARS = 16
MAX_PASSKEY_INPUT_CHARS = 256
UNLOCK_SECONDS = 30 * 60
MAX_FAILURES = 5
LOCKOUT_SECONDS = 5 * 60

MAX_USES = 20
MAX_VALID_DAYS = 30
MAX_NOTE_CHARS = 120

UNLOCKED_AT = "_admin_unlocked_at"

NOT_ADMIN_MESSAGE = "Admin access required."
WRONG_PASSKEY_MESSAGE = "That passkey is not right."
NOT_SET_UP_MESSAGE = (
    "Admin tools are not set up on this instance. Apply "
    "db/migrations/011_admin_passkey.sql."
)
GENERIC_MESSAGE = "That did not work. Try again in a moment."

# The sentences the migration raises deliberately. Only these are shown as they are.
_KNOWN_MESSAGES = (
    NOT_ADMIN_MESSAGE,
    "Uses must be between 1 and 20.",
    "Days valid must be between 1 and 30.",
    "Keep the note under 120 characters.",
    "No such invite code.",
    "That account is not a teacher.",
)

# Wrong passkeys across every session in this server process.
_failures: List[float] = []
_failures_lock = threading.Lock()


@dataclass(frozen=True)
class AdminOutcome:
    ok: bool
    message: str
    # The plain invite code, only on the call that created it.
    code: Optional[str] = None


@dataclass(frozen=True)
class InviteRow:
    id: int
    note: str
    max_uses: int
    use_count: int
    expires_at: Optional[datetime]
    created_at: Optional[datetime]
    last_used_by: Optional[str]
    last_used_at: Optional[datetime]

    def status(self, now: Optional[datetime] = None) -> str:
        now = now or datetime.now(timezone.utc)
        if self.use_count >= self.max_uses:
            return "Used up"
        if self.expires_at is not None and self.expires_at <= now:
            return "Expired"
        return "Active"


@dataclass(frozen=True)
class TeacherRow:
    profile_id: str
    display_name: str
    student_count: int


# --------------------------------------------------------------------------
# The passkey
# --------------------------------------------------------------------------
def _configured_passkey() -> str:
    return os.getenv(PASSKEY_ENV, "").strip()


def setup_problem() -> Optional[str]:
    """Why admin cannot be used on this instance, or None when it can.

    Never says what the passkey is, only whether it is usable.
    """
    passkey = _configured_passkey()
    if not passkey:
        return f"Admin is switched off: the {PASSKEY_ENV} secret is not set."
    if len(passkey) < MIN_PASSKEY_CHARS:
        return (
            f"Admin is switched off: {PASSKEY_ENV} is shorter than "
            f"{MIN_PASSKEY_CHARS} characters. Set a longer, random one."
        )
    if not os.getenv("SUPABASE_URL", "").strip():
        return "Admin needs Supabase: SUPABASE_URL is not set."
    if not os.getenv(SERVICE_KEY_ENV, "").strip():
        return f"Admin needs the {SERVICE_KEY_ENV} secret, which is not set."
    return None


def locked_for() -> int:
    """Seconds until the passkey form accepts guesses again (0 = open)."""
    now = time.monotonic()
    with _failures_lock:
        _failures[:] = [t for t in _failures if now - t < LOCKOUT_SECONDS]
        if len(_failures) < MAX_FAILURES:
            return 0
        return max(1, int(LOCKOUT_SECONDS - (now - _failures[0])))


def _record_failure() -> None:
    with _failures_lock:
        _failures.append(time.monotonic())


def _reset_failures() -> None:
    with _failures_lock:
        _failures.clear()


def unlock(passkey: str) -> AdminOutcome:
    problem = setup_problem()
    if problem:
        return AdminOutcome(False, problem)
    wait = locked_for()
    if wait:
        return AdminOutcome(False, f"Too many wrong passkeys. Try again in {wait} seconds.")

    typed = (passkey or "").strip()[:MAX_PASSKEY_INPUT_CHARS]
    if not typed or not hmac.compare_digest(
        typed.encode("utf-8"), _configured_passkey().encode("utf-8")
    ):
        _record_failure()
        return AdminOutcome(False, WRONG_PASSKEY_MESSAGE)

    st.session_state[UNLOCKED_AT] = time.monotonic()
    return AdminOutcome(True, "Admin unlocked.")


def is_unlocked() -> bool:
    if setup_problem():
        return False
    try:
        unlocked_at = st.session_state.get(UNLOCKED_AT)
    except Exception:  # noqa: BLE001 - no session state available
        return False
    if unlocked_at is None:
        return False
    if time.monotonic() - unlocked_at >= UNLOCK_SECONDS:
        lock()
        return False
    return True


def lock() -> None:
    try:
        st.session_state.pop(UNLOCKED_AT, None)
    except Exception:  # noqa: BLE001 - no session state available
        pass


# --------------------------------------------------------------------------
# The service-role client
# --------------------------------------------------------------------------
def _new_service_client() -> Any:
    from supabase import create_client  # imported lazily; optional at runtime

    return create_client(
        os.getenv("SUPABASE_URL", "").strip(), os.getenv(SERVICE_KEY_ENV, "").strip()
    )


def _admin_client() -> Tuple[Optional[Any], Optional[str]]:
    """A service-role client, only for an unlocked session."""
    if not is_unlocked():
        return None, NOT_ADMIN_MESSAGE
    try:
        return _new_service_client(), None
    except Exception:  # noqa: BLE001 - never echo the key or the URL
        return None, GENERIC_MESSAGE


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _message_for(exc: Exception) -> str:
    text = str(exc)
    if "could not find the function" in text.lower() or "PGRST202" in text:
        return NOT_SET_UP_MESSAGE
    for known in _KNOWN_MESSAGES:
        if known in text:
            return known
    return GENERIC_MESSAGE


# --------------------------------------------------------------------------
# Invite codes
# --------------------------------------------------------------------------
def create_teacher_invite(note: str, max_uses: int, valid_days: int) -> AdminOutcome:
    note = (note or "").strip()
    if len(note) > MAX_NOTE_CHARS:
        return AdminOutcome(False, "Keep the note under 120 characters.")
    if not 1 <= int(max_uses) <= MAX_USES:
        return AdminOutcome(False, "Uses must be between 1 and 20.")
    if not 1 <= int(valid_days) <= MAX_VALID_DAYS:
        return AdminOutcome(False, "Days valid must be between 1 and 30.")

    client, problem = _admin_client()
    if client is None:
        return AdminOutcome(False, problem or NOT_ADMIN_MESSAGE)
    try:
        code = client.rpc(
            "admin_create_teacher_invite",
            {"p_note": note, "p_max_uses": int(max_uses), "p_valid_days": int(valid_days)},
        ).execute().data
    except Exception as exc:  # noqa: BLE001 - mapped to a safe message
        return AdminOutcome(False, _message_for(exc))
    if not isinstance(code, str) or not code:
        return AdminOutcome(False, GENERIC_MESSAGE)
    return AdminOutcome(True, "Invite code created.", code=code)


def list_teacher_invites() -> Tuple[List[InviteRow], Optional[str]]:
    client, problem = _admin_client()
    if client is None:
        return [], problem
    try:
        data = client.rpc("admin_list_teacher_invites").execute().data or []
    except Exception as exc:  # noqa: BLE001 - mapped to a safe message
        return [], _message_for(exc)
    rows = [
        InviteRow(
            id=int(r["id"]),
            note=r.get("note") or "",
            max_uses=int(r.get("max_uses") or 1),
            use_count=int(r.get("use_count") or 0),
            expires_at=_parse_time(r.get("expires_at")),
            created_at=_parse_time(r.get("created_at")),
            last_used_by=r.get("last_used_by"),
            last_used_at=_parse_time(r.get("last_used_at")),
        )
        for r in data
    ]
    return rows, None


def cancel_teacher_invite(invite_id: int) -> AdminOutcome:
    client, problem = _admin_client()
    if client is None:
        return AdminOutcome(False, problem or NOT_ADMIN_MESSAGE)
    try:
        client.rpc("admin_cancel_teacher_invite", {"p_invite_id": int(invite_id)}).execute()
    except Exception as exc:  # noqa: BLE001 - mapped to a safe message
        return AdminOutcome(False, _message_for(exc))
    return AdminOutcome(True, "Invite code cancelled. It can no longer be used.")


# --------------------------------------------------------------------------
# Teachers
# --------------------------------------------------------------------------
def list_teachers() -> Tuple[List[TeacherRow], Optional[str]]:
    client, problem = _admin_client()
    if client is None:
        return [], problem
    try:
        data = client.rpc("admin_list_teachers").execute().data or []
    except Exception as exc:  # noqa: BLE001 - mapped to a safe message
        return [], _message_for(exc)
    rows = [
        TeacherRow(
            profile_id=r["profile_id"],
            display_name=r.get("display_name") or r["profile_id"],
            student_count=int(r.get("student_count") or 0),
        )
        for r in data
    ]
    return rows, None


def demote_teacher(profile_id: str, release_students: bool) -> AdminOutcome:
    client, problem = _admin_client()
    if client is None:
        return AdminOutcome(False, problem or NOT_ADMIN_MESSAGE)
    try:
        client.rpc(
            "admin_demote_teacher",
            {"p_profile_id": profile_id, "p_release_students": bool(release_students)},
        ).execute()
    except Exception as exc:  # noqa: BLE001 - mapped to a safe message
        return AdminOutcome(False, _message_for(exc))
    return AdminOutcome(True, "Teacher access removed. They now have a student account.")
