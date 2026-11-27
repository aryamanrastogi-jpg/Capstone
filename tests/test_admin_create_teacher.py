"""Tests for creating teacher accounts from the Admin page (migration 012).

WHAT THESE COVER
  * The form is checked before anything reaches Supabase.
  * A good form creates a confirmed sign-in, then makes that profile a teacher
    with `admin_make_teacher`, sending only the auth user id.
  * All or nothing: if the role change fails, the new account is deleted.
  * A taken email gets a plain message; other errors never echo raw text.
  * A locked session never builds the service client.
  * 012 keeps the admin rules: guard first, service_role only, no email.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from services import admin_service

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "db" / "migrations" / "012_admin_create_teacher.sql"
PASSKEY = "any-passkey"
USER_ID = "7d4c2a8e-0000-4000-8000-000000000001"


class _AuthAdmin:
    def __init__(self, create_error: Optional[Exception] = None) -> None:
        self.create_error = create_error
        self.created: List[Dict[str, Any]] = []
        self.deleted: List[str] = []

    def create_user(self, attributes: Dict[str, Any]) -> Any:
        self.created.append(attributes)
        if self.create_error is not None:
            raise self.create_error
        return SimpleNamespace(user=SimpleNamespace(id=USER_ID))

    def delete_user(self, user_id: str) -> None:
        self.deleted.append(user_id)


class _Client:
    def __init__(self, rpc_error: Optional[Exception] = None, **auth_kwargs: Any) -> None:
        self.auth = SimpleNamespace(admin=_AuthAdmin(**auth_kwargs))
        self.rpc_error = rpc_error
        self.calls: List[tuple] = []

    def rpc(self, name: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self.calls.append((name, params))
        error = self.rpc_error

        def execute() -> Any:
            if error is not None:
                raise error
            return SimpleNamespace(data="usr_new")

        return SimpleNamespace(execute=execute)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    monkeypatch.setenv("ADMIN_PASSKEY", PASSKEY)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    store: Dict[str, Any] = {}
    monkeypatch.setattr(admin_service.st, "session_state", store)
    admin_service._reset_failures()
    yield store
    admin_service._reset_failures()


def _use(monkeypatch: pytest.MonkeyPatch, client: _Client) -> Dict[str, int]:
    built = {"n": 0}

    def build() -> _Client:
        built["n"] += 1
        return client

    monkeypatch.setattr(admin_service, "_new_service_client", build)
    return built


def _unlock() -> None:
    assert admin_service.unlock(PASSKEY).ok


@pytest.mark.parametrize(
    "name, email, password, wanted",
    [
        ("", "a@b.org", "secret123", "name"),
        ("x" * 61, "a@b.org", "secret123", "60"),
        ("Ms Rao", "not-an-email", "secret123", "email"),
        ("Ms Rao", "a@b.org", "short1", "temporary password"),
        ("Ms Rao", "a@b.org", "lettersonly", "number"),
    ],
)
def test_a_bad_form_never_reaches_supabase(
    monkeypatch: pytest.MonkeyPatch, name: str, email: str, password: str, wanted: str
) -> None:
    built = _use(monkeypatch, _Client())
    _unlock()
    outcome = admin_service.create_teacher(name, email, password)
    assert not outcome.ok and wanted in outcome.message
    assert built["n"] == 0


def test_a_locked_session_cannot_create_teachers(monkeypatch: pytest.MonkeyPatch) -> None:
    built = _use(monkeypatch, _Client())
    outcome = admin_service.create_teacher("Ms Rao", "rao@school.org", "secret123")
    assert not outcome.ok and outcome.message == admin_service.NOT_ADMIN_MESSAGE
    assert built["n"] == 0


def test_a_teacher_is_created_and_promoted(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    _use(monkeypatch, client)
    _unlock()
    outcome = admin_service.create_teacher(" Ms Rao ", " Rao@School.org ", "secret123")
    assert outcome.ok and "Ms Rao" in outcome.message
    assert "secret123" not in outcome.message and "rao@school.org" not in outcome.message
    [created] = client.auth.admin.created
    # ARY-002: the password is only a temporary one - the flag makes the
    # teacher choose their own at first sign-in (services/auth_service.py).
    assert created == {
        "email": "rao@school.org",
        "password": "secret123",
        "email_confirm": True,
        "user_metadata": {"full_name": "Ms Rao", "must_change_password": True},
    }
    assert client.calls == [("admin_make_teacher", {"p_auth_user_id": USER_ID})]
    assert client.auth.admin.deleted == []


def test_the_admin_is_told_the_teacher_will_choose_their_own_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, _Client())
    _unlock()
    outcome = admin_service.create_teacher("Ms Rao", "rao@school.org", "secret123")
    assert outcome.ok
    assert "temporary password" in outcome.message
    assert "own password" in outcome.message


def test_a_failed_promotion_deletes_the_new_account(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client(rpc_error=RuntimeError("connection reset by peer at 10.0.0.1"))
    _use(monkeypatch, client)
    _unlock()
    outcome = admin_service.create_teacher("Ms Rao", "rao@school.org", "secret123")
    assert not outcome.ok and outcome.message == admin_service.GENERIC_MESSAGE
    assert client.auth.admin.deleted == [USER_ID]


def test_a_missing_migration_names_012(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client(rpc_error=RuntimeError("PGRST202 Could not find the function"))
    _use(monkeypatch, client)
    _unlock()
    outcome = admin_service.create_teacher("Ms Rao", "rao@school.org", "secret123")
    assert not outcome.ok and "012_admin_create_teacher.sql" in outcome.message
    assert client.auth.admin.deleted == [USER_ID]


def test_a_taken_email_gets_a_plain_message(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client(create_error=RuntimeError("A user with this email address has already been registered"))
    _use(monkeypatch, client)
    _unlock()
    outcome = admin_service.create_teacher("Ms Rao", "rao@school.org", "secret123")
    assert not outcome.ok and outcome.message == admin_service.EMAIL_TAKEN_MESSAGE
    assert client.calls == []


def test_other_auth_errors_are_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client(create_error=RuntimeError("service-key rejected for https://example.supabase.co"))
    _use(monkeypatch, client)
    _unlock()
    outcome = admin_service.create_teacher("Ms Rao", "rao@school.org", "secret123")
    assert not outcome.ok and outcome.message == admin_service.GENERIC_MESSAGE


# --------------------------------------------------------------------------
# The migration
# --------------------------------------------------------------------------
def _sql() -> str:
    text = MIGRATION.read_text(encoding="utf-8")
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines()).lower()


def test_012_is_guarded_and_service_role_only() -> None:
    sql = _sql()
    body = re.search(r"function public\.admin_make_teacher\(.*?\$fn\$(.*?)\$fn\$", sql, re.S)
    assert body and "perform public.app_require_admin();" in body.group(1)
    assert "teacher_id = null" in body.group(1)
    assert re.findall(r"grant execute on function public\.(\w+)\([^)]*\) to (\w+);", sql) == [
        ("admin_make_teacher", "service_role")
    ]
    assert (
        "revoke all on function public.admin_make_teacher(uuid) from public, anon, authenticated;"
        in sql
    )
    assert "email" not in sql and "auth.users" not in sql


def test_setup_all_includes_012() -> None:
    setup = (ROOT / "db" / "setup_all.sql").read_text(encoding="utf-8")
    assert "-- Source: db/migrations/012_admin_create_teacher.sql" in setup
    assert setup.index("012_admin_create_teacher.sql") < setup.index("-- Source: db/policies.sql")
