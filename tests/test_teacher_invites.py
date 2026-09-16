"""Tests for teacher invite codes - the one route from student to teacher.

WHAT THESE COVER
  How the application hands a code to the database and what it does with the
  answer: that only the code travels (never a role, never a profile id), that
  every kind of refusal reads the same, that the promoted role is re-read from
  the profile row rather than assumed, and that the Profile page offers the box
  to students only.

WHAT THEY DO NOT COVER
  The SQL function itself. `redeem_teacher_invite` in
  db/migrations/005_teacher_invites.sql is modelled here by `_InviteClient.rpc`,
  so these assert the client's behaviour against that model. The static checks
  on the migration file are a tripwire for somebody weakening it (storing the
  plain code, granting it to anon), not a substitute for running it against a
  live project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from models import Role, User
from services import auth_service
from tests.test_auth import STUDENT_PROFILE, FakeAuthClient, _install

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "db" / "migrations" / "005_teacher_invites.sql"
PROFILE_PAGE = str(ROOT / "pages" / "profile.py")


class _Rpc:
    def __init__(self, run) -> None:
        self._run = run

    def execute(self) -> Any:
        return self._run()


class _InviteClient(FakeAuthClient):
    """A client whose `rpc` behaves like the function in migration 005.

    `outcomes` maps a code to what the database would do with it: "ok" promotes
    the caller, anything else raises that text, the way PostgREST surfaces a
    `raise exception`.
    """

    def __init__(self, outcomes: Dict[str, str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.outcomes = outcomes
        self.calls: List[Tuple[str, Optional[Dict[str, Any]]]] = []

    def rpc(self, name: str, params: Optional[Dict[str, Any]] = None) -> _Rpc:
        self.calls.append((name, params))

        def run() -> Any:
            code = (params or {}).get("code", "")
            outcome = self.outcomes.get(code, "That invite code is not valid.")
            if outcome != "ok":
                raise RuntimeError(outcome)
            for row in self.profiles:
                if row["auth_user_id"] == self.auth_user_id:
                    row["role"] = "teacher"
                    row["teacher_id"] = None
            return None

        return _Rpc(run)


def _signed_in_student(
    monkeypatch: pytest.MonkeyPatch, outcomes: Dict[str, str]
) -> _InviteClient:
    client = _InviteClient(
        outcomes,
        accounts={"s@example.com": "hunter22"},
        profiles=[dict(STUDENT_PROFILE)],
    )
    _install(monkeypatch, client)
    assert auth_service.sign_in("s@example.com", "hunter22").ok
    return client


# --------------------------------------------------------------------------
# Redeeming
# --------------------------------------------------------------------------
def test_a_good_code_promotes_the_caller_and_the_role_is_reread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _signed_in_student(monkeypatch, {"A1B2C3D4E5F6": "ok"})
    assert auth_service.current_role() is Role.STUDENT

    outcome = auth_service.redeem_teacher_invite("a1b2 c3d4 e5f6 ")

    assert outcome.ok, outcome.message
    # The cached student profile must not survive: the new role has to come
    # from the row, or the menu would keep showing the student journey.
    assert auth_service.current_role() is Role.TEACHER
    assert auth_service.current_user().teacher_id is None
    assert client.calls == [("redeem_teacher_invite", {"code": "A1B2C3D4E5F6"})]


def test_only_the_code_is_sent_never_a_role_or_an_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The function acts on auth.uid(). Sending an id would invite trusting it."""
    client = _signed_in_student(monkeypatch, {"GOODCODE1": "ok"})

    auth_service.redeem_teacher_invite("goodcode1")

    [(_, params)] = client.calls
    assert set(params) == {"code"}
    assert "teacher" not in str(params).lower()
    assert "usr_" not in str(params)


def test_unknown_used_and_expired_codes_read_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A different message per failure would let somebody probe for live codes."""
    client = _signed_in_student(
        monkeypatch,
        {
            "USED1": "That invite code is not valid. (use_count exhausted)",
            "OLD1": "invite expired at 2026-01-01",
        },
    )

    messages = {
        auth_service.redeem_teacher_invite(code).message
        for code in ("NOSUCHCODE", "USED1", "OLD1")
    }

    assert messages == {auth_service.INVALID_INVITE_MESSAGE}
    assert auth_service.current_role() is Role.STUDENT
    assert len(client.calls) == 3


def test_a_blank_or_oversized_code_never_reaches_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _signed_in_student(monkeypatch, {})

    blank = auth_service.redeem_teacher_invite("   ")
    huge = auth_service.redeem_teacher_invite(
        "X" * (auth_service.MAX_INVITE_CODE_CHARS + 1)
    )

    assert blank.ok is False and huge.ok is False
    assert blank.message == huge.message == auth_service.INVALID_INVITE_MESSAGE
    assert client.calls == []


def test_redeeming_needs_a_signed_in_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _InviteClient({"GOODCODE1": "ok"})
    _install(monkeypatch, client)

    outcome = auth_service.redeem_teacher_invite("GOODCODE1")

    assert outcome.ok is False
    assert "Sign in" in outcome.message
    assert client.calls == []


def test_a_teacher_redeeming_again_spends_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second redemption would burn a use of somebody else's code."""
    client = _InviteClient(
        {"GOODCODE1": "ok"},
        accounts={"t@example.com": "hunter22"},
        profiles=[dict(STUDENT_PROFILE, role="teacher", teacher_id=None)],
    )
    _install(monkeypatch, client)
    auth_service.sign_in("t@example.com", "hunter22")

    outcome = auth_service.redeem_teacher_invite("GOODCODE1")

    assert outcome.ok is True
    assert client.calls == []


def test_a_missing_migration_is_named_not_disguised_as_a_bad_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _signed_in_student(
        monkeypatch,
        {
            "ANYCODE1": "Could not find the function "
            "public.redeem_teacher_invite(code) in the schema cache"
        },
    )

    outcome = auth_service.redeem_teacher_invite("ANYCODE1")

    assert outcome.ok is False
    assert "005_teacher_invites.sql" in outcome.message


# --------------------------------------------------------------------------
# The migration keeps its promises
# --------------------------------------------------------------------------
def _migration_sql() -> str:
    """The executable part of 005, without comments or the operator notes."""
    text = MIGRATION.read_text(encoding="utf-8")
    lines = [line.split("--", 1)[0] for line in text.splitlines()]
    return "\n".join(lines).lower()


def test_the_migration_stores_hashes_not_codes() -> None:
    import re

    sql = _migration_sql()
    table = sql.split("create table if not exists public.teacher_invites", 1)[1]
    table = table.split(");", 1)[0]
    columns = [line.strip().split()[0] for line in table.splitlines() if line.strip()]

    assert "code_hash" in columns
    # No column that could hold a usable code.
    assert not [c for c in columns if re.fullmatch(r"\(?code", c)]
    assert "digest(" in sql


def test_the_migration_promotes_only_the_caller_and_clears_the_roster() -> None:
    sql = _migration_sql()
    assert "security definer" in sql
    assert "public.app_profile_id()" in sql
    assert "set role = 'teacher', teacher_id = null" in sql
    assert "where id = me" in sql


def test_the_migration_fails_every_bad_code_with_one_message() -> None:
    sql = _migration_sql()
    assert sql.count("raise exception") == 2  # not signed in, and invalid
    assert sql.count("that invite code is not valid.") == 1
    assert "use_count < max_uses" in sql and "expires_at > now()" in sql
    assert "for update" in sql


def test_the_invite_table_and_function_are_closed_to_anonymous_callers() -> None:
    sql = _migration_sql()
    assert "alter table public.teacher_invites enable row level security" in sql
    assert "revoke all on public.teacher_invites from public, anon, authenticated" in sql
    assert "create policy" not in sql
    assert (
        "revoke all on function public.redeem_teacher_invite(text) from public, anon"
        in sql
    )


# --------------------------------------------------------------------------
# The Profile page
# --------------------------------------------------------------------------
def _profile_page(monkeypatch: pytest.MonkeyPatch, role: Role):
    from streamlit.testing.v1 import AppTest

    user = User(id="usr_s01", display_name="Ada Lovelace", role=role)
    monkeypatch.setattr(auth_service, "current_user", lambda: user)
    monkeypatch.setattr(auth_service, "current_email", lambda: "ada@example.com")

    at = AppTest.from_file(PROFILE_PAGE, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def test_a_student_is_offered_the_invite_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = _profile_page(monkeypatch, Role.STUDENT)

    [code_input] = [w for w in at.text_input if w.label == "Invite code"]
    assert code_input.max_chars == auth_service.MAX_INVITE_CODE_CHARS
    assert "Redeem code" in [b.label for b in at.button]
    # Nothing on the page lets the role itself be edited.
    [role_input] = [w for w in at.text_input if w.label == "Role"]
    assert role_input.disabled


def test_a_teacher_is_not_offered_the_invite_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = _profile_page(monkeypatch, Role.TEACHER)

    assert "Invite code" not in [w.label for w in at.text_input]
    assert "Redeem code" not in [b.label for b in at.button]


def test_submitting_a_code_on_the_page_goes_through_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: List[str] = []

    def _redeem(code: str) -> auth_service.AuthOutcome:
        received.append(code)
        return auth_service.AuthOutcome(False, auth_service.INVALID_INVITE_MESSAGE)

    monkeypatch.setattr(auth_service, "redeem_teacher_invite", _redeem)
    at = _profile_page(monkeypatch, Role.STUDENT)

    next(w for w in at.text_input if w.label == "Invite code").input("NOPE123")
    next(b for b in at.button if b.label == "Redeem code").click()
    at.run()

    assert not at.exception, at.exception
    assert received == ["NOPE123"]
    assert [e.value for e in at.error] == [auth_service.INVALID_INVITE_MESSAGE]
