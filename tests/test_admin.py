"""Tests for the Admin page (db/migrations/010_admin.sql).

WHAT THESE COVER
  * The migration keeps its promises: app_admins is closed to every client
    role, every admin function opens with the admin guard, nothing is granted
    to anon, and no email is selected.
  * admin_service refuses non-admins before calling the database, sends only
    the agreed parameters, and turns database errors into safe messages.
  * The admin flag comes from the database and defaults to off.
  * Navigation shows the Admin page to signed-in admins only.
  * The page itself refuses a non-admin and renders for an admin.

WHAT THEY DO NOT COVER
  Running the SQL. The functions are modelled by `_AdminClient.rpc`; the
  static checks are a tripwire for somebody weakening the migration.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

from models import Role, User
from services import admin_service, auth_service
from tests.test_auth import STUDENT_PROFILE, FakeAuthClient, _install

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "db" / "migrations" / "010_admin.sql"
ADMIN_PAGE = str(ROOT / "pages" / "admin.py")

TEACHER_PROFILE = dict(STUDENT_PROFILE, role="teacher", teacher_id=None)


class _Rpc:
    def __init__(self, run) -> None:
        self._run = run

    def execute(self) -> Any:
        return SimpleNamespace(data=self._run())


class _AdminClient(FakeAuthClient):
    """A client whose `rpc` stands in for the functions in migration 010.

    `responses` maps a function name to the data it returns, or to an
    Exception it raises the way PostgREST surfaces a `raise exception`.
    """

    def __init__(
        self, is_admin: bool, responses: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.is_admin = is_admin
        self.responses = dict(responses or {})
        self.calls: List[Tuple[str, Optional[Dict[str, Any]]]] = []

    def rpc(self, name: str, params: Optional[Dict[str, Any]] = None) -> _Rpc:
        if name == "is_app_admin":
            return _Rpc(lambda: self.is_admin)
        self.calls.append((name, params))

        def run() -> Any:
            response = self.responses.get(name)
            if isinstance(response, Exception):
                raise response
            return response

        return _Rpc(run)


def _signed_in(
    monkeypatch: pytest.MonkeyPatch,
    is_admin: bool,
    responses: Optional[Dict[str, Any]] = None,
) -> _AdminClient:
    client = _AdminClient(
        is_admin,
        responses,
        accounts={"t@example.com": "hunter22"},
        profiles=[dict(TEACHER_PROFILE)],
    )
    _install(monkeypatch, client)
    assert auth_service.sign_in("t@example.com", "hunter22").ok
    return client


# --------------------------------------------------------------------------
# The admin flag
# --------------------------------------------------------------------------
def test_the_admin_flag_comes_from_the_database(monkeypatch: pytest.MonkeyPatch) -> None:
    _signed_in(monkeypatch, is_admin=True)
    assert auth_service.current_user().is_admin is True


def test_a_failing_admin_check_means_not_an_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Before 010 is applied the function is missing: the page must stay hidden."""
    client = _signed_in(monkeypatch, is_admin=False)

    def missing(name: str, params: Optional[Dict[str, Any]] = None) -> _Rpc:
        def run() -> Any:
            raise RuntimeError("Could not find the function public.is_app_admin")

        return _Rpc(run)

    monkeypatch.setattr(client, "rpc", missing)
    auth_service.invalidate_cached_profile()
    assert auth_service.current_user().is_admin is False


def test_users_are_not_admins_by_default() -> None:
    assert User(display_name="S-1101").is_admin is False


# --------------------------------------------------------------------------
# admin_service
# --------------------------------------------------------------------------
def test_a_non_admin_is_refused_without_calling_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _signed_in(monkeypatch, is_admin=False)

    outcomes = [
        admin_service.create_teacher_invite("Ms Rao", 1, 7),
        admin_service.cancel_teacher_invite(3),
        admin_service.demote_teacher("usr_t9", True),
    ]
    invites, invite_error = admin_service.list_teacher_invites()
    teachers, teacher_error = admin_service.list_teachers()

    assert all(not o.ok and o.message == admin_service.NOT_ADMIN_MESSAGE for o in outcomes)
    assert invites == [] and teachers == []
    assert invite_error == teacher_error == admin_service.NOT_ADMIN_MESSAGE
    assert client.calls == []


def test_signed_out_callers_are_told_to_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _AdminClient(is_admin=True)
    _install(monkeypatch, client)

    outcome = admin_service.create_teacher_invite("x", 1, 7)

    assert not outcome.ok and "Sign in" in outcome.message
    assert client.calls == []


def test_creating_a_code_returns_it_once_and_sends_only_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _signed_in(
        monkeypatch, is_admin=True, responses={"admin_create_teacher_invite": "A1B2C3D4E5F6A7B8C9"}
    )

    outcome = admin_service.create_teacher_invite("  Ms Rao, maths ", 3, 14)

    assert outcome.ok and outcome.code == "A1B2C3D4E5F6A7B8C9"
    assert client.calls == [
        (
            "admin_create_teacher_invite",
            {"p_note": "Ms Rao, maths", "p_max_uses": 3, "p_valid_days": 14},
        )
    ]


@pytest.mark.parametrize(
    "note, uses, days",
    [("x" * 121, 1, 7), ("ok", 0, 7), ("ok", 21, 7), ("ok", 1, 0), ("ok", 1, 31)],
)
def test_out_of_range_settings_never_reach_the_database(
    monkeypatch: pytest.MonkeyPatch, note: str, uses: int, days: int
) -> None:
    client = _signed_in(monkeypatch, is_admin=True)

    outcome = admin_service.create_teacher_invite(note, uses, days)

    assert not outcome.ok
    assert client.calls == []


def test_database_messages_are_shown_only_when_deliberate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _signed_in(
        monkeypatch,
        is_admin=True,
        responses={
            "admin_demote_teacher": RuntimeError(
                "{'code': 'P0001', 'message': 'You cannot demote yourself.'}"
            ),
            "admin_cancel_teacher_invite": RuntimeError(
                'duplicate key value violates unique constraint "teacher_invites_pkey"'
            ),
            "admin_list_teachers": RuntimeError(
                "Could not find the function public.admin_list_teachers"
            ),
        },
    )

    assert admin_service.demote_teacher("usr_s01", False).message == "You cannot demote yourself."
    leaked = admin_service.cancel_teacher_invite(1).message
    assert leaked == admin_service.GENERIC_MESSAGE
    assert "teacher_invites_pkey" not in leaked
    _, error = admin_service.list_teachers()
    assert error == admin_service.NOT_SET_UP_MESSAGE


def test_invite_rows_are_parsed_and_given_a_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _signed_in(
        monkeypatch,
        is_admin=True,
        responses={
            "admin_list_teacher_invites": [
                {"id": 1, "note": "Live", "max_uses": 2, "use_count": 1,
                 "expires_at": "2999-01-01T00:00:00+00:00", "created_at": "2026-11-01T09:00:00Z",
                 "last_used_by": "Ms Rao", "last_used_at": "2026-11-02T09:00:00Z"},
                {"id": 2, "note": None, "max_uses": 1, "use_count": 1,
                 "expires_at": "2999-01-01T00:00:00+00:00", "created_at": None,
                 "last_used_by": None, "last_used_at": None},
                {"id": 3, "note": "Old", "max_uses": 1, "use_count": 0,
                 "expires_at": "2020-01-01T00:00:00+00:00", "created_at": None,
                 "last_used_by": None, "last_used_at": None},
            ]
        },
    )

    rows, error = admin_service.list_teacher_invites()

    assert error is None
    assert [r.status() for r in rows] == ["Active", "Used up", "Expired"]
    assert rows[1].note == ""


def test_demote_sends_the_profile_and_the_release_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _signed_in(monkeypatch, is_admin=True)

    outcome = admin_service.demote_teacher("usr_t9", False)

    assert outcome.ok
    assert client.calls == [
        ("admin_demote_teacher", {"p_profile_id": "usr_t9", "p_release_students": False})
    ]


# --------------------------------------------------------------------------
# Navigation
# --------------------------------------------------------------------------
def _paths(role: Role, **kwargs: Any) -> set:
    from components.navigation import pages_for

    return {spec["path"] for spec in pages_for(role, **kwargs)}


@pytest.mark.parametrize("role", [Role.STUDENT, Role.TEACHER])
def test_the_admin_page_is_only_for_signed_in_admins(role: Role) -> None:
    assert "pages/admin.py" in _paths(role, signed_in=True, is_admin=True)
    assert "pages/admin.py" not in _paths(role, signed_in=True, is_admin=False)
    # The demo and signed-out visitors never see it, flag or not.
    assert "pages/admin.py" not in _paths(role, signed_in=False, is_admin=True)
    assert "pages/admin.py" not in _paths(role)


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------
def _admin_page(monkeypatch: pytest.MonkeyPatch, is_admin: bool):
    from streamlit.testing.v1 import AppTest

    user = User(id="usr_t01", display_name="Herdy", role=Role.TEACHER, is_admin=is_admin)
    monkeypatch.setattr(auth_service, "current_user", lambda: user)
    monkeypatch.setattr(
        admin_service,
        "list_teacher_invites",
        lambda: (
            [
                admin_service.InviteRow(
                    id=1, note="Ms Rao", max_uses=1, use_count=0,
                    expires_at=None, created_at=None, last_used_by=None, last_used_at=None,
                )
            ],
            None,
        ),
    )
    monkeypatch.setattr(
        admin_service,
        "list_teachers",
        lambda: (
            [
                admin_service.TeacherRow("usr_t01", "Herdy", 0, True),
                admin_service.TeacherRow("usr_t02", "Ms Rao", 12, False),
            ],
            None,
        ),
    )
    at = AppTest.from_file(ADMIN_PAGE, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def test_the_page_refuses_a_non_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    at = _admin_page(monkeypatch, is_admin=False)
    assert any("for admins" in e.value for e in at.error)
    assert "Create code" not in [b.label for b in at.button]


def test_the_page_renders_for_an_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    at = _admin_page(monkeypatch, is_admin=True)
    labels = [b.label for b in at.button]
    assert "Create code" in labels
    assert "Cancel code" in labels
    assert "Remove teacher access" in labels
    # Only the non-admin teacher can be removed.
    [teacher] = [s for s in at.selectbox if s.label == "Teacher"]
    assert teacher.options == ["Ms Rao (usr_t02)"]


def test_a_new_code_is_shown_once(monkeypatch: pytest.MonkeyPatch) -> None:
    at = _admin_page(monkeypatch, is_admin=True)
    monkeypatch.setattr(
        admin_service,
        "create_teacher_invite",
        lambda note, uses, days: admin_service.AdminOutcome(True, "ok", code="ABCDEF123456789012"),
    )
    next(b for b in at.button if b.label == "Create code").click().run()
    assert not at.exception, at.exception
    assert [c.value for c in at.code] == ["ABCDEF123456789012"]

    at.run()
    assert [c.value for c in at.code] == []


# --------------------------------------------------------------------------
# The migration keeps its promises
# --------------------------------------------------------------------------
def _migration_sql() -> str:
    """The executable part of 010, without comments or the operator notes."""
    text = MIGRATION.read_text(encoding="utf-8")
    lines = [line.split("--", 1)[0] for line in text.splitlines()]
    return "\n".join(lines).lower()


def _functions(sql: str) -> Dict[str, str]:
    bodies = re.findall(
        r"create or replace function public\.(\w+)\((.*?)\$fn\$(.*?)\$fn\$", sql, re.S
    )
    return {name: body for name, _, body in bodies}


def test_app_admins_is_closed_to_every_client_role() -> None:
    sql = _migration_sql()
    assert "alter table public.app_admins enable row level security" in sql
    assert "revoke all on public.app_admins from public, anon, authenticated" in sql
    assert "create policy" not in sql
    assert "insert into public.app_admins" not in sql


def test_every_admin_function_opens_with_the_guard() -> None:
    functions = _functions(_migration_sql())
    admin_functions = {n: b for n, b in functions.items() if n.startswith("admin_")}

    assert set(admin_functions) == {
        "admin_create_teacher_invite",
        "admin_list_teacher_invites",
        "admin_cancel_teacher_invite",
        "admin_list_teachers",
        "admin_demote_teacher",
    }
    for name, body in admin_functions.items():
        assert "public.app_require_admin()" in body, name


def test_nothing_is_granted_to_anonymous_callers_and_the_guard_to_nobody() -> None:
    sql = _migration_sql()
    assert not re.search(r"grant[^;]*to[^;]*\banon\b", sql)
    assert (
        "revoke all on function public.app_require_admin() from public, anon, authenticated"
        in sql
    )
    assert "grant execute on function public.app_require_admin" not in sql
    for name in _functions(sql):
        if name != "app_require_admin":
            assert f"revoke all on function public.{name}(" in sql, name


def test_no_email_and_no_code_hash_leave_the_database() -> None:
    sql = _migration_sql()
    listing = _functions(sql)["admin_list_teacher_invites"]
    assert "code_hash" not in listing
    assert "email" not in sql
    assert "auth.users" not in sql


def test_setup_all_includes_010() -> None:
    setup = (ROOT / "db" / "setup_all.sql").read_text(encoding="utf-8")
    assert "-- Source: db/migrations/010_admin.sql" in setup
    assert "('app_admins')" in setup
