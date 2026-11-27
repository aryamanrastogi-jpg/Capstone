"""Changing your own password, and the forced change for admin-created teachers (ARY-002 / BUG-002).

WHAT THESE COVER
  * `must_change_password()` reads the flag the admin's create_user call sets.
  * `choose_password()` (first sign-in) saves the password and clears the flag
    in the one request, and signs the account's other sessions out.
  * `change_password()` (Profile) checks the current password first, on a
    throwaway client, and counts a wrong one like a failed sign-in.
  * Nothing typed ever comes back in a message, and a raw library error is
    summarised.
  * app.py shows only the choose-a-password page while the flag is set.
  * Profile offers the change form and keeps what was typed when it fails.

WHAT THEY DO NOT COVER
  Supabase Auth itself: `_Client` stands in for gotrue, so these assert how
  the application behaves around it, not that the real service accepts the
  calls. The emailed "forgot password" route is not built (it needs an email
  provider and Auth settings that are not set up).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from streamlit.proto.TextInput_pb2 import TextInput as TextInputProto
from streamlit.testing.v1 import AppTest

from models import Role, User
from services import auth_service

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
PROFILE_PAGE = str(ROOT / "views" / "profile.py")

EMAIL = "rao@school.org"
OLD = "Temporary1"
NEW = "BrandNew42"


# --------------------------------------------------------------------------
# A stand-in for the Supabase client's auth surface
# --------------------------------------------------------------------------
class _Auth:
    def __init__(self, owner: "_Client") -> None:
        self._owner = owner

    def get_session(self) -> Optional[Any]:
        return self._owner.session

    def get_user(self) -> Optional[Any]:
        if self._owner.session is None:
            return None
        return SimpleNamespace(user=self._owner.user)

    def sign_in_with_password(self, credentials: Dict[str, str]) -> None:
        if self._owner.accounts.get(credentials["email"]) != credentials["password"]:
            raise RuntimeError("Invalid login credentials")
        self._owner.session = SimpleNamespace(user=self._owner.user)

    def update_user(self, attributes: Dict[str, Any]) -> Any:
        self._owner.updates.append(attributes)
        if self._owner.update_error is not None:
            raise self._owner.update_error
        if "password" in attributes:
            self._owner.accounts[self._owner.user.email] = attributes["password"]
        self._owner.user.user_metadata.update(attributes.get("data", {}))
        return SimpleNamespace(user=self._owner.user)

    def sign_out(self, options: Optional[Dict[str, str]] = None) -> None:
        self._owner.sign_outs.append(options)
        if (options or {}).get("scope", "global") != "others":
            self._owner.session = None


class _Client:
    def __init__(
        self,
        accounts: Dict[str, str],
        metadata: Optional[Dict[str, Any]] = None,
        signed_in: bool = True,
        update_error: Optional[Exception] = None,
    ) -> None:
        self.accounts = accounts
        self.user = SimpleNamespace(
            id="auth-uuid-1", email=EMAIL, user_metadata=dict(metadata or {})
        )
        self.session: Optional[Any] = SimpleNamespace(user=self.user) if signed_in else None
        self.update_error = update_error
        self.updates: List[Dict[str, Any]] = []
        self.sign_outs: List[Optional[Dict[str, str]]] = []
        self.auth = _Auth(self)


@pytest.fixture
def accounts(monkeypatch: pytest.MonkeyPatch) -> Dict[str, str]:
    """The one account, and a private stand-in for the browser session's state.

    Outside a Streamlit run `st.session_state` is one shared bare state, so a
    lockout recorded by one test would otherwise still be there for the next.
    """
    monkeypatch.setattr(auth_service.st, "session_state", {})
    return {EMAIL: OLD}


@pytest.fixture
def signed_in(monkeypatch: pytest.MonkeyPatch, accounts: Dict[str, str]) -> _Client:
    """A signed-in session, plus a separate throwaway client for the password check."""
    client = _Client(accounts, metadata={"full_name": "Ms Rao", "must_change_password": True})
    throwaway: List[_Client] = []

    def new_client() -> _Client:
        fresh = _Client(accounts, signed_in=False)
        throwaway.append(fresh)
        return fresh

    monkeypatch.setattr(auth_service, "session_client", lambda: client)
    monkeypatch.setattr(auth_service, "_new_client", new_client)
    client.throwaway = throwaway  # type: ignore[attr-defined]
    return client


# --------------------------------------------------------------------------
# The flag
# --------------------------------------------------------------------------
def test_the_flag_is_read_from_the_signed_in_session(signed_in: _Client) -> None:
    assert auth_service.must_change_password() is True
    signed_in.user.user_metadata["must_change_password"] = False
    assert auth_service.must_change_password() is False


def test_an_ordinary_account_is_never_forced(
    monkeypatch: pytest.MonkeyPatch, accounts: Dict[str, str]
) -> None:
    client = _Client(accounts, metadata={"full_name": "Ms Rao"})
    monkeypatch.setattr(auth_service, "session_client", lambda: client)
    assert auth_service.must_change_password() is False


def test_nobody_signed_in_is_not_forced(
    monkeypatch: pytest.MonkeyPatch, accounts: Dict[str, str]
) -> None:
    client = _Client(accounts, metadata={"must_change_password": True}, signed_in=False)
    monkeypatch.setattr(auth_service, "session_client", lambda: client)
    assert auth_service.must_change_password() is False


def test_no_supabase_means_no_forced_change(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_service, "session_client", lambda: None)
    assert auth_service.must_change_password() is False


# --------------------------------------------------------------------------
# Choosing your own password at first sign-in
# --------------------------------------------------------------------------
def test_choosing_a_password_saves_it_and_clears_the_flag_in_one_request(
    signed_in: _Client,
) -> None:
    outcome = auth_service.choose_password(NEW)
    assert outcome.ok, outcome.message
    assert signed_in.updates == [{"password": NEW, "data": {"must_change_password": False}}]
    assert auth_service.must_change_password() is False
    assert signed_in.accounts[EMAIL] == NEW


def test_choosing_a_password_signs_the_other_sessions_out(signed_in: _Client) -> None:
    """Whoever was given the temporary password must not stay signed in."""
    assert auth_service.choose_password(NEW).ok
    assert signed_in.sign_outs == [{"scope": "others"}]
    assert signed_in.session is not None, "this session stays signed in"


@pytest.mark.parametrize(
    "bad, wanted",
    [("short1", "at least 8"), ("lettersonly", "number"), ("12345678", "letter"), ("x" * 129, "at most")],
)
def test_a_weak_password_never_reaches_supabase(
    signed_in: _Client, bad: str, wanted: str
) -> None:
    outcome = auth_service.choose_password(bad)
    assert not outcome.ok and wanted in outcome.message
    assert signed_in.updates == []


def test_choosing_a_password_needs_a_signed_in_user(
    monkeypatch: pytest.MonkeyPatch, accounts: Dict[str, str]
) -> None:
    client = _Client(accounts, signed_in=False)
    monkeypatch.setattr(auth_service, "session_client", lambda: client)
    outcome = auth_service.choose_password(NEW)
    assert not outcome.ok and outcome.message == "Sign in first."
    assert client.updates == []


# --------------------------------------------------------------------------
# Changing it from Profile
# --------------------------------------------------------------------------
def test_a_wrong_current_password_changes_nothing(signed_in: _Client) -> None:
    outcome = auth_service.change_password("Not-the-one1", NEW)
    assert not outcome.ok and "current password" in outcome.message.lower()
    assert signed_in.updates == []
    assert signed_in.sign_outs == []


def test_the_right_current_password_lets_the_change_through(signed_in: _Client) -> None:
    outcome = auth_service.change_password(OLD, NEW)
    assert outcome.ok, outcome.message
    assert signed_in.updates == [{"password": NEW, "data": {"must_change_password": False}}]
    assert signed_in.sign_outs == [{"scope": "others"}]


def test_a_change_does_not_touch_the_flag_when_there_is_none(
    monkeypatch: pytest.MonkeyPatch, accounts: Dict[str, str]
) -> None:
    client = _Client(accounts, metadata={"full_name": "Ms Rao"})
    monkeypatch.setattr(auth_service, "session_client", lambda: client)
    monkeypatch.setattr(auth_service, "_new_client", lambda: _Client(accounts, signed_in=False))
    assert auth_service.change_password(OLD, NEW).ok
    assert client.updates == [{"password": NEW}]


def test_the_current_password_is_checked_on_a_throwaway_session(signed_in: _Client) -> None:
    """Checking must never replace, or sign out, the session the person is using."""
    assert auth_service.change_password(OLD, NEW).ok
    [fresh] = signed_in.throwaway  # type: ignore[attr-defined]
    assert fresh.sign_outs == [{"scope": "local"}], "only the throwaway session may be ended"
    assert signed_in.session is not None


def test_the_new_password_must_differ_from_the_current_one(signed_in: _Client) -> None:
    outcome = auth_service.change_password(OLD, OLD)
    assert not outcome.ok and "different" in outcome.message
    assert signed_in.updates == []


def test_wrong_current_passwords_lock_the_form_like_failed_sign_ins(
    signed_in: _Client,
) -> None:
    for _ in range(auth_service.MAX_FAILED_SIGN_INS):
        assert not auth_service.change_password("Nope-nope-1", NEW).ok
    outcome = auth_service.change_password(OLD, NEW)  # even the right one is refused now
    assert not outcome.ok and "Too many" in outcome.message
    assert signed_in.updates == []


def test_a_successful_change_resets_the_failure_count(signed_in: _Client) -> None:
    for _ in range(auth_service.MAX_FAILED_SIGN_INS - 1):
        auth_service.change_password("Nope-nope-1", NEW)
    assert auth_service.change_password(OLD, NEW).ok
    assert auth_service.sign_in_locked_for(EMAIL) == 0


def test_the_form_needs_a_signed_in_user(
    monkeypatch: pytest.MonkeyPatch, accounts: Dict[str, str]
) -> None:
    client = _Client(accounts, signed_in=False)
    monkeypatch.setattr(auth_service, "session_client", lambda: client)
    outcome = auth_service.change_password(OLD, NEW)
    assert not outcome.ok and outcome.message == "Sign in first."


def test_an_over_long_current_password_is_just_wrong(signed_in: _Client) -> None:
    outcome = auth_service.change_password("x" * 500, NEW)
    assert not outcome.ok
    assert signed_in.updates == []


# --------------------------------------------------------------------------
# What is said back
# --------------------------------------------------------------------------
@pytest.mark.parametrize("action", ["choose", "change"])
def test_no_message_repeats_a_password_or_the_raw_error(
    monkeypatch: pytest.MonkeyPatch, accounts: Dict[str, str], action: str
) -> None:
    raw = RuntimeError(f"500 from https://x.supabase.co for {EMAIL} password {NEW} {OLD}")
    client = _Client(accounts, metadata={"must_change_password": True}, update_error=raw)
    monkeypatch.setattr(auth_service, "session_client", lambda: client)
    monkeypatch.setattr(auth_service, "_new_client", lambda: _Client(accounts, signed_in=False))
    outcome = (
        auth_service.choose_password(NEW)
        if action == "choose"
        else auth_service.change_password(OLD, NEW)
    )
    assert not outcome.ok
    for secret in (NEW, OLD, EMAIL, "supabase.co", "500"):
        assert secret not in outcome.message


def test_a_session_that_needs_a_fresh_sign_in_gets_a_plain_instruction(
    monkeypatch: pytest.MonkeyPatch, accounts: Dict[str, str]
) -> None:
    error = RuntimeError("Password update requires reauthentication")
    client = _Client(accounts, update_error=error)
    monkeypatch.setattr(auth_service, "session_client", lambda: client)
    monkeypatch.setattr(auth_service, "_new_client", lambda: _Client(accounts, signed_in=False))
    outcome = auth_service.change_password(OLD, NEW)
    assert not outcome.ok and "sign in again" in outcome.message.lower()


def test_supabase_refusing_a_repeated_password_is_explained(
    monkeypatch: pytest.MonkeyPatch, accounts: Dict[str, str]
) -> None:
    error = RuntimeError("New password should be different from the old password.")
    client = _Client(accounts, update_error=error)
    monkeypatch.setattr(auth_service, "session_client", lambda: client)
    outcome = auth_service.choose_password(NEW)
    assert not outcome.ok and "different" in outcome.message


# --------------------------------------------------------------------------
# The admin side sets the flag
# --------------------------------------------------------------------------
def test_an_admin_created_teacher_is_flagged_to_change_the_password() -> None:
    from services import admin_service

    assert admin_service.FORCE_PASSWORD_CHANGE_KEY == auth_service.FORCE_PASSWORD_CHANGE_KEY
    assert auth_service.FORCE_PASSWORD_CHANGE_KEY == "must_change_password"


# --------------------------------------------------------------------------
# app.py: only the choose-a-password page while the flag is set
# --------------------------------------------------------------------------
TEACHER = User(id="usr_t99", display_name="Ms Rao", role=Role.TEACHER)


@pytest.fixture
def forced_teacher(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    state: Dict[str, Any] = {"forced": True, "saved": []}

    def choose(new_password: str) -> auth_service.AuthOutcome:
        state["saved"].append(new_password)
        state["forced"] = False
        return auth_service.AuthOutcome(True, "Password saved.")

    monkeypatch.setattr(auth_service, "current_user", lambda: TEACHER)
    monkeypatch.setattr(auth_service, "is_signed_in", lambda: True)
    monkeypatch.setattr(auth_service, "current_email", lambda: EMAIL)
    monkeypatch.setattr(auth_service, "must_change_password", lambda: state["forced"])
    monkeypatch.setattr(auth_service, "choose_password", choose)
    return state


def test_a_flagged_account_sees_only_the_choose_a_password_page(
    forced_teacher: Dict[str, Any],
) -> None:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception
    assert [t.label for t in at.text_input] == ["New password", "Confirm new password"]
    assert "Save password" in [b.label for b in at.button]
    assert "Sign out" in [b.label for b in at.button]
    assert not at.sidebar.button, "no menu, no feedback button: nowhere else to go"
    page_text = " ".join(m.value for m in at.markdown)
    assert "Choose your password" in page_text
    assert "Class Overview" not in page_text


def test_mismatched_passwords_are_refused_and_nothing_is_saved(
    forced_teacher: Dict[str, Any],
) -> None:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    at.text_input[0].input(NEW)
    at.text_input[1].input(NEW + "x")
    next(b for b in at.button if b.label == "Save password").click().run()
    assert not at.exception, at.exception
    assert any("do not match" in e.value for e in at.error)
    assert forced_teacher["saved"] == []


def test_a_blank_form_is_refused(forced_teacher: Dict[str, Any]) -> None:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    next(b for b in at.button if b.label == "Save password").click().run()
    assert at.error and forced_teacher["saved"] == []


def test_saving_a_password_opens_the_app(forced_teacher: Dict[str, Any]) -> None:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    at.text_input[0].input(NEW)
    at.text_input[1].input(NEW)
    next(b for b in at.button if b.label == "Save password").click().run()
    assert not at.exception, at.exception
    assert forced_teacher["saved"] == [NEW]
    assert "Save password" not in [b.label for b in at.button]
    assert "Class Overview" in " ".join(m.value for m in at.markdown)


def test_an_unflagged_account_never_sees_the_page(
    forced_teacher: Dict[str, Any],
) -> None:
    forced_teacher["forced"] = False
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception
    assert "Save password" not in [b.label for b in at.button]
    assert "Class Overview" in " ".join(m.value for m in at.markdown)


# --------------------------------------------------------------------------
# Profile: change it any time
# --------------------------------------------------------------------------
@pytest.fixture
def profile_calls(monkeypatch: pytest.MonkeyPatch) -> List[tuple]:
    calls: List[tuple] = []

    def change(current: str, new: str) -> auth_service.AuthOutcome:
        calls.append((current, new))
        if current != OLD:
            return auth_service.AuthOutcome(False, "Your current password is not right.")
        return auth_service.AuthOutcome(True, "Password changed.")

    monkeypatch.setattr(auth_service, "current_user", lambda: TEACHER)
    monkeypatch.setattr(auth_service, "current_email", lambda: EMAIL)
    monkeypatch.setattr(auth_service, "change_password", change)
    return calls


def _profile() -> AppTest:
    at = AppTest.from_file(PROFILE_PAGE, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def _fill(at: AppTest, current: str, new: str, confirm: str) -> None:
    at.text_input(key="change_password_current").input(current)
    at.text_input(key="change_password_new").input(new)
    at.text_input(key="change_password_confirm").input(confirm)


def test_profile_offers_a_change_password_form(profile_calls: List[tuple]) -> None:
    at = _profile()
    # An expander with an icon is reported by AppTest as a status block.
    folded = [e.label for e in at.expander] + [e.label for e in at.status]
    assert [label for label in folded if "password" in label.lower()] == ["Change password"]
    labels = [t.label for t in at.text_input]
    for wanted in ("Current password", "New password", "Confirm new password"):
        assert wanted in labels
    for key in ("change_password_current", "change_password_new", "change_password_confirm"):
        assert at.text_input(key=key).proto.type == TextInputProto.PASSWORD


def test_a_good_change_goes_to_the_service_and_clears_the_fields(
    profile_calls: List[tuple],
) -> None:
    at = _profile()
    _fill(at, OLD, NEW, NEW)
    next(b for b in at.button if b.label == "Change password").click().run()
    assert not at.exception, at.exception
    assert profile_calls == [(OLD, NEW)]
    assert any("Password changed." in s.value for s in at.success)
    for key in ("change_password_current", "change_password_new", "change_password_confirm"):
        assert at.text_input(key=key).value == ""


def test_a_failed_change_keeps_what_was_typed(profile_calls: List[tuple]) -> None:
    at = _profile()
    _fill(at, "Wrong-one-1", NEW, NEW)
    next(b for b in at.button if b.label == "Change password").click().run()
    assert any("current password" in e.value.lower() for e in at.error)
    assert at.text_input(key="change_password_new").value == NEW
    assert at.text_input(key="change_password_confirm").value == NEW


def test_mismatched_new_passwords_never_reach_the_service(
    profile_calls: List[tuple],
) -> None:
    at = _profile()
    _fill(at, OLD, NEW, NEW + "x")
    next(b for b in at.button if b.label == "Change password").click().run()
    assert any("do not match" in e.value for e in at.error)
    assert profile_calls == []
    assert at.text_input(key="change_password_current").value == OLD
