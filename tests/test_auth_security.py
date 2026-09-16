"""Tests for the privacy and security controls around signing in and up.

WHAT THESE COVER
  * password rules at sign-up, with a message that says what to change
  * the per-session lock after repeated failed sign-ins
  * length limits on every field a visitor can type into, in the service and
    on the forms
  * that emails, passwords and tokens are not echoed back onto the page or
    written to stdout, stderr or a log
  * that the privacy notice says what is now true: names and emails are stored,
    who sees them, and how to delete them

WHAT THEY DO NOT COVER
  Supabase Auth's own per-IP rate limit and password policy. The lock here is
  per browser session, so a new session starts with a clean slate; it slows
  somebody at a keyboard and is not the real defence against a script.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import pytest

from services import auth_service
from tests.test_auth import STUDENT_PROFILE, FakeAuthClient, _FakeAuth, _install
from utils import config

ROOT = Path(__file__).resolve().parent.parent
SIGN_IN_PAGE = str(ROOT / "pages" / "sign_in.py")


class _Clock:
    """Stands in for the `time` module inside auth_service."""

    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def time(self) -> float:
        return self.now


class _CountingClient(FakeAuthClient):
    """Counts how often Supabase is actually asked, so a lock can be proven."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.sign_in_calls = 0
        self.sign_up_calls = 0
        outer = self

        class _CountingAuth(_FakeAuth):
            def sign_in_with_password(self, credentials: Dict[str, str]) -> None:
                outer.sign_in_calls += 1
                return super().sign_in_with_password(credentials)

            def sign_up(self, credentials: Dict[str, Any]) -> Any:
                outer.sign_up_calls += 1
                return super().sign_up(credentials)

        self.auth = _CountingAuth(outer)


def _counting(monkeypatch: pytest.MonkeyPatch) -> _CountingClient:
    client = _CountingClient(
        accounts={"a@example.com": "hunter22"}, profiles=[dict(STUDENT_PROFILE)]
    )
    _install(monkeypatch, client)
    return client


# --------------------------------------------------------------------------
# Password rules
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "password, fragment",
    [
        ("abc123", "at least 8 characters"),
        ("abcdefgh", "at least one number"),
        ("12345678", "at least one letter"),
        ("a1" * 65, "at most 128 characters"),
    ],
)
def test_weak_passwords_are_refused_with_a_clear_reason(
    password: str, fragment: str
) -> None:
    problem = auth_service.password_problem(password)
    assert problem is not None and fragment in problem


@pytest.mark.parametrize("password", ["hunter22", "correct horse 9", "Pässwört1"])
def test_reasonable_passwords_are_accepted(password: str) -> None:
    assert auth_service.password_problem(password) is None


def test_sign_up_with_a_weak_password_never_reaches_supabase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _counting(monkeypatch)

    outcome = auth_service.sign_up("new@example.com", "password", "Ada")

    assert outcome.ok is False
    assert "number" in outcome.message
    assert client.sign_up_calls == 0


# --------------------------------------------------------------------------
# Locking after repeated failures
# --------------------------------------------------------------------------
def _fail(times: int) -> List[auth_service.AuthOutcome]:
    return [auth_service.sign_in("a@example.com", "wrong1") for _ in range(times)]


def test_five_failures_lock_the_form_and_stop_calling_supabase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    monkeypatch.setattr(auth_service, "time", clock)
    client = _counting(monkeypatch)

    _fail(auth_service.MAX_FAILED_SIGN_INS)
    assert client.sign_in_calls == auth_service.MAX_FAILED_SIGN_INS

    # Even the right password is refused while locked - otherwise the lock only
    # inconveniences somebody who has already given up.
    locked = auth_service.sign_in("a@example.com", "hunter22")

    assert locked.ok is False
    assert "Too many failed attempts" in locked.message
    assert "60 seconds" in locked.message
    assert client.sign_in_calls == auth_service.MAX_FAILED_SIGN_INS
    assert auth_service.is_signed_in() is False


def test_the_lock_lifts_after_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _Clock()
    monkeypatch.setattr(auth_service, "time", clock)
    _counting(monkeypatch)
    _fail(auth_service.MAX_FAILED_SIGN_INS)

    clock.now += auth_service.LOCKOUT_SECONDS - 1
    assert auth_service.sign_in_locked_for() == 1

    clock.now += 1
    assert auth_service.sign_in_locked_for() == 0
    assert auth_service.sign_in("a@example.com", "hunter22").ok is True


def test_a_successful_sign_in_resets_the_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Four typos, a success, then four more must not add up to a lock."""
    monkeypatch.setattr(auth_service, "time", _Clock())
    _counting(monkeypatch)

    _fail(auth_service.MAX_FAILED_SIGN_INS - 1)
    assert auth_service.sign_in("a@example.com", "hunter22").ok
    auth_service.sign_out()
    _fail(auth_service.MAX_FAILED_SIGN_INS - 1)

    assert auth_service.sign_in_locked_for() == 0


def test_the_lock_message_is_the_same_whether_or_not_the_account_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_service, "time", _Clock())
    _counting(monkeypatch)
    _fail(auth_service.MAX_FAILED_SIGN_INS)

    real = auth_service.sign_in("a@example.com", "x1").message
    made_up = auth_service.sign_in("nobody@example.com", "x1").message

    assert real == made_up


# --------------------------------------------------------------------------
# Length limits
# --------------------------------------------------------------------------
def test_an_oversized_sign_in_is_refused_locally_and_counts_as_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_service, "time", _Clock())
    client = _counting(monkeypatch)

    long_email = auth_service.sign_in("a" * 300 + "@example.com", "hunter22")
    long_password = auth_service.sign_in("a@example.com", "p1" * 100)

    assert long_email.ok is False and long_password.ok is False
    assert long_email.message == "That email and password do not match an account."
    assert client.sign_in_calls == 0


def test_an_oversized_sign_up_is_refused_before_supabase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _counting(monkeypatch)

    long_name = auth_service.sign_up("n@example.com", "hunter22", "N" * 61)
    long_email = auth_service.sign_up("n" * 255 + "@example.com", "hunter22", "Ada")

    assert long_name.ok is False and "60" in long_name.message
    assert long_email.ok is False and "too long" in long_email.message
    assert client.sign_up_calls == 0


def test_every_text_box_on_the_sign_in_page_has_a_length_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = _render_sign_in_page(monkeypatch)

    assert at.text_input.len >= 6
    for widget in at.text_input:
        assert widget.max_chars, f"{widget.label} has no max_chars"


# --------------------------------------------------------------------------
# Nothing sensitive echoed or logged
# --------------------------------------------------------------------------
def test_an_unrecognised_auth_error_is_summarised_not_echoed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gotrue messages can carry the email that was typed; the page shows this."""

    class _Leaky(FakeAuthClient):
        def __init__(self) -> None:
            super().__init__()

            class _Auth(_FakeAuth):
                def sign_in_with_password(self, credentials: Dict[str, str]) -> None:
                    raise RuntimeError(
                        f"unexpected failure for {credentials['email']} "
                        "token=eyJhbGciOi.eyJzdWIi.c2ln"
                    )

            self.auth = _Auth(self)

    _install(monkeypatch, _Leaky())

    message = auth_service.sign_in("secret.person@example.com", "hunter22").message

    assert "secret.person" not in message
    assert "eyJ" not in message
    assert message == "Authentication failed. Please try again."


def test_error_details_shown_on_the_profile_page_are_redacted() -> None:
    raw = RuntimeError(
        "upload failed for ada@example.com: Authorization: Bearer abc.def.ghi "
        "at https://x.supabase.co/storage?apikey=sb_publishable_123 jwt "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"
    )

    shown = auth_service._redacted(raw)

    for secret in ("ada@example.com", "abc.def.ghi", "sb_publishable_123", "eyJ"):
        assert secret not in shown
    assert "upload failed" in shown


def test_signing_in_and_up_write_no_credentials_to_output_or_logs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    _counting(monkeypatch)

    auth_service.sign_in("a@example.com", "wrongpass1")
    auth_service.sign_in("a@example.com", "hunter22")
    auth_service.sign_out()
    auth_service.sign_up("fresh@example.com", "brandnew99", "Ada")

    captured = capsys.readouterr()
    everything = captured.out + captured.err + caplog.text
    for secret in (
        "a@example.com",
        "fresh@example.com",
        "wrongpass1",
        "hunter22",
        "brandnew99",
    ):
        assert secret not in everything


def test_no_auth_module_prints_or_logs() -> None:
    """A tripwire: the modules that handle credentials should not log at all."""
    for relative in (
        "services/auth_service.py",
        "components/auth_forms.py",
        "pages/sign_in.py",
        "pages/landing.py",
        "pages/profile.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        for call in ("print(", "logging.", "logger.", "st.write(password"):
            assert call not in source, f"{relative} contains {call}"


# --------------------------------------------------------------------------
# The privacy notice says what is now true
# --------------------------------------------------------------------------
def test_the_privacy_notice_admits_names_and_emails_are_stored() -> None:
    notice = config.PRIVACY_NOTICE.lower()

    assert "name" in notice and "email" in notice
    assert "teacher" in notice
    assert "delete" in notice and "profile" in notice
    # The old promise contradicts the sign-up form and must not come back.
    assert "do not upload real student names" not in notice


def test_the_full_privacy_statement_covers_what_why_who_and_deletion() -> None:
    details = " ".join(config.PRIVACY_DETAILS).lower()

    for topic in ("what we store", "why", "who can see it", "deleting it"):
        assert topic in details
    assert "profile > delete account" in details
    assert "class list" in details


def _render_sign_in_page(monkeypatch: pytest.MonkeyPatch, locked_until: float = 0):
    import services.supabase_client as client_module
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(
        client_module,
        "get_connection_status",
        lambda: client_module.ConnectionStatus(
            connected=True, demo_mode=True, signed_out=True, message="Connected."
        ),
    )
    monkeypatch.setattr(auth_service, "current_user", lambda: None)

    at = AppTest.from_file(SIGN_IN_PAGE, default_timeout=60)
    if locked_until:
        at.session_state[auth_service.LOCKED_UNTIL] = locked_until
    at.run()
    assert not at.exception, at.exception
    return at


def test_the_sign_in_page_shows_the_full_privacy_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = _render_sign_in_page(monkeypatch)

    # An expander with an icon is reported by AppTest as a status block.
    folded = [e.label for e in at.expander] + [e.label for e in at.status]
    assert "How we use your name and email" in folded
    body = " ".join(m.value for m in at.markdown)
    assert "Profile > Delete account" in body
    captions = " ".join(c.value for c in at.caption)
    assert "store your name and email" in captions


def test_the_sign_in_page_says_when_the_form_is_locked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    at = _render_sign_in_page(monkeypatch, locked_until=time.time() + 30)

    assert any("Too many failed attempts" in w.value for w in at.warning)


def test_the_sign_up_form_explains_the_password_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = _render_sign_in_page(monkeypatch)

    [password] = [w for w in at.text_input if w.key == "sign_up_password"]
    assert "8 characters" in password.help and "number" in password.help


def test_the_sign_up_form_rejects_a_weak_password_with_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: List[Any] = []
    monkeypatch.setattr(auth_service, "sign_up", lambda *a: called.append(a))
    at = _render_sign_in_page(monkeypatch)

    at.text_input(key="sign_up_name").input("Ada Lovelace")
    at.text_input(key="sign_up_email").input("ada@example.com")
    at.text_input(key="sign_up_password").input("letmein")
    at.text_input(key="sign_up_confirm").input("letmein")
    next(b for b in at.button if b.label == "Create account").click()
    at.run()

    assert not at.exception, at.exception
    errors = [e.value for e in at.error]
    assert errors == ["Your password must be at least 8 characters."]
    assert called == []
    # The typed email is not echoed anywhere outside its own input box.
    rendered = " ".join(
        [m.value for m in at.markdown]
        + [c.value for c in at.caption]
        + errors
    )
    assert "ada@example.com" not in rendered
