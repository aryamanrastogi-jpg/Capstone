"""Regression tests for the auth / access-control fixes from the QA audit.

BUG-001  students read teacher and shared sets through student_questions
BUG-003  Create Assessment passes owner_id and reports a refused save calmly
BUG-006  a deep link that had to pass the welcome page lands where it asked
BUG-017  the sign-in lockout survives a new browser session
BUG-020  a cached profile does not outlive the session behind it
BUG-032  no Sign In page when there is nothing to sign in to

The SQL halves of BUG-001/002/016 live in db/migrations/007_bug_fixes.sql and
need a real Postgres to exercise; these cover the application side.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from models import Role
from services import auth_service
from services import repository as repository_module
from services.repository import SessionRepository, SupabaseRepository
from tests.test_auth import STUDENT_PROFILE, FakeAuthClient, _install
from tests.test_repository import FakeSupabase

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def _no_forced_repository():
    repository_module.set_repository(None)
    yield
    repository_module.set_repository(None)


# --------------------------------------------------------------------------
# BUG-017
# --------------------------------------------------------------------------
def _client(monkeypatch: pytest.MonkeyPatch) -> FakeAuthClient:
    client = FakeAuthClient(
        accounts={"a@example.com": "hunter22"}, profiles=[dict(STUDENT_PROFILE)]
    )
    _install(monkeypatch, client)
    return client


def test_the_lockout_survives_a_new_browser_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _client(monkeypatch)
    for _ in range(auth_service.MAX_FAILED_SIGN_INS):
        auth_service.sign_in("a@example.com", "wrong1")

    # A refresh is a brand-new session: fresh session state, fresh client.
    _client(monkeypatch)
    assert auth_service.sign_in_locked_for() == 0  # the session itself is clean

    # Case and surrounding spaces do not make it a different account.
    locked = auth_service.sign_in("  A@Example.com ", "hunter22")
    assert locked.ok is False
    assert "Too many failed attempts" in locked.message
    assert auth_service.sign_in_locked_for("a@example.com") > 0


def test_the_process_lockout_is_per_email(monkeypatch: pytest.MonkeyPatch) -> None:
    _client(monkeypatch)
    for _ in range(auth_service.MAX_FAILED_SIGN_INS):
        auth_service.sign_in("someone@example.com", "wrong1")

    _client(monkeypatch)
    assert auth_service.sign_in("a@example.com", "hunter22").ok is True


def test_a_successful_sign_in_clears_the_email_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _client(monkeypatch)
    for _ in range(auth_service.MAX_FAILED_SIGN_INS - 1):
        auth_service.sign_in("a@example.com", "wrong1")
    assert auth_service.sign_in("a@example.com", "hunter22").ok
    auth_service.sign_out()

    _client(monkeypatch)
    auth_service.sign_in("a@example.com", "wrong1")
    assert auth_service.sign_in_locked_for("a@example.com") == 0


# --------------------------------------------------------------------------
# BUG-020
# --------------------------------------------------------------------------
def test_a_cached_profile_is_dropped_when_the_session_has_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch)
    assert auth_service.sign_in("a@example.com", "hunter22").ok
    assert auth_service.current_user() is not None

    # The token expired and could not be refreshed.
    client.session = None

    assert auth_service.current_user() is None
    assert auth_service.st.session_state.get(auth_service.PROFILE) is None


def test_a_cached_profile_is_used_while_the_session_is_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch)
    assert auth_service.sign_in("a@example.com", "hunter22").ok
    client.profiles.clear()  # would be unreadable if it were fetched again

    user = auth_service.current_user()
    assert user is not None and user.id == STUDENT_PROFILE["id"]


# --------------------------------------------------------------------------
# BUG-001
# --------------------------------------------------------------------------
def _assessment_row(assessment_id: str, owner_id: Any, student_created: bool) -> Dict[str, Any]:
    return {
        "id": assessment_id,
        "title": f"Set {assessment_id}",
        "grade_level": 10,
        "topic": "Algebra",
        "owner_id": owner_id,
        "student_created": student_created,
        "is_shared": False,
    }


def _question_row(assessment_id: str, answer: bool) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "id": f"q_{assessment_id}",
        "assessment_id": assessment_id,
        "position": 0,
        "question_text": "Solve 2x = 8",
        "max_marks": "2",
    }
    if answer:
        row.update(model_answer="x = 4", marking_criteria="1 mark method")
    return row


@pytest.fixture()
def student_db() -> FakeSupabase:
    """What PostgREST returns to a signed-in student after migration 007.

    `questions` only holds rows RLS lets the student see (their own set); the
    view holds every visible set, without the answer columns.
    """
    db = FakeSupabase()
    db.tables["assessments"] = [
        _assessment_row("as_teacher", "usr_t1", False),
        _assessment_row("as_mine", "usr_s01", True),
        _assessment_row("as_hidden", "usr_t9", False),
    ]
    db.tables["questions"] = [_question_row("as_mine", answer=True)]
    db.tables["student_questions"] = [
        _question_row("as_teacher", answer=False),
        _question_row("as_mine", answer=False),
    ]
    return db


def test_a_student_loads_teacher_sets_without_their_answers(
    student_db: FakeSupabase,
) -> None:
    repo = SupabaseRepository(student_db, student_reads=True)

    loaded = {a.id: a for a in repo.list_assessments()}

    teacher_set = loaded["as_teacher"]
    assert teacher_set.question_count == 1
    assert teacher_set.questions[0].model_answer == ""
    assert teacher_set.is_gradable is False
    # Their own set keeps the answers they wrote, so it can still be graded.
    assert loaded["as_mine"].questions[0].model_answer == "x = 4"
    assert loaded["as_mine"].is_gradable is True
    # A set with no readable questions is skipped instead of breaking the list.
    assert "as_hidden" not in loaded
    assert repo.get_assessment("as_hidden") is None
    assert repo.get_assessment("as_teacher").questions[0].model_answer == ""


def test_a_teacher_reads_the_questions_table_directly(student_db: FakeSupabase) -> None:
    student_db.select_calls.clear()
    SupabaseRepository(student_db).list_assessments()
    assert "student_questions" not in student_db.select_calls


@pytest.mark.parametrize("role, student_reads", [(Role.STUDENT, True), (Role.TEACHER, False), (None, True)])
def test_get_repository_picks_the_read_path_from_the_role(
    monkeypatch: pytest.MonkeyPatch, role: Any, student_reads: bool
) -> None:
    monkeypatch.setattr(auth_service, "authenticated_client", lambda: FakeSupabase())
    monkeypatch.setattr(auth_service, "current_role", lambda: role)

    repo = repository_module.get_repository()

    assert isinstance(repo, SupabaseRepository)
    assert repo._student_reads is student_reads


# --------------------------------------------------------------------------
# BUG-032
# --------------------------------------------------------------------------
def test_sign_in_is_hidden_when_accounts_are_unavailable() -> None:
    from components.navigation import pages_for

    without = {s["title"] for s in pages_for(Role.STUDENT, False, accounts_available=False)}
    with_accounts = {s["title"] for s in pages_for(Role.STUDENT, False)}

    assert "Sign In" not in without
    assert "Sign In" in with_accounts


# --------------------------------------------------------------------------
# App-level: BUG-003, BUG-006, BUG-032
# --------------------------------------------------------------------------
def _app_as(role: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    users = at.session_state["users"]
    wanted = next(u for u in users if u.role.value == role)
    at.session_state["current_user_id"] = wanted.id
    at.session_state["entered_demo"] = True
    at.run()
    assert not at.exception, at.exception
    return at


def test_the_demo_menu_has_no_sign_in_page() -> None:
    at = _app_as("student")
    with pytest.raises(ValueError):
        at.switch_page("pages/sign_in.py")


def test_a_deep_link_is_honoured_once_the_visitor_is_in() -> None:
    from components.navigation import REQUESTED_PAGE

    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    # Set by the hidden deep-link page on the welcome screen.
    at.session_state[REQUESTED_PAGE] = "pages/study_camp.py"
    next(b for b in at.button if b.label == "Explore the demo").click().run()

    assert not at.exception, at.exception
    assert REQUESTED_PAGE not in at.session_state
    assert "Start my study camp" in [b.label for b in at.button]


def test_a_deep_link_to_the_other_role_s_page_is_ignored() -> None:
    from components.navigation import REQUESTED_PAGE

    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    at.session_state[REQUESTED_PAGE] = "pages/dashboard.py"
    next(b for b in at.button if b.label == "Explore the demo").click().run()

    assert not at.exception, at.exception
    assert REQUESTED_PAGE not in at.session_state


def _fill_create_assessment(at: AppTest) -> None:
    at.session_state["create_assessment_rows"] = pd.DataFrame(
        [{"question_text": "Solve 2x = 8", "model_answer": "x = 4",
          "marking_criteria": "", "max_marks": 2.0}]
    )
    at.switch_page("pages/create_assessment.py").run()
    at.text_input(key="ca_title").input("Owner test")
    at.text_input(key="ca_topic").input("Algebra")
    next(b for b in at.button if b.label == "Save assessment").click().run()


def test_create_assessment_saves_the_teacher_as_owner() -> None:
    at = _app_as("teacher")
    teacher_id = at.session_state["current_user_id"]

    _fill_create_assessment(at)

    assert not at.exception, at.exception
    saved = [a for a in at.session_state["assessments"] if a.title == "Owner test"]
    assert len(saved) == 1
    assert saved[0].owner_id == teacher_id
    assert saved[0].student_created is False


def test_a_refused_save_is_reported_without_a_traceback() -> None:
    class _Refusing(SessionRepository):
        def save_assessment(self, assessment):  # type: ignore[override]
            raise RuntimeError("new row violates row-level security policy")

    at = _app_as("teacher")
    repository_module.set_repository(_Refusing())

    _fill_create_assessment(at)

    assert not at.exception, at.exception
    errors = " ".join(e.value for e in at.error)
    assert "could not be saved" in errors
    assert "row-level security" not in errors
