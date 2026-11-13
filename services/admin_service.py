"""Admin actions: teacher invite codes and teachers.

Everything that matters happens in Postgres (db/migrations/010_admin.sql).
Every function there opens with `app_require_admin()`, so a caller who is not
on `app_admins` is refused by the database whatever this module or the page
does. The checks here only save a round trip and give a clear message.

Messages from the database are passed on only when they are one of the
sentences 010 raises on purpose. Anything else (a constraint name, a network
error) becomes one plain sentence, so internals never reach the page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from services import auth_service

MAX_USES = 20
MAX_VALID_DAYS = 30
MAX_NOTE_CHARS = 120

NOT_ADMIN_MESSAGE = "Admin access required."
NOT_SET_UP_MESSAGE = (
    "Admin tools are not set up on this instance. Apply "
    "db/migrations/010_admin.sql."
)
GENERIC_MESSAGE = "That did not work. Try again in a moment."

# The sentences 010 raises deliberately. Only these are shown as they are.
_KNOWN_MESSAGES = (
    NOT_ADMIN_MESSAGE,
    "Uses must be between 1 and 20.",
    "Days valid must be between 1 and 30.",
    "Keep the note under 120 characters.",
    "No such invite code.",
    "You cannot demote yourself.",
    "That teacher is an admin. Remove their admin access first.",
    "That account is not a teacher.",
)


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
    is_admin: bool


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


def _admin_client() -> Tuple[Optional[Any], Optional[str]]:
    """The signed-in client, or the reason there is none to use."""
    user = auth_service.current_user()
    if user is None:
        return None, "Sign in first."
    if not user.is_admin:
        return None, NOT_ADMIN_MESSAGE
    client = auth_service.authenticated_client()
    if client is None:
        return None, "Sign in first."
    return client, None


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
            is_admin=bool(r.get("is_admin")),
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
