"""Teacher review decisions must reach the database, and survive later edits.

Drives `SupabaseRepository` through `FakeSupabase` (see test_repository.py) and
asserts on the rows written. The fake here also models the ON DELETE CASCADE
from `questions` to `submission_answers` and `grading_results`, because that
cascade is exactly how a re-saved assessment used to erase approved marks.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from models import GradingResult, Question, ReviewStatus, SubmissionStatus
from services import assessment_service as service
from services.grading_service import apply_teacher_decision
from services.repository import SupabaseRepository, set_repository
from tests.test_repository import FakeSupabase, _assessment, _Query, _submission


class _CascadingQuery(_Query):
    def execute(self):  # type: ignore[override]
        response = super().execute()
        if self._table == "questions" and self._op == "delete":
            live = {q["id"] for q in self._db.tables["questions"]}
            for child in ("submission_answers", "grading_results"):
                self._db.tables[child] = [
                    r for r in self._db.tables[child] if r["question_id"] in live
                ]
        return response


class CascadingSupabase(FakeSupabase):
    def table(self, name: str) -> _Query:
        return _CascadingQuery(self, name)


@pytest.fixture()
def db() -> CascadingSupabase:
    return CascadingSupabase()


@pytest.fixture()
def repo(db: CascadingSupabase) -> Iterator[SupabaseRepository]:
    repository = SupabaseRepository(db)
    set_repository(repository)
    yield repository
    set_repository(None)


def _seed(repo: SupabaseRepository) -> None:
    repo.save_assessment(_assessment())
    repo.save_submission(
        _submission(answers={"q_as_1_1": "x = 4", "q_as_1_2": "x = 2"})
    )
    for qid, max_marks in (("q_as_1_1", 2), ("q_as_1_2", 3)):
        service.save_grading_result(
            GradingResult(
                submission_id="sub_1", question_id=qid, max_marks=max_marks,
                suggested_score=1, confidence=0.6, student_feedback="Check it.",
            )
        )


def _row(db: FakeSupabase, qid: str) -> dict[str, Any]:
    return next(r for r in db.tables["grading_results"] if r["question_id"] == qid)


def test_fresh_results_are_written_awaiting_review(repo, db) -> None:
    _seed(repo)
    assert len(db.tables["grading_results"]) == 2
    assert all(r["review_status"] == "awaiting_review" for r in db.tables["grading_results"])
    assert all(r["teacher_approved_score"] is None for r in db.tables["grading_results"])
    assert db.tables["submissions"][0]["status"] == "graded"


def test_approve_edit_and_flag_are_each_written(repo, db) -> None:
    _seed(repo)
    first, second = repo.list_grading_results("sub_1")

    service.save_grading_result(
        apply_teacher_decision(first, ReviewStatus.APPROVED,
                               score=first.suggested_score,
                               feedback=first.student_feedback)
    )
    row = _row(db, first.question_id)
    assert row["review_status"] == "approved"
    assert row["teacher_approved_score"] == 1

    service.save_grading_result(
        apply_teacher_decision(second, ReviewStatus.EDITED, score=2.5, feedback="Nearly.")
    )
    row = _row(db, second.question_id)
    assert (row["review_status"], row["teacher_approved_score"],
            row["teacher_approved_feedback"]) == ("edited", 2.5, "Nearly.")
    assert db.tables["submissions"][0]["status"] == "reviewed"

    service.save_grading_result(apply_teacher_decision(second, ReviewStatus.FLAGGED))
    row = _row(db, second.question_id)
    assert row["review_status"] == "flagged"
    assert row["teacher_approved_score"] is None
    assert row["teacher_approved_feedback"] is None
    # A flagged question keeps the submission out of "reviewed".
    assert db.tables["submissions"][0]["status"] == "graded"
    assert len(db.tables["grading_results"]) == 2


def test_a_decision_reloads_intact(repo) -> None:
    _seed(repo)
    result = repo.list_grading_results("sub_1")[0]
    service.save_grading_result(
        apply_teacher_decision(result, ReviewStatus.EDITED, score=0.5, feedback="Show working.")
    )
    reloaded = service.get_grading_result("sub_1", result.question_id)
    assert reloaded is not None
    assert reloaded.final_score == 0.5
    assert reloaded.final_feedback == "Show working."
    assert service.get_submission("sub_1").status is SubmissionStatus.GRADED


def test_resaving_an_assessment_keeps_answers_and_approved_marks(repo, db) -> None:
    """Regression: questions were deleted-then-inserted, cascading every result away."""
    _seed(repo)
    result = repo.list_grading_results("sub_1")[0]
    service.save_grading_result(apply_teacher_decision(result, ReviewStatus.APPROVED))

    service.set_shared("as_1", True)

    assert len(db.tables["grading_results"]) == 2
    assert len(db.tables["submission_answers"]) == 2
    assert _row(db, result.question_id)["review_status"] == "approved"


def test_removing_a_question_removes_only_that_question(repo, db) -> None:
    _seed(repo)
    trimmed = _assessment(questions=[_assessment().questions[0]])
    repo.save_assessment(trimmed)

    assert [q["id"] for q in db.tables["questions"]] == ["q_as_1_1"]
    assert [r["question_id"] for r in db.tables["grading_results"]] == ["q_as_1_1"]


def test_reordering_questions_writes_new_positions(repo, db) -> None:
    _seed(repo)
    original = _assessment().questions
    repo.save_assessment(_assessment(questions=[original[1], original[0]]))

    positions = {q["id"]: q["position"] for q in db.tables["questions"]}
    assert positions == {"q_as_1_2": 0, "q_as_1_1": 1}
    assert [q.id for q in repo.get_assessment("as_1").questions] == ["q_as_1_2", "q_as_1_1"]
    assert len(db.tables["grading_results"]) == 2


def test_adding_a_question_keeps_existing_results(repo, db) -> None:
    _seed(repo)
    extra = Question(id="q_as_1_3", question_text="Solve 3x = 9", model_answer="x = 3",
                     max_marks=1)
    repo.save_assessment(_assessment(questions=[*_assessment().questions, extra]))

    assert len(db.tables["questions"]) == 3
    assert len(db.tables["grading_results"]) == 2
