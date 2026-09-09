"""Tests for authentication and backend selection.

WHAT THESE COVER
  The decisions that would be dangerous to get wrong: who the app thinks you
  are, whether a role can be self-declared, and whether one person's signed-in
  client can end up serving somebody else.

WHAT THEY DO NOT COVER
  Supabase Auth itself. `FakeAuthClient` stands in for gotrue, so these assert
  how the application responds to sign-in succeeding or failing - not that the
  real service behaves as modelled. The trigger in
  db/migrations/002_auth_profiles.sql is likewise unexercised until there is an
  integration test signed in against a live project.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from models import Role, User
from services import auth_service
from services.repository import SessionRepository, SupabaseRepository


# --------------------------------------------------------------------------
# A stand-in for the Supabase client's auth surface
# --------------------------------------------------------------------------
class _AuthUser:
    def __init__(self, user_id: str) -> None:
        self.id = user_id


class _AuthUserResponse:
    def __init__(self, user: Optional[_AuthUser]) -> None:
        self.user = user


class _SignUpResponse:
    def __init__(self, session: Optional[object]) -> None:
        self.session = session


class _FakeAuth:
    def __init__(self, owner: "FakeAuthClient") -> None:
        self._owner = owner

    def get_session(self) -> Optional[object]:
        return self._owner.session

    def get_user(self) -> _AuthUserResponse:
        if self._owner.session is None:
            return _AuthUserResponse(None)
        return _AuthUserResponse(_AuthUser(self._owner.auth_user_id))

    def sign_in_with_password(self, credentials: Dict[str, str]) -> None:
        if credentials["email"] not in self._owner.accounts:
            raise RuntimeError("Invalid login credentials")
        if self._owner.accounts[credentials["email"]] != credentials["password"]:
            raise RuntimeError("Invalid login credentials")
        self._owner.session = object()

    def sign_up(self, credentials: Dict[str, str]) -> _SignUpResponse:
        if credentials["email"] in self._owner.accounts:
            raise RuntimeError("User already registered")
        self._owner.accounts[credentials["email"]] = credentials["password"]
        if self._owner.confirm_by_email:
            return _SignUpResponse(None)
        self._owner.session = object()
        return _SignUpResponse(object())

    def sign_out(self) -> None:
        self._owner.session = None


class _Table:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows
        self._filters: List[Any] = []

    def select(self, *_columns: str) -> "_Table":
        return self

    def eq(self, column: str, value: Any) -> "_Table":
        self._filters.append((column, value))
        return self

    def execute(self) -> Any:
        rows = [
            row
            for row in self._rows
            if all(row.get(c) == v for c, v in self._filters)
        ]

        class _R:
            data = rows

        return _R()


class FakeAuthClient:
    """Enough of a Supabase client to exercise auth_service."""

    def __init__(
        self,
        accounts: Optional[Dict[str, str]] = None,
        profiles: Optional[List[Dict[str, Any]]] = None,
        confirm_by_email: bool = False,
    ) -> None:
        self.accounts = dict(accounts or {})
        self.profiles = list(profiles or [])
        self.session: Optional[object] = None
        self.auth_user_id = "auth-uuid-1"
        self.confirm_by_email = confirm_by_email
        self.auth = _FakeAuth(self)

    def table(self, name: str) -> _Table:
        assert name == "profiles", f"unexpected table {name}"
        return _Table(self.profiles)


STUDENT_PROFILE = {
    "id": "usr_s01",
    "auth_user_id": "auth-uuid-1",
    "display_name": "S-1101",
    "role": "student",
    "teacher_id": "usr_t1",
    "year_group": 10,
}


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch):
    """Give each test a clean session and forget any forced repository."""
    import services.repository as repository_module

    repository_module.set_repository(None)
    yield
    repository_module.set_repository(None)


def _install(monkeypatch: pytest.MonkeyPatch, client: FakeAuthClient) -> None:
    """Point auth_service at a fake client and an in-memory session store."""
    session: Dict[str, Any] = {}

    class _SessionState:
        def __contains__(self, key: str) -> bool:
            return key in session

        def __setitem__(self, key: str, value: Any) -> None:
            session[key] = value

        def __getitem__(self, key: str) -> Any:
            return session[key]

        def get(self, key: str, default: Any = None) -> Any:
            return session.get(key, default)

        def pop(self, key: str, default: Any = None) -> Any:
            return session.pop(key, default)

    monkeypatch.setattr(auth_service.st, "session_state", _SessionState())
    monkeypatch.setattr(auth_service, "_new_client", lambda: client)


# --------------------------------------------------------------------------
# Signing in
# --------------------------------------------------------------------------
def test_sign_in_with_good_credentials_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeAuthClient(
        accounts={"a@example.com": "hunter22"}, profiles=[STUDENT_PROFILE]
    )
    _install(monkeypatch, client)

    outcome = auth_service.sign_in("a@example.com", "hunter22")

    assert outcome.ok is True
    assert auth_service.is_signed_in() is True
    user = auth_service.current_user()
    assert user is not None
    assert user.display_name == "S-1101"
    assert user.role is Role.STUDENT


def test_wrong_password_does_not_sign_anyone_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeAuthClient(
        accounts={"a@example.com": "hunter22"}, profiles=[STUDENT_PROFILE]
    )
    _install(monkeypatch, client)

    outcome = auth_service.sign_in("a@example.com", "wrong")

    assert outcome.ok is False
    assert auth_service.is_signed_in() is False
    assert auth_service.current_user() is None


def test_failure_message_does_not_reveal_whether_the_account_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telling a visitor which emails have accounts is a disclosure."""
    client = FakeAuthClient(accounts={"a@example.com": "hunter22"})
    _install(monkeypatch, client)

    wrong_password = auth_service.sign_in("a@example.com", "nope")
    no_such_account = auth_service.sign_in("nobody@example.com", "nope")

    assert wrong_password.message == no_such_account.message


def test_sign_in_without_a_profile_is_reported_not_silently_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing profile means the sign-up trigger is not installed.

    Left unreported, every page would render empty and look like a data bug.
    """
    client = FakeAuthClient(accounts={"a@example.com": "hunter22"}, profiles=[])
    _install(monkeypatch, client)

    outcome = auth_service.sign_in("a@example.com", "hunter22")

    assert outcome.ok is False
    assert "002_auth_profiles.sql" in outcome.message


def test_sign_out_clears_the_session_and_the_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeAuthClient(
        accounts={"a@example.com": "hunter22"}, profiles=[STUDENT_PROFILE]
    )
    _install(monkeypatch, client)
    auth_service.sign_in("a@example.com", "hunter22")

    auth_service.sign_out()

    assert auth_service.is_signed_in() is False
    assert auth_service.current_user() is None


# --------------------------------------------------------------------------
# Signing up
# --------------------------------------------------------------------------
def test_sign_up_sends_no_role_and_no_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The role is assigned by the database trigger, never by the client.

    If a role ever reached Supabase from here, a person could sign up as a
    teacher and read the whole class.
    """
    sent: Dict[str, Any] = {}

    class _RecordingClient(FakeAuthClient):
        def __init__(self) -> None:
            super().__init__()
            outer = self

            class _RecordingAuth(_FakeAuth):
                def sign_up(self, credentials: Dict[str, str]) -> _SignUpResponse:
                    sent.update(credentials)
                    return super().sign_up(credentials)

            self.auth = _RecordingAuth(outer)

    client = _RecordingClient()
    _install(monkeypatch, client)

    auth_service.sign_up("new@example.com", "hunter22")

    assert set(sent) == {"email", "password"}
    assert "role" not in sent
    assert "data" not in sent
    assert "display_name" not in sent


def test_sign_up_needing_confirmation_is_reported_as_such(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeAuthClient(confirm_by_email=True)
    _install(monkeypatch, client)

    outcome = auth_service.sign_up("new@example.com", "hunter22")

    assert outcome.ok is True
    assert outcome.needs_confirmation is True
    assert auth_service.is_signed_in() is False


def test_duplicate_sign_up_is_reported_readably(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeAuthClient(accounts={"a@example.com": "hunter22"})
    _install(monkeypatch, client)

    outcome = auth_service.sign_up("a@example.com", "hunter22")

    assert outcome.ok is False
    assert "already exists" in outcome.message


# --------------------------------------------------------------------------
# The role cannot be self-declared
# --------------------------------------------------------------------------
def test_role_comes_from_the_profile_row_not_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    teacher_profile = dict(STUDENT_PROFILE, role="teacher", teacher_id=None)
    client = FakeAuthClient(
        accounts={"t@example.com": "hunter22"}, profiles=[teacher_profile]
    )
    _install(monkeypatch, client)
    auth_service.sign_in("t@example.com", "hunter22")

    assert auth_service.current_role() is Role.TEACHER


def test_a_signed_in_profile_overrides_the_demo_identity_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dropdown must not be able to promote a signed-in student.

    services.state.get_current_user asks auth first, so selecting the teacher
    from the demo switcher cannot change who you are once you have signed in.
    """
    client = FakeAuthClient(
        accounts={"a@example.com": "hunter22"}, profiles=[STUDENT_PROFILE]
    )
    _install(monkeypatch, client)
    auth_service.sign_in("a@example.com", "hunter22")

    import services.state as state_module

    monkeypatch.setattr(
        state_module.st, "session_state", {"current_user_id": "usr_teacher01"}
    )
    monkeypatch.setattr(
        state_module,
        "get_users",
        lambda: [
            User(id="usr_teacher01", display_name="Ms Rao", role=Role.TEACHER)
        ],
    )

    assert state_module.get_current_user().role is Role.STUDENT


# --------------------------------------------------------------------------
# Backend selection
# --------------------------------------------------------------------------
def test_backend_is_session_state_until_someone_signs_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeAuthClient(
        accounts={"a@example.com": "hunter22"}, profiles=[STUDENT_PROFILE]
    )
    _install(monkeypatch, client)
    import services.repository as repository_module

    assert isinstance(repository_module.get_repository(), SessionRepository)

    auth_service.sign_in("a@example.com", "hunter22")

    assert isinstance(repository_module.get_repository(), SupabaseRepository)


def test_signing_out_returns_the_app_to_sample_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeAuthClient(
        accounts={"a@example.com": "hunter22"}, profiles=[STUDENT_PROFILE]
    )
    _install(monkeypatch, client)
    import services.repository as repository_module

    auth_service.sign_in("a@example.com", "hunter22")
    auth_service.sign_out()

    assert isinstance(repository_module.get_repository(), SessionRepository)


def test_the_sign_in_page_renders_and_offers_no_role_choice() -> None:
    """The form must never grow a "sign up as a teacher" control.

    Rendering the page is the cheap half; the assertion that matters is the
    absence of any widget offering a role. A selector here would let anybody
    claim the teacher role, and every read policy downstream would believe it.
    """
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    page = str(Path(__file__).resolve().parent.parent / "pages" / "sign_in.py")
    at = AppTest.from_file(page, default_timeout=60)
    at.run()

    assert not at.exception, at.exception
    assert [t.value for t in at.title] == ["Sign in to AssessAI"]
    assert [b.label for b in at.button] == ["Sign in", "Create account"]

    labels = " ".join(
        [w.label or "" for w in at.selectbox]
        + [w.label or "" for w in at.radio]
        + [w.label or "" for w in at.text_input]
    ).lower()
    assert "role" not in labels
    assert "teacher" not in labels


def test_the_backend_is_not_cached_across_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One process serves every browser, so caching this would leak a client.

    If `get_repository` memoised at module level, the second person to sign in
    would be handed the first person's authenticated client - and read their
    rows. This asserts the answer is recomputed rather than remembered.
    """
    client = FakeAuthClient(
        accounts={"a@example.com": "hunter22"}, profiles=[STUDENT_PROFILE]
    )
    _install(monkeypatch, client)
    import services.repository as repository_module

    first = repository_module.get_repository()
    auth_service.sign_in("a@example.com", "hunter22")
    second = repository_module.get_repository()

    assert isinstance(first, SessionRepository)
    assert isinstance(second, SupabaseRepository)
    assert first is not second
