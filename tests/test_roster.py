"""Tests for class rosters.

WHAT MATTERS HERE
  `profiles.teacher_id` decides what a student can see and whose oversight they
  fall under. So the tests worth writing are about who is allowed to change it,
  not about the happy path:

    * a student joins only the class whose code they were given
    * a revoked code stops working
    * a teacher can only remove somebody who is actually on their roster
    * an invalid code and a revoked code are indistinguishable from outside

WHAT THEY DO NOT COVER
  The `security definer` functions in db/migrations/003_roster.sql. These run
  against the session-state backend, so they exercise the demo path and the
  service layer. Whether the SQL functions refuse the same things needs a
  signed-in integration test against a live project - still outstanding, and
  noted in db/README.md.
"""

from __future__ import annotations

from typing import Dict, List

import pytest

from models import Role, User
from services import roster_service
from services.repository import (
    CODE_ALPHABET,
    CODE_LENGTH,
    SessionRepository,
    generate_class_code,
)

TEACHER_A = "usr_t_a"
TEACHER_B = "usr_t_b"


class _Store:
    """Stands in for services.state, holding users and codes in memory."""

    def __init__(self, users: List[User]) -> None:
        self.users = users
        self.codes: Dict[str, str] = {}


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    users = [
        User(id=TEACHER_A, display_name="Ms Rao", role=Role.TEACHER),
        User(id=TEACHER_B, display_name="Mr Diaz", role=Role.TEACHER),
        User(id="usr_s01", display_name="S-1101", role=Role.STUDENT,
             teacher_id=TEACHER_A, year_group=10),
        User(id="usr_s02", display_name="S-1102", role=Role.STUDENT,
             year_group=10),
        User(id="usr_s03", display_name="S-1103", role=Role.STUDENT,
             teacher_id=TEACHER_B, year_group=9),
    ]
    fake = _Store(users)

    import services.repository as repository_module

    monkeypatch.setattr(repository_module.store, "get_users", lambda: fake.users)
    monkeypatch.setattr(repository_module.store, "get_class_codes", lambda: fake.codes)
    repository_module.set_repository(SessionRepository())
    yield fake
    repository_module.set_repository(None)


def _student(store: _Store, student_id: str) -> User:
    return next(u for u in store.users if u.id == student_id)


# --------------------------------------------------------------------------
# Code generation
# --------------------------------------------------------------------------
def test_a_generated_code_avoids_characters_that_get_misread() -> None:
    """These get read aloud and copied off a whiteboard. No O/0, no I/1."""
    codes = [generate_class_code() for _ in range(200)]

    for code in codes:
        assert len(code) == CODE_LENGTH
        assert set(code) <= set(CODE_ALPHABET)

    joined = "".join(codes)
    for confusable in "O0I1":
        assert confusable not in joined


def test_codes_are_not_all_the_same() -> None:
    assert len({generate_class_code() for _ in range(50)}) > 40


# --------------------------------------------------------------------------
# Joining
# --------------------------------------------------------------------------
def test_a_student_joins_the_class_whose_code_they_were_given(
    store: _Store,
) -> None:
    code = roster_service.rotate_class_code(TEACHER_A)

    outcome = roster_service.join_class("usr_s02", code)

    assert outcome.ok is True
    assert _student(store, "usr_s02").teacher_id == TEACHER_A


def test_joining_is_case_and_whitespace_forgiving(store: _Store) -> None:
    """It gets copied off a whiteboard; a stray space is not a wrong answer."""
    code = roster_service.rotate_class_code(TEACHER_A)

    outcome = roster_service.join_class("usr_s02", f"  {code.lower()} ")

    assert outcome.ok is True
    assert _student(store, "usr_s02").teacher_id == TEACHER_A


def test_an_unknown_code_joins_nothing(store: _Store) -> None:
    roster_service.rotate_class_code(TEACHER_A)

    outcome = roster_service.join_class("usr_s02", "ZZZZZZ")

    assert outcome.ok is False
    assert _student(store, "usr_s02").teacher_id is None


def test_an_empty_code_is_rejected_before_anything_is_looked_up(
    store: _Store,
) -> None:
    outcome = roster_service.join_class("usr_s02", "   ")

    assert outcome.ok is False
    assert _student(store, "usr_s02").teacher_id is None


def test_a_rotated_code_stops_working(store: _Store) -> None:
    """Rotation has to revoke, or the button is a decoration."""
    old_code = roster_service.rotate_class_code(TEACHER_A)
    new_code = roster_service.rotate_class_code(TEACHER_A)
    assert old_code != new_code

    with_old = roster_service.join_class("usr_s02", old_code)

    assert with_old.ok is False
    assert _student(store, "usr_s02").teacher_id is None

    with_new = roster_service.join_class("usr_s02", new_code)
    assert with_new.ok is True


def test_rotating_does_not_evict_the_students_already_in_the_class(
    store: _Store,
) -> None:
    """The code is how you join, not what keeps you there."""
    roster_service.rotate_class_code(TEACHER_A)

    assert [s.id for s in roster_service.list_roster(TEACHER_A)] == ["usr_s01"]


def test_an_invalid_code_and_a_revoked_code_look_identical(
    store: _Store,
) -> None:
    """Otherwise the box becomes a way of testing which codes exist."""
    old_code = roster_service.rotate_class_code(TEACHER_A)
    roster_service.rotate_class_code(TEACHER_A)

    revoked = roster_service.join_class("usr_s02", old_code)
    unknown = roster_service.join_class("usr_s02", "ZZZZZZ")

    assert revoked.message == unknown.message


def test_joining_a_second_class_moves_the_student(store: _Store) -> None:
    """A student has one teacher. Joining B leaves A, it does not stack."""
    code_b = roster_service.rotate_class_code(TEACHER_B)

    roster_service.join_class("usr_s01", code_b)

    assert _student(store, "usr_s01").teacher_id == TEACHER_B
    assert [s.id for s in roster_service.list_roster(TEACHER_A)] == []


def test_a_teacher_cannot_join_a_class(store: _Store) -> None:
    """A teacher on a roster would break teacher_has_no_roster, and mean nothing."""
    code = roster_service.rotate_class_code(TEACHER_A)

    outcome = roster_service.join_class(TEACHER_B, code)

    assert outcome.ok is False
    assert _student(store, TEACHER_B).teacher_id is None


# --------------------------------------------------------------------------
# Leaving and removing
# --------------------------------------------------------------------------
def test_a_student_can_leave(store: _Store) -> None:
    outcome = roster_service.leave_class("usr_s01")

    assert outcome.ok is True
    assert _student(store, "usr_s01").teacher_id is None


def test_a_teacher_removes_a_student_on_their_own_roster(store: _Store) -> None:
    outcome = roster_service.remove_from_roster(TEACHER_A, "usr_s01")

    assert outcome.ok is True
    assert _student(store, "usr_s01").teacher_id is None


def test_a_teacher_cannot_remove_somebody_elses_student(store: _Store) -> None:
    """usr_s03 is on Mr Diaz's roster, not Ms Rao's."""
    outcome = roster_service.remove_from_roster(TEACHER_A, "usr_s03")

    assert outcome.ok is False
    assert _student(store, "usr_s03").teacher_id == TEACHER_B


def test_removing_a_student_deletes_nothing_they_made(
    store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removal changes visibility, not ownership."""
    import services.repository as repository_module

    from models import Assessment, Question

    owned = [
        Assessment(
            id="as_own",
            title="My worksheet",
            grade_level=10,
            topic="Algebra",
            owner_id="usr_s01",
            student_created=True,
            questions=[Question(id="q1", question_text="Solve 2x = 8", max_marks=2)],
        )
    ]
    monkeypatch.setattr(
        repository_module.store, "get_assessments", lambda: owned
    )

    roster_service.remove_from_roster(TEACHER_A, "usr_s01")

    from services import assessment_service

    assert [a.id for a in assessment_service.list_assessments_owned_by("usr_s01")] == [
        "as_own"
    ]


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------
def test_a_roster_holds_only_that_teachers_students(store: _Store) -> None:
    assert [s.id for s in roster_service.list_roster(TEACHER_A)] == ["usr_s01"]
    assert [s.id for s in roster_service.list_roster(TEACHER_B)] == ["usr_s03"]


def test_a_roster_never_contains_a_teacher(store: _Store) -> None:
    code = roster_service.rotate_class_code(TEACHER_A)
    roster_service.join_class("usr_s02", code)

    roster = roster_service.list_roster(TEACHER_A)

    assert all(s.is_student for s in roster)


def test_a_teacher_with_no_code_has_no_code(store: _Store) -> None:
    assert roster_service.class_code(TEACHER_A) is None

    code = roster_service.rotate_class_code(TEACHER_A)

    assert roster_service.class_code(TEACHER_A) == code
    assert roster_service.class_code(TEACHER_B) is None


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------
def _page() -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parent.parent / "pages" / "my_class.py")


def _seeded_users() -> List[User]:
    return [
        User(id="usr_t", display_name="Ms Rao", role=Role.TEACHER),
        User(id="usr_s", display_name="S-1101", role=Role.STUDENT,
             teacher_id="usr_t"),
        User(id="usr_s_free", display_name="S-1102", role=Role.STUDENT),
    ]


def _run_page_as(user_id: str):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(_page(), default_timeout=60)
    at.session_state["users"] = _seeded_users()
    at.session_state["current_user_id"] = user_id
    at.run()
    assert not at.exception, at.exception
    return at


def test_the_teacher_view_renders_with_roster_controls() -> None:
    at = _run_page_as("usr_t")

    labels = [b.label for b in at.button]
    assert "Issue a class code" in labels
    assert "Remove from class" in labels


def test_the_student_view_names_the_class_they_are_in() -> None:
    at = _run_page_as("usr_s")

    assert any("Ms Rao" in m.value for m in at.success)


def test_a_student_with_no_class_is_offered_a_join_box_not_an_error() -> None:
    """Having no class is a normal state, not a failure."""
    at = _run_page_as("usr_s_free")

    assert any("not in a class yet" in m.value for m in at.info)
    assert any((w.label or "") == "Class code" for w in at.text_input)


def test_the_student_view_offers_no_way_to_pick_a_teacher_directly() -> None:
    """Joining goes through a code. A teacher picker would skip their consent."""
    at = _run_page_as("usr_s_free")

    labels = " ".join((w.label or "") for w in at.selectbox).lower()
    assert "teacher" not in labels
    assert "class" not in labels
