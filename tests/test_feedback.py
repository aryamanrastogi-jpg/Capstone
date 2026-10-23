"""The sidebar survey: what it accepts, where it goes, and the sidebar around it."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services import auth_service, feedback_service
from services.feedback_service import MAX_FEEDBACK_CHARS
from models import Role

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")


class _FakeTable:
    def __init__(self, calls, fail):
        self.calls, self.fail = calls, fail

    def insert(self, row, **kwargs):
        self.calls.append((row, kwargs))
        return self

    def execute(self):
        if self.fail:
            raise RuntimeError("permission denied")
        return None


class _FakeClient:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def table(self, name):
        assert name == "app_feedback"
        return _FakeTable(self.calls, self.fail)


@pytest.mark.parametrize(
    "rating, suggestion, comments",
    [
        (None, "", ""),
        (0, "", ""),
        (6, "", ""),
        (3, "x" * (MAX_FEEDBACK_CHARS + 1), ""),
        (3, "", "x" * (MAX_FEEDBACK_CHARS + 1)),
    ],
)
def test_a_bad_answer_is_refused_before_anything_is_sent(
    monkeypatch, rating, suggestion, comments
):
    client = _FakeClient()
    monkeypatch.setattr(auth_service, "authenticated_client", lambda: client)

    outcome = feedback_service.submit(rating, suggestion, comments)

    assert not outcome.saved and outcome.level == "error"
    assert client.calls == []


def test_the_demo_says_it_did_not_send(monkeypatch):
    monkeypatch.setattr(auth_service, "authenticated_client", lambda: None)

    outcome = feedback_service.submit(4, "more topics", "")

    assert not outcome.saved and outcome.level == "info"
    assert "not sent" in outcome.message


def test_a_signed_in_answer_is_inserted_without_reading_it_back(monkeypatch):
    from postgrest import ReturnMethod

    client = _FakeClient()
    monkeypatch.setattr(auth_service, "authenticated_client", lambda: client)
    monkeypatch.setattr(auth_service, "current_role", lambda: Role.STUDENT)

    outcome = feedback_service.submit(5, "  flashcards  ", "")

    assert outcome.saved and outcome.level == "success"
    [(row, kwargs)] = client.calls
    # No author column: the database fills it from the signed-in account.
    assert row == {"rating": 5, "suggestion": "flashcards", "comments": None, "role": "student"}
    assert kwargs["returning"] is ReturnMethod.minimal


def test_a_failed_insert_gives_a_plain_message(monkeypatch):
    client = _FakeClient(fail=True)
    monkeypatch.setattr(auth_service, "authenticated_client", lambda: client)
    monkeypatch.setattr(auth_service, "current_role", lambda: Role.TEACHER)

    outcome = feedback_service.submit(2, "", "slow")

    assert not outcome.saved and outcome.level == "error"
    assert "permission" not in outcome.message


def test_the_migration_lets_users_only_add_their_own_rows():
    sql = (ROOT / "db" / "migrations" / "009_app_feedback.sql").read_text(encoding="utf-8")

    assert "enable row level security" in sql
    assert "with check (profile_id = public.app_profile_id())" in sql
    assert "grant insert (role, rating, suggestion, comments)" in sql
    assert "for select" not in sql
    assert "009_app_feedback" in (ROOT / "db" / "setup_all.sql").read_text(encoding="utf-8")


def _demo_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    at.session_state["entered_demo"] = True
    at.run()
    assert not at.exception, at.exception
    return at


def test_the_sidebar_has_feedback_and_none_of_the_old_clutter():
    at = _demo_app()
    labels = [b.label for b in at.sidebar.button]

    assert "Give feedback" in labels
    assert "Welcome page" in labels and "Reset" in labels
    sidebar_text = " ".join(c.value for c in at.sidebar.caption)
    assert "Privacy:" not in sidebar_text
    assert "About" not in [m.value for m in at.sidebar.markdown]
    assert "st.logo(" not in (ROOT / "app.py").read_text(encoding="utf-8")


def test_the_feedback_button_opens_the_survey():
    at = _demo_app()
    next(b for b in at.sidebar.button if b.label == "Give feedback").click().run()

    assert not at.exception, at.exception
    areas = [t.label for t in at.text_area]
    assert "2. What do you think we should include in the app?" in areas
    assert "3. Any feedback?" in areas
