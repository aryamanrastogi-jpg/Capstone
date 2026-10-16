"""Editing and deleting a question set after it has been created.

Creating a set was the only write the pages offered. These cover the rest:
the service keeps a set's identity and its question ids through an edit (so
work already handed in stays attached), only the author may change a set, and
both pages drive the edit dialog and the two-click delete without an error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from streamlit.testing.v1 import AppTest

from postgrest.exceptions import APIError

from models import Assessment, GradingResult, Question, ReviewStatus, Role, User
from services import assessment_service as service
from services import attempt_service
from services.repository import SessionRepository, SupabaseRepository, set_repository
from tests.test_form_page_fixes import (
    _app_as,
    _button,
    _labels,
    _owned_titles,
    _student_with_a_saved_set,
)
from tests.test_repository import _assessment, _Query, _submission
from tests.test_review_persistence import CascadingSupabase

APP = str(Path(__file__).resolve().parent.parent / "app.py")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
@pytest.fixture()
def db() -> CascadingSupabase:
    return CascadingSupabase()


@pytest.fixture()
def repo(
    db: CascadingSupabase, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SupabaseRepository]:
    from services import auth_service

    monkeypatch.setattr(
        auth_service,
        "current_user",
        lambda: User(id="teacher_1", display_name="Teacher", role=Role.TEACHER),
    )
    repository = SupabaseRepository(db)
    set_repository(repository)
    yield repository
    set_repository(None)


def test_rows_keep_their_ids_only_once_and_only_for_this_set():
    rows = [
        {"id": "q_keep", "question_text": "A", "max_marks": 1},
        # A duplicated row cannot claim the same question twice.
        {"id": "q_keep", "question_text": "A again", "max_marks": 1},
        # An id from some other set is not this set's to reuse.
        {"id": "q_elsewhere", "question_text": "B", "max_marks": 2},
        {"id": "", "question_text": "C", "max_marks": 1},
    ]

    questions = service.build_questions(rows, keep_ids=["q_keep"])

    ids = [q.id for q in questions]
    assert ids[0] == "q_keep"
    assert len(set(ids)) == 4
    assert "q_elsewhere" not in ids


def test_an_edit_keeps_the_set_and_its_question_ids(repo: SupabaseRepository):
    original = _assessment(owner_id="teacher_1", is_shared=True)
    repo.save_assessment(original)

    rows = service.question_rows(original)
    rows[0]["question_text"] = "Solve 3x = 9"
    service.update_assessment(
        original,
        title="Renamed",
        subject=original.subject,
        topic="Algebra",
        rows=rows,
        assessment_type="exercise",
    )

    stored = repo.get_assessment(original.id)
    assert stored is not None
    assert stored.title == "Renamed"
    assert stored.assessment_type.value == "exercise"
    assert stored.created_at == original.created_at
    assert stored.owner_id == "teacher_1"
    assert stored.is_shared is True
    assert [q.id for q in stored.questions] == [q.id for q in original.questions]
    assert stored.questions[0].question_text == "Solve 3x = 9"


def test_marks_survive_an_edit_but_not_a_removed_question(
    repo: SupabaseRepository, db: CascadingSupabase
):
    original = _assessment(owner_id="teacher_1")
    repo.save_assessment(original)
    repo.save_submission(_submission(answers={"q_as_1_1": "x = 4", "q_as_1_2": "x = 3"}))
    for question in original.questions:
        repo.save_grading_result(
            GradingResult(
                submission_id="sub_1", question_id=question.id,
                max_marks=question.max_marks, suggested_score=1, confidence=0.8,
            )
        )

    rows = service.question_rows(original)
    rows[0]["max_marks"] = 4
    del rows[1]
    rows.append({"question_text": "Solve 5x = 10", "model_answer": "x = 2", "max_marks": 2})
    edited = service.update_assessment(
        original,
        title=original.title,
        subject=original.subject,
        topic=original.topic,
        rows=rows,
        assessment_type=original.assessment_type,
    )

    graded = {r["question_id"] for r in db.tables["grading_results"]}
    assert graded == {"q_as_1_1"}
    assert edited.questions[0].id == "q_as_1_1"
    assert edited.questions[1].id not in {"q_as_1_1", "q_as_1_2"}
    assert edited.max_marks == 6


def test_only_the_author_can_edit_a_set():
    def set_owned_by(owner, **kwargs):
        return Assessment(
            title="T", grade_level=10, topic="Algebra", owner_id=owner,
            questions=[Question(question_text="Q", max_marks=1)], **kwargs,
        )

    author = User(id="usr_1", display_name="A", role=Role.STUDENT)
    other = User(id="usr_2", display_name="B", role=Role.STUDENT)

    assert service.can_edit(set_owned_by("usr_1"), author)
    assert not service.can_edit(set_owned_by("usr_1"), other)
    assert not service.can_edit(set_owned_by("usr_1"), None)
    # The unowned demo set belongs to nobody.
    assert not service.can_edit(set_owned_by(None), author)
    assert not service.can_edit(set_owned_by("usr_1", is_archived=True), author)


def _rename(assessment: Assessment, title: str, rows=None) -> Assessment:
    return service.update_assessment(
        assessment,
        title=title,
        subject=assessment.subject,
        topic=assessment.topic,
        rows=rows if rows is not None else service.question_rows(assessment),
        assessment_type=assessment.assessment_type,
    )


def test_an_edit_from_a_stale_form_is_refused(repo: SupabaseRepository, db):
    """Two tabs: B adds a question; A, opened earlier, must not delete it."""
    opened_in_tab_a = _assessment(owner_id="teacher_1")
    repo.save_assessment(opened_in_tab_a)
    rows = service.question_rows(opened_in_tab_a)
    rows.append({"question_text": "Solve 9x = 18", "model_answer": "x = 2", "max_marks": 1})
    _rename(opened_in_tab_a, opened_in_tab_a.title, rows)  # tab B saves first

    with pytest.raises(service.StaleEditError):
        _rename(opened_in_tab_a, "Renamed in tab A")

    stored = repo.get_assessment(opened_in_tab_a.id)
    assert stored.question_count == 3
    assert stored.title == opened_in_tab_a.title


def test_a_deleted_set_cannot_be_saved_back(repo: SupabaseRepository):
    original = _assessment(owner_id="teacher_1")
    repo.save_assessment(original)
    repo.delete_assessment(original.id)

    with pytest.raises(service.StaleEditError):
        _rename(original, "Back from the dead")
    assert repo.get_assessment(original.id) is None


def test_a_student_cannot_remove_a_question_their_teacher_reviewed(
    repo: SupabaseRepository,
):
    original = _assessment(owner_id="usr_s01", student_created=True)
    repo.save_assessment(original)
    repo.save_submission(
        _submission(is_self_study=True, answers={"q_as_1_1": "x = 4", "q_as_1_2": "x = 3"})
    )
    repo.save_grading_result(
        GradingResult(
            submission_id="sub_1", question_id="q_as_1_1", max_marks=2,
            suggested_score=2, confidence=0.9, review_status=ReviewStatus.APPROVED,
        )
    )
    frozen = service.frozen_question_ids(original, "usr_s01")
    assert frozen == {"q_as_1_1", "q_as_1_2"}

    rows = service.question_rows(original)[:1]
    with pytest.raises(ValueError, match="Q2 cannot be removed"):
        service.update_assessment(
            original, title="Renamed", subject=original.subject, topic=original.topic,
            rows=rows, assessment_type=original.assessment_type,
            protected_question_ids=frozen,
        )
    assert repo.get_assessment(original.id).title == original.title


def test_a_refused_question_delete_leaves_the_set_unchanged(
    repo: SupabaseRepository, db, monkeypatch: pytest.MonkeyPatch
):
    """Removals are written first, so a database refusal saves nothing."""
    original = _assessment(owner_id="teacher_1")
    repo.save_assessment(original)
    real_execute = _Query.execute

    def refuse_question_deletes(self: _Query):
        if self._table == "questions" and self._op == "delete":
            raise APIError({"code": "42501", "message": "This work can no longer be changed."})
        return real_execute(self)

    monkeypatch.setattr(_Query, "execute", refuse_question_deletes)
    with pytest.raises(APIError):
        _rename(original, "Renamed", service.question_rows(original)[:1])

    monkeypatch.setattr(_Query, "execute", real_execute)
    stored = repo.get_assessment(original.id)
    assert stored.title == original.title
    assert stored.question_count == 2


def test_a_re_marked_question_scales_its_old_score():
    """8/10 on a question now worth 1 mark is 0.8 of a mark, not 800%."""
    assessment = Assessment(
        id="as_r", title="T", grade_level=10, topic="Algebra",
        questions=[Question(id="q_r", question_text="Q", max_marks=1)],
    )
    submission = _submission(id="sub_r", assessment_id="as_r", student_id="usr_s01")
    old = GradingResult(
        submission_id="sub_r", question_id="q_r", max_marks=10,
        suggested_score=8, confidence=0.9,
    )

    state = attempt_service.build_state(assessment, "usr_s01", [submission], [old])

    standing = state.standings[0]
    assert standing.best_score == pytest.approx(0.8)
    assert standing.best_percentage == pytest.approx(80.0)


def test_demo_mode_deletes_the_work_on_a_deleted_set_or_question(
    monkeypatch: pytest.MonkeyPatch,
):
    from services import state

    assessment = _assessment(owner_id="usr_t1")
    submission = _submission(answers={"q_as_1_1": "x = 4", "q_as_1_2": "x = 3"})
    results = [
        GradingResult(submission_id="sub_1", question_id=q.id, max_marks=2,
                      suggested_score=1, confidence=0.5)
        for q in assessment.questions
    ]
    lists = {"a": [assessment], "s": [submission], "r": results}
    monkeypatch.setattr(state, "get_assessments", lambda: lists["a"])
    monkeypatch.setattr(state, "get_submissions", lambda: lists["s"])
    monkeypatch.setattr(state, "get_grading_results", lambda: lists["r"])
    demo = SessionRepository()

    trimmed = assessment.model_copy(update={"questions": assessment.questions[:1]})
    demo.save_assessment(trimmed)
    assert set(submission.answers) == {"q_as_1_1"}
    assert [r.question_id for r in lists["r"]] == ["q_as_1_1"]

    demo.delete_assessment(assessment.id)
    assert lists["s"] == []
    assert lists["r"] == []


# ---------------------------------------------------------------------------
# My Questions (student)
# ---------------------------------------------------------------------------
def _title_box(at: AppTest, label: str, value: str):
    return next(t for t in at.text_input if t.label == label and t.value == value)


def test_a_student_can_read_and_edit_a_saved_set():
    at = _student_with_a_saved_set()
    assert any(e.label == "See the questions" for e in at.expander)

    _button(at, "Edit").click().run()
    assert not at.exception, at.exception
    assert "Save changes" in _labels(at)

    _title_box(at, "Name *", "Delete me").input("Renamed set").run()
    _button(at, "Save changes").click().run()

    assert not at.exception, at.exception
    assert "Renamed set" in _owned_titles(at)
    assert "Delete me" not in _owned_titles(at)
    assert any("Saved changes" in s.value for s in at.success)
    assert "Save changes" not in _labels(at), "the dialog closes after saving"


def test_cancelling_an_edit_changes_nothing():
    at = _student_with_a_saved_set()
    _button(at, "Edit").click().run()
    _title_box(at, "Name *", "Delete me").input("Not this").run()

    _button(at, "Cancel").click().run()

    assert not at.exception, at.exception
    assert "Delete me" in _owned_titles(at)
    assert "Save changes" not in _labels(at)


def test_an_edit_that_breaks_the_set_is_refused_in_the_dialog():
    at = _student_with_a_saved_set()
    _button(at, "Edit").click().run()
    _title_box(at, "Name *", "Delete me").input("   ").run()

    _button(at, "Save changes").click().run()

    assert not at.exception, at.exception
    assert any("fix the following" in e.value for e in at.error)
    assert "Delete me" in _owned_titles(at)
    assert "Save changes" in _labels(at), "the dialog stays open to fix it"


# ---------------------------------------------------------------------------
# Create Assessment (teacher)
# ---------------------------------------------------------------------------
def _teacher_with_an_assessment(with_work: bool = False) -> AppTest:
    at = _app_as("teacher")
    me = at.session_state["current_user_id"]
    at.session_state["assessments"].append(
        Assessment(
            id="as_mine",
            title="My class test",
            grade_level=10,
            topic="Algebra",
            owner_id=me,
            questions=[
                Question(id="q_mine_1", question_text="Solve 2x = 8",
                         model_answer="x = 4", max_marks=2),
            ],
        )
    )
    if with_work:
        # A roster student's work on the set, as an upload would add it.
        seeded = at.session_state["submissions"][0]
        at.session_state["submissions"].append(
            seeded.model_copy(update={"id": "sub_on_mine", "assessment_id": "as_mine"})
        )
    at.switch_page("pages/create_assessment.py")
    at.run()
    assert not at.exception, at.exception
    return at


def _teacher_titles(at: AppTest):
    return [a.title for a in at.session_state["assessments"]]


def test_a_teacher_gets_edit_and_delete_only_on_their_own_sets():
    at = _teacher_with_an_assessment()
    owned = [
        a for a in at.session_state["assessments"]
        if a.owner_id == at.session_state["current_user_id"]
    ]

    assert _labels(at).count("Edit") == len(owned)
    assert _labels(at).count("Delete") == len(owned)
    assert any("read only" in c.value for c in at.caption)


def test_a_teacher_can_edit_their_assessment():
    at = _teacher_with_an_assessment()
    _button(at, "Edit").click().run()
    assert not at.exception, at.exception

    _title_box(at, "Assessment title *", "My class test").input("Class test v2").run()
    _button(at, "Save changes").click().run()

    assert not at.exception, at.exception
    assert "Class test v2" in _teacher_titles(at)
    saved = next(a for a in at.session_state["assessments"] if a.id == "as_mine")
    assert [q.id for q in saved.questions] == ["q_mine_1"]


def test_a_teacher_delete_takes_two_clicks():
    at = _teacher_with_an_assessment()

    _button(at, "Delete").click().run()
    assert "My class test" in _teacher_titles(at), "one click must not delete"

    _button(at, "Yes, delete").click().run()

    assert not at.exception, at.exception
    assert "My class test" not in _teacher_titles(at)
    assert any("Deleted" in s.value for s in at.success)


def test_editing_a_set_with_handed_in_work_warns_first():
    at = _teacher_with_an_assessment(with_work=True)
    _button(at, "Edit").click().run()

    assert not at.exception, at.exception
    assert any("1 piece of work has been handed in" in w.value for w in at.warning)


def test_deleting_a_set_with_handed_in_work_says_what_goes_with_it():
    at = _teacher_with_an_assessment(with_work=True)
    _button(at, "Delete").click().run()

    assert not at.exception, at.exception
    assert any("1 piece of student work" in c.value for c in at.caption)
