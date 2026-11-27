"""Tests for the Admin page (db/migrations/011_admin_passkey.sql).

WHAT THESE COVER
  * The passkey: admin stays off without an ADMIN_PASSKEY and the
    service-role key, a wrong passkey is refused, counted and slowed down,
    repeated wrong guesses lock the form for that visitor only (BUG-008), and
    an unlock expires.
  * The service-role client is only built for an unlocked session, and only
    the agreed parameters are sent. Database errors become safe messages.
  * Routing: /admin is registered for everybody, hidden from the menu, and
    opens from the welcome screen; nothing links to it (BUG-016).
  * The migration keeps its promises: only `service_role` can run the admin
    functions, the guard checks the service-role claim, `app_admins` is gone.

WHAT THEY DO NOT COVER
  Running the SQL against Supabase. The functions are modelled by
  `_ServiceClient.rpc`; the static checks are a tripwire for somebody weakening
  the migration.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest
from streamlit.proto.TextInput_pb2 import TextInput as TextInputProto

from models import Role
from services import admin_service

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "db" / "migrations" / "011_admin_passkey.sql"
ADMIN_PAGE = str(ROOT / "views" / "admin.py")
APP = str(ROOT / "app.py")

PASSKEY = "correct-horse-battery-staple-42"


class _Rpc:
    def __init__(self, run) -> None:
        self._run = run

    def execute(self) -> Any:
        return SimpleNamespace(data=self._run())


class _ServiceClient:
    """Stands in for the service-role client and the functions in 011."""

    def __init__(self, responses: Optional[Dict[str, Any]] = None) -> None:
        self.responses = dict(responses or {})
        self.calls: List[Tuple[str, Optional[Dict[str, Any]]]] = []

    def rpc(self, name: str, params: Optional[Dict[str, Any]] = None) -> _Rpc:
        self.calls.append((name, params))

        def run() -> Any:
            response = self.responses.get(name)
            if isinstance(response, Exception):
                raise response
            return response

        return _Rpc(run)


@pytest.fixture(autouse=True)
def _admin_env(monkeypatch: pytest.MonkeyPatch):
    """A configured instance, a private session, and no wrong guesses yet."""
    monkeypatch.setenv("ADMIN_PASSKEY", PASSKEY)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    admin_service._reset_failures()
    yield
    admin_service._reset_failures()


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    store: Dict[str, Any] = {}
    monkeypatch.setattr(admin_service.st, "session_state", store)
    return store


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    """Counts service-client builds; `client` is the one handed out."""
    state: Dict[str, Any] = {"built": 0, "client": _ServiceClient()}

    def build() -> _ServiceClient:
        state["built"] += 1
        return state["client"]

    monkeypatch.setattr(admin_service, "_new_service_client", build)
    return state


# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------
def test_admin_is_off_without_a_passkey(monkeypatch: pytest.MonkeyPatch, session) -> None:
    monkeypatch.delenv("ADMIN_PASSKEY")
    assert "ADMIN_PASSKEY" in admin_service.setup_problem()
    assert not admin_service.unlock("anything").ok


def test_a_short_passkey_is_allowed(monkeypatch: pytest.MonkeyPatch, session) -> None:
    # No minimum length: any non-empty passkey switches admin on.
    monkeypatch.setenv("ADMIN_PASSKEY", "short")
    assert admin_service.setup_problem() is None
    assert not admin_service.unlock("shor").ok
    assert admin_service.unlock("short").ok
    assert admin_service.is_unlocked()


def test_admin_needs_the_service_key(monkeypatch: pytest.MonkeyPatch, session) -> None:
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY")
    assert "SUPABASE_SERVICE_ROLE_KEY" in admin_service.setup_problem()


def test_setup_messages_never_contain_the_passkey(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_PASSKEY", "tiny-secret")
    assert "tiny-secret" not in (admin_service.setup_problem() or "")


# --------------------------------------------------------------------------
# Unlocking
# --------------------------------------------------------------------------
def test_the_right_passkey_unlocks_this_session(session) -> None:
    assert not admin_service.is_unlocked()
    outcome = admin_service.unlock(f"  {PASSKEY} ")
    assert outcome.ok
    assert admin_service.is_unlocked()
    admin_service.lock()
    assert not admin_service.is_unlocked()


def test_a_wrong_passkey_is_refused_without_saying_why(session) -> None:
    outcome = admin_service.unlock(PASSKEY[:-1])
    assert not outcome.ok
    assert outcome.message == admin_service.WRONG_PASSKEY_MESSAGE
    assert not admin_service.is_unlocked()


def test_repeated_wrong_guesses_lock_the_form_even_for_the_right_passkey(session) -> None:
    for _ in range(admin_service.MAX_FAILURES):
        admin_service.unlock("wrong")
    assert admin_service.locked_for() > 0

    outcome = admin_service.unlock(PASSKEY)

    assert not outcome.ok and "Too many" in outcome.message
    assert not admin_service.is_unlocked()


class _Visitor:
    """Who `_client_key` says is asking; change `key` between calls to switch visitor."""

    key = "ip:203.0.113.5"


@pytest.fixture
def visitor(monkeypatch: pytest.MonkeyPatch) -> type:
    _Visitor.key = "ip:203.0.113.5"
    monkeypatch.setattr(admin_service, "_client_key", lambda: _Visitor.key)
    return _Visitor


def test_one_visitors_wrong_guesses_do_not_lock_the_owner_out(session, visitor) -> None:
    """BUG-008: five wrong passkeys from anyone used to block everybody."""
    visitor.key = "ip:198.51.100.7"  # somebody guessing
    for _ in range(admin_service.MAX_FAILURES):
        admin_service.unlock("wrong")
    assert admin_service.locked_for() > 0

    visitor.key = "ip:203.0.113.5"  # the owner, somewhere else
    assert admin_service.locked_for() == 0
    assert admin_service.unlock(PASSKEY).ok
    assert admin_service.is_unlocked()


def test_the_guesser_stays_locked_out_after_the_owner_unlocks(session, visitor) -> None:
    visitor.key = "ip:198.51.100.7"
    for _ in range(admin_service.MAX_FAILURES):
        admin_service.unlock("wrong")
    visitor.key = "ip:203.0.113.5"
    assert admin_service.unlock(PASSKEY).ok  # a right passkey must not clear anyone else's count
    visitor.key = "ip:198.51.100.7"
    assert admin_service.locked_for() > 0


class _Context:
    def __init__(self, headers: Dict[str, str], ip: Optional[str]) -> None:
        self.headers = headers
        self.ip_address = ip


def _with_context(
    monkeypatch: pytest.MonkeyPatch, headers: Dict[str, str], ip: Optional[str]
) -> None:
    fake = SimpleNamespace(context=_Context(headers, ip), session_state={})
    monkeypatch.setattr(admin_service, "st", fake)


def test_the_client_is_the_right_most_forwarded_hop(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first hop is whatever the visitor typed, so it must never be the key."""
    _with_context(monkeypatch, {"X-Forwarded-For": "6.6.6.6, 203.0.113.9"}, "10.0.0.1")
    first = admin_service._client_key()
    _with_context(monkeypatch, {"X-Forwarded-For": "7.7.7.7, 203.0.113.9"}, "10.0.0.1")
    assert admin_service._client_key() == first == "ip:203.0.113.9"


def test_without_a_forwarded_header_the_connection_address_is_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_context(monkeypatch, {}, "203.0.113.9")
    assert admin_service._client_key() == "ip:203.0.113.9"


def test_without_any_address_the_client_is_the_browser_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_context(monkeypatch, {}, None)
    assert admin_service._client_key().startswith("session:")


def test_the_failure_table_cannot_grow_without_limit(session, visitor, monkeypatch) -> None:
    monkeypatch.setattr(admin_service, "_MAX_TRACKED_CLIENTS", 50)
    for n in range(200):
        visitor.key = f"ip:10.0.{n // 250}.{n % 250}"
        admin_service.unlock("wrong")
    assert len(admin_service._failures) <= 50


def test_a_wrong_passkey_costs_a_pause_and_a_right_one_does_not(
    monkeypatch: pytest.MonkeyPatch, session
) -> None:
    pauses: List[float] = []
    monkeypatch.setattr(admin_service, "WRONG_PASSKEY_DELAY_SECONDS", 1.0)
    monkeypatch.setattr(admin_service.time, "sleep", pauses.append)

    assert admin_service.unlock(PASSKEY).ok
    assert pauses == []
    assert not admin_service.unlock("wrong").ok
    assert pauses == [1.0]


def test_the_lockout_ends_after_its_window(monkeypatch: pytest.MonkeyPatch, session) -> None:
    now = [1000.0]
    monkeypatch.setattr(admin_service.time, "monotonic", lambda: now[0])
    for _ in range(admin_service.MAX_FAILURES):
        admin_service.unlock("wrong")
    assert admin_service.locked_for() > 0

    now[0] += admin_service.LOCKOUT_SECONDS + 1

    assert admin_service.locked_for() == 0
    assert admin_service.unlock(PASSKEY).ok


def test_an_unlock_expires(monkeypatch: pytest.MonkeyPatch, session) -> None:
    now = [1000.0]
    monkeypatch.setattr(admin_service.time, "monotonic", lambda: now[0])
    assert admin_service.unlock(PASSKEY).ok

    now[0] += admin_service.UNLOCK_SECONDS + 1

    assert not admin_service.is_unlocked()
    assert admin_service.UNLOCKED_AT not in session


# --------------------------------------------------------------------------
# Admin actions
# --------------------------------------------------------------------------
def test_a_locked_session_never_builds_the_service_client(session, service) -> None:
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
    assert service["built"] == 0


def test_creating_a_code_returns_it_once_and_sends_only_the_settings(session, service) -> None:
    admin_service.unlock(PASSKEY)
    service["client"].responses["admin_create_teacher_invite"] = "A1B2C3D4E5F6A7B8C9"

    outcome = admin_service.create_teacher_invite("  Ms Rao, maths ", 3, 14)

    assert outcome.ok and outcome.code == "A1B2C3D4E5F6A7B8C9"
    assert service["client"].calls == [
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
    session, service, note: str, uses: int, days: int
) -> None:
    admin_service.unlock(PASSKEY)
    assert not admin_service.create_teacher_invite(note, uses, days).ok
    assert service["client"].calls == []


def test_database_messages_are_shown_only_when_deliberate(session, service) -> None:
    admin_service.unlock(PASSKEY)
    service["client"].responses.update(
        {
            "admin_demote_teacher": RuntimeError(
                "{'code': 'P0001', 'message': 'That account is not a teacher.'}"
            ),
            "admin_cancel_teacher_invite": RuntimeError(
                'duplicate key value violates unique constraint "teacher_invites_pkey"'
            ),
            "admin_list_teachers": RuntimeError(
                "Could not find the function public.admin_list_teachers"
            ),
        }
    )

    assert admin_service.demote_teacher("usr_s01", False).message == "That account is not a teacher."
    leaked = admin_service.cancel_teacher_invite(1).message
    assert leaked == admin_service.GENERIC_MESSAGE and "pkey" not in leaked
    _, error = admin_service.list_teachers()
    assert error == admin_service.NOT_SET_UP_MESSAGE


def test_a_failing_service_client_never_echoes_its_settings(
    monkeypatch: pytest.MonkeyPatch, session
) -> None:
    admin_service.unlock(PASSKEY)

    def broken() -> Any:
        raise RuntimeError("bad key service-key for https://example.supabase.co")

    monkeypatch.setattr(admin_service, "_new_service_client", broken)
    outcome = admin_service.create_teacher_invite("x", 1, 7)
    assert outcome.message == admin_service.GENERIC_MESSAGE


def test_invite_rows_are_parsed_and_given_a_status(session, service) -> None:
    admin_service.unlock(PASSKEY)
    service["client"].responses["admin_list_teacher_invites"] = [
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

    rows, error = admin_service.list_teacher_invites()

    assert error is None
    assert [r.status() for r in rows] == ["Active", "Used up", "Expired"]
    assert rows[1].note == ""


def test_demote_sends_the_profile_and_the_release_choice(session, service) -> None:
    admin_service.unlock(PASSKEY)
    assert admin_service.demote_teacher("usr_t9", False).ok
    assert service["client"].calls == [
        ("admin_demote_teacher", {"p_profile_id": "usr_t9", "p_release_students": False})
    ]


def test_nothing_outside_admin_imports_the_service_client() -> None:
    """The service-role key must only be reachable from the Admin page."""
    offenders = []
    for path in list((ROOT / "services").glob("*.py")) + list((ROOT / "views").glob("*.py")) + [
        ROOT / "app.py"
    ] + list((ROOT / "components").glob("*.py")):
        if path.name in {"admin_service.py", "admin.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(
            r"from services import[^\n]*\badmin_service\b"
            r"|import services\.admin_service|from services\.admin_service"
            r"|[\"']SUPABASE_SERVICE_ROLE_KEY[\"']",
            text,
        ):
            offenders.append(path.name)
    assert offenders == []


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role", [Role.STUDENT, Role.TEACHER])
@pytest.mark.parametrize("signed_in", [True, False, None])
def test_admin_is_registered_for_everybody_but_hidden(role: Role, signed_in) -> None:
    from components.navigation import pages_for

    [spec] = [s for s in pages_for(role, signed_in) if s["path"] == "views/admin.py"]
    assert spec["hidden"] is True and spec["without_account"] is True


def test_the_sign_in_form_does_not_link_to_admin() -> None:
    """BUG-016: /admin is shared privately, not advertised under the public form.

    This replaces `test_the_sign_in_form_links_to_admin` (20 Nov), which asserted
    the opposite; house rules: /admin is unlinked.
    """
    source = (ROOT / "components" / "auth_forms.py").read_text(encoding="utf-8")
    assert "page_link" not in source
    assert "views/admin" not in source and "Admin access" not in source


def test_admin_opens_from_the_welcome_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an account /admin shows the passkey form, not the landing page."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert "Explore the demo" in [b.label for b in at.button]
    at.switch_page("views/admin.py")
    at.run()
    assert not at.exception, at.exception
    assert "Unlock" in [b.label for b in at.button]
    assert "Explore the demo" not in [b.label for b in at.button]


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------
def _admin_page(monkeypatch: pytest.MonkeyPatch, unlocked: bool):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(admin_service, "is_unlocked", lambda: unlocked)
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
        lambda: ([admin_service.TeacherRow("usr_t02", "Ms Rao", 12)], None),
    )
    at = AppTest.from_file(ADMIN_PAGE, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def test_a_locked_page_asks_for_the_passkey_and_shows_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = _admin_page(monkeypatch, unlocked=False)
    labels = [b.label for b in at.button]
    assert labels == ["Unlock"]
    [field] = at.text_input
    assert field.label == "Admin passkey"
    assert len(at.dataframe) == 0


def test_the_passkey_box_has_no_length_limit_and_a_long_passkey_unlocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ARY-001, decided 27 Nov: the passkey has no length rules. The box has no
    max_chars, so it shows no count (it said "10/256", telling an onlooker the
    length), and nothing is cut off: a 300-character passkey typed in full
    unlocks the page. AppTest ignores input longer than max_chars, as a browser
    does, so this fails if either limit comes back."""
    from streamlit.testing.v1 import AppTest

    long_passkey = "passkey-10" * 30
    monkeypatch.setenv("ADMIN_PASSKEY", long_passkey)
    monkeypatch.setattr(admin_service, "list_teacher_invites", lambda: ([], None))
    monkeypatch.setattr(admin_service, "list_teachers", lambda: ([], None))
    at = AppTest.from_file(ADMIN_PAGE, default_timeout=60)
    at.run()
    [field] = at.text_input
    assert not field.max_chars

    field.input(long_passkey)
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert "Lock admin" in [b.label for b in at.button]


@pytest.mark.parametrize("missing", ["ADMIN_PASSKEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"])
def test_the_page_shows_a_setup_problem_instead_of_the_form(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    """BUG-016: every visitor sees the same neutral sentence; the detail is logged."""
    monkeypatch.delenv(missing)
    at = _admin_page(monkeypatch, unlocked=False)
    assert [e.value for e in at.error] == ["Admin is not available."]
    page_text = " ".join(
        [e.value for e in at.error] + [m.value for m in at.markdown] + [c.value for c in at.caption]
    )
    assert "ADMIN_PASSKEY" not in page_text and "SUPABASE" not in page_text
    assert "Unlock" not in [b.label for b in at.button]


def test_an_unlocked_page_renders_the_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    at = _admin_page(monkeypatch, unlocked=True)
    labels = [b.label for b in at.button]
    for wanted in (
        "Lock admin", "Create teacher account", "Create code", "Cancel code",
        "Remove teacher access",
    ):
        assert wanted in labels
    [teacher] = [s for s in at.selectbox if s.label == "Teacher"]
    assert teacher.options == ["Ms Rao (usr_t02)"]


TEACHER_BOXES = {
    "admin_teacher_name": "Ms Rao",
    "admin_teacher_email": "rao@school.org",
    "admin_teacher_password": "secret123",
}


def _fill_teacher_form(at) -> None:
    for key, value in TEACHER_BOXES.items():
        at.text_input(key=key).input(value)


def test_a_failed_add_a_teacher_keeps_what_was_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    """BUG-011: an error must not wipe the name, email and password."""
    at = _admin_page(monkeypatch, unlocked=True)
    seen: List[tuple] = []

    def refuse(name: str, email: str, password: str) -> admin_service.AdminOutcome:
        seen.append((name, email, password))
        return admin_service.AdminOutcome(
            False, "The temporary password must be at least 8 characters."
        )

    monkeypatch.setattr(admin_service, "create_teacher", refuse)
    _fill_teacher_form(at)
    next(b for b in at.button if b.label == "Create teacher account").click().run()

    assert not at.exception, at.exception
    assert seen == [("Ms Rao", "rao@school.org", "secret123")]
    assert any("at least 8 characters" in e.value for e in at.error)
    for key, value in TEACHER_BOXES.items():
        assert at.text_input(key=key).value == value


def test_a_successful_add_a_teacher_empties_the_form(monkeypatch: pytest.MonkeyPatch) -> None:
    at = _admin_page(monkeypatch, unlocked=True)
    monkeypatch.setattr(
        admin_service,
        "create_teacher",
        lambda name, email, password: admin_service.AdminOutcome(
            True, "Teacher account created for Ms Rao."
        ),
    )
    _fill_teacher_form(at)
    next(b for b in at.button if b.label == "Create teacher account").click().run()

    assert not at.exception, at.exception
    assert any("Teacher account created" in s.value for s in at.success)
    for key in TEACHER_BOXES:
        assert at.text_input(key=key).value == ""


def test_the_password_box_is_labelled_temporary(monkeypatch: pytest.MonkeyPatch) -> None:
    at = _admin_page(monkeypatch, unlocked=True)
    assert at.text_input(key="admin_teacher_password").label == "Temporary password"
    assert at.text_input(key="admin_teacher_password").proto.type == TextInputProto.PASSWORD


def test_a_new_code_is_shown_once(monkeypatch: pytest.MonkeyPatch) -> None:
    at = _admin_page(monkeypatch, unlocked=True)
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
    """The executable part of 011, without comments or the operator notes."""
    text = MIGRATION.read_text(encoding="utf-8")
    lines = [line.split("--", 1)[0] for line in text.splitlines()]
    return "\n".join(lines).lower()


def _functions(sql: str) -> Dict[str, str]:
    bodies = re.findall(
        r"create or replace function public\.(\w+)\((.*?)\$fn\$(.*?)\$fn\$", sql, re.S
    )
    return {name: body for name, _, body in bodies}


ADMIN_FUNCTIONS = {
    "admin_create_teacher_invite",
    "admin_list_teacher_invites",
    "admin_cancel_teacher_invite",
    "admin_list_teachers",
    "admin_demote_teacher",
}


def test_every_admin_function_opens_with_the_guard() -> None:
    functions = _functions(_migration_sql())
    assert {n for n in functions if n.startswith("admin_")} == ADMIN_FUNCTIONS
    for name in ADMIN_FUNCTIONS:
        assert "perform public.app_require_admin();" in functions[name], name


def test_the_guard_checks_the_service_role_claim() -> None:
    guard = _functions(_migration_sql())["app_require_admin"]
    assert "request.jwt.claims" in guard and "'service_role'" in guard
    assert "raise exception 'admin access required.'" in guard


def test_only_service_role_can_run_the_admin_functions() -> None:
    sql = _migration_sql()
    grants = re.findall(r"grant execute on function public\.(\w+)\([^)]*\) to (\w+);", sql)
    assert grants and all(role == "service_role" for _, role in grants)
    assert {name for name, _ in grants} == ADMIN_FUNCTIONS
    for name in ADMIN_FUNCTIONS | {"app_require_admin"}:
        assert re.search(
            rf"revoke all on function public\.{name}\([^)]*\) from public, anon, authenticated;",
            sql,
        ), name
    assert "grant execute on function public.app_require_admin" not in sql


def test_the_account_based_admin_from_010_is_dropped() -> None:
    sql = _migration_sql()
    assert "drop table if exists public.app_admins;" in sql
    assert "drop function if exists public.is_app_admin();" in sql


def test_no_email_and_no_code_hash_leave_the_database() -> None:
    sql = _migration_sql()
    assert "code_hash" not in _functions(sql)["admin_list_teacher_invites"]
    assert "email" not in sql and "auth.users" not in sql


def test_setup_all_includes_011() -> None:
    setup = (ROOT / "db" / "setup_all.sql").read_text(encoding="utf-8")
    assert "-- Source: db/migrations/011_admin_passkey.sql" in setup
    assert "('app_admins')" not in setup
