"""A handed-in mock exam is saved as the student's work.

It used to live in session state only, so it never showed in My Progress or
Study Camp and was gone on refresh. Now each paper is saved as self-study work
on the sets its questions came from, labelled as a mock exam, which keeps it
out of the attempt loop.
"""

from __future__ import annotations

from typing import Iterator

import pandas as pd
import pytest

from models import Assessment, Question, Role, User
from models.submission import MOCK_EXAM_SOURCE
from services import analytics_service as analytics
from services import assessment_service as service
from services import attempt_service
from services import mock_exam_service as exams
from services.repository import SupabaseRepository, set_repository
from tests.test_form_page_fixes import _app_as, _button
from tests.test_repository import FakeSupabase

STUDENT = User(id="usr_s01", display_name="S-1101", role=Role.STUDENT)


def _own_set(set_id: str, topic: str, *questions: tuple) -> Assessment:
    return Assessment(
        id=set_id,
        title=f"{topic} sheet",
        grade_level=10,
        topic=topic,
        owner_id=STUDENT.id,
        student_created=True,
        questions=[
            Question(id=qid, question_text=text, model_answer=answer, max_marks=marks)
            for qid, text, answer, marks in questions
        ],
    )


SETS = [
    _own_set(
        "as_lin", "Linear Equations",
        ("q_lin_1", "Solve 2x + 3 = 11.", "x = 4", 2),
        ("q_lin_2", "Solve 5 - x = 2.", "x = 3", 2),
    ),
    _own_set("as_rat", "Ratio and Proportion", ("q_rat_1", "Share 45 in the ratio 2 : 3.", "18 and 27", 3)),
]


@pytest.fixture()
def db(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSupabase]:
    from services import auth_service

    monkeypatch.setattr(auth_service, "current_user", lambda: STUDENT)
    fake = FakeSupabase()
    repository = SupabaseRepository(fake)
    for assessment in SETS:
        repository.save_assessment(assessment)
    set_repository(repository)
    yield fake
    set_repository(None)


def _handed_in(frame: pd.DataFrame | None = None):
    exam = exams.build_exam(
        STUDENT.id, SETS, ["Linear Equations", "Ratio and Proportion"],
        frame if frame is not None else pd.DataFrame(columns=analytics.FRAME_COLUMNS),
        question_count=3,
    )
    answers = {item.question.id: "x = 4" for item in exam.items}
    return exams.submit_exam(exam, answers)


def test_a_paper_is_saved_once_per_set_as_mock_exam_work(db: FakeSupabase):
    exam = _handed_in()

    saved = exams.save_to_history(exam, "S-1101", SETS)

    rows = db.tables["submissions"]
    assert sorted(r["assessment_id"] for r in rows) == ["as_lin", "as_rat"]
    assert all(r["uploaded_filename"] == MOCK_EXAM_SOURCE for r in rows)
    assert all(r["is_self_study"] and r["student_id"] == STUDENT.id for r in rows)
    assert sorted(r["id"] for r in rows) == sorted(saved)
    results = db.tables["grading_results"]
    assert len(results) == len(exam.items)
    assert {r["submission_id"] for r in results} == set(saved)
    answers = db.tables["submission_answers"]
    assert {a["question_id"] for a in answers} == {i.question.id for i in exam.items}

    # Saving again changes nothing.
    assert exams.save_to_history(exam, "S-1101", SETS) == saved
    assert len(db.tables["submissions"]) == 2


def test_a_saved_mock_uses_no_attempts_but_counts_in_progress(db: FakeSupabase):
    exam = _handed_in()
    exams.save_to_history(exam, "S-1101", SETS)

    submissions = service.list_submissions(student_id=STUDENT.id)
    results = service.list_grading_results(student_id=STUDENT.id)
    assert len(submissions) == 2 and all(s.is_mock_exam for s in submissions)

    for assessment in SETS:
        assert attempt_service.attempts_for(STUDENT.id, assessment.id, submissions) == []
        state = attempt_service.build_state(assessment, STUDENT.id, submissions, results)
        assert state.attempts_used == 0
        assert not state.settled

    frame = analytics.student_dataframe(STUDENT.id, results, SETS, submissions)
    assert len(frame) == len(exam.items)
    assert set(frame["assessment_type"]) == {"Mock Exam"}
    assert set(frame["topic"]) == {"Linear Equations", "Ratio and Proportion"}
    assert all(title.startswith("Mock exam: ") for title in frame["assessment_title"])


def test_a_failed_save_leaves_nothing_behind(db: FakeSupabase, monkeypatch: pytest.MonkeyPatch):
    exam = _handed_in()
    real_save = service.save_grading_result
    calls = {"n": 0}

    def flaky(result):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("the database is down")
        return real_save(result)

    monkeypatch.setattr(service, "save_grading_result", flaky)

    with pytest.raises(RuntimeError):
        exams.save_to_history(exam, "S-1101", SETS)

    assert db.tables["submissions"] == []
    assert exam.saved_submission_ids == []


def test_the_before_score_is_fixed_when_the_paper_is_set():
    """Once saved, the mock is part of the history - it must not count in its
    own "before"."""
    history = pd.DataFrame(
        [{"topic": "Linear Equations", "percentage": 40.0},
         {"topic": "Ratio and Proportion", "percentage": 60.0}]
    )
    exam = _handed_in(history)
    with_the_mock_in_it = pd.concat(
        [history, pd.DataFrame([{"topic": "Linear Equations", "percentage": 100.0}])]
    )

    summary = exams.score_summary(exam, with_the_mock_in_it)

    befores = {t["topic"]: t["before"] for t in summary["topics"]}
    assert befores == {"Linear Equations": 40.0, "Ratio and Proportion": 60.0}


def test_the_mock_exam_page_saves_the_result():
    at = _app_as("student")
    me = at.session_state["current_user_id"]
    before = [s.id for s in at.session_state["submissions"] if s.student_id == me]
    at.switch_page("pages/mock_exam.py")
    at.run()
    assert not at.exception, at.exception

    _button(at, "Start the mock exam").click().run()
    at.text_area[0].input("x = 5").run()
    _button(at, "Submit my answers").click().run()
    _button(at, "Submit anyway").click().run()

    assert not at.exception, at.exception
    assert any("Saved to your work as a mock exam" in c.value for c in at.caption)
    mine = [s for s in at.session_state["submissions"] if s.student_id == me]
    new = [s for s in mine if s.id not in before]
    assert new and all(s.is_mock_exam and s.is_self_study for s in new)

    # My Progress counts every question on the paper as mock exam work.
    from services import state

    paper = at.session_state[state.MOCK_EXAM]
    at.switch_page("pages/my_progress.py")
    at.run()
    assert not at.exception, at.exception
    by_type = next(d.value for d in at.dataframe if "Type" in d.value.columns)
    mock_questions = int(by_type.loc[by_type["Type"] == "Mock Exam", "Questions"].iloc[0])
    assert mock_questions >= len(paper.items)
