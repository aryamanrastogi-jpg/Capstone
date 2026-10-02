"""Regression tests for grading / review logic fixes.

BUG-005 teacher feedback reaches the student once finalised.
BUG-007 flagged results never count as a score.
BUG-008 flagged results stay visible in the teacher's to-do.
BUG-009 mark mismatch denominator and boundary.
BUG-026 recent-work labels use the real question number.
"""

from __future__ import annotations

import pytest

from models import Assessment, GradingResult, Question, ReviewStatus, Submission
from services import analytics_service as analytics
from services import attempt_service
from services.grading_service import apply_teacher_decision, student_safe_view

STUDENT = "usr_student"


def _assessment(marks=(3,)) -> Assessment:
    return Assessment(
        title="Algebra",
        grade_level=9,
        topic="Algebra",
        questions=[
            Question(
                id=f"q{i}",
                question_text=f"Solve x + {i} = {i + 7}.",
                model_answer="x = 7",
                max_marks=m,
            )
            for i, m in enumerate(marks, start=1)
        ],
    )


def _submission(assessment, number=1, sid=None, teacher=None) -> Submission:
    return Submission(
        id=sid or f"sub_{number}",
        assessment_id=assessment.id,
        student_identifier="S-1",
        student_id=STUDENT,
        submission_text="answers",
        attempt_number=number,
        teacher_awarded_score=teacher,
    )


def _result(sub_id, q, score, confidence=0.9) -> GradingResult:
    return GradingResult(
        submission_id=sub_id,
        question_id=q.id,
        max_marks=q.max_marks,
        suggested_score=score,
        confidence=confidence,
        student_feedback="AI feedback.",
    )


# ---------------------------------------------------------------- BUG-005
def test_teacher_feedback_reaches_student_once_finalised():
    a = _assessment()
    r = _result("s", a.questions[0], 2)
    apply_teacher_decision(r, ReviewStatus.EDITED, score=2, feedback="Revisit step 2.")
    view = student_safe_view(r, a.questions[0])
    assert view["teacher_feedback"] == "Revisit step 2."
    assert "x = 7" not in str(view)


def test_no_teacher_feedback_before_finalised_or_when_flagged():
    a = _assessment()
    pending = _result("s", a.questions[0], 2)
    assert student_safe_view(pending, a.questions[0])["teacher_feedback"] is None
    flagged = apply_teacher_decision(_result("s", a.questions[0], 2), ReviewStatus.FLAGGED)
    assert student_safe_view(flagged, a.questions[0])["teacher_feedback"] is None


# ---------------------------------------------------------------- BUG-007
def test_flagged_full_marks_does_not_settle_or_complete():
    a = _assessment()
    sub = _submission(a)
    r = apply_teacher_decision(_result(sub.id, a.questions[0], 3), ReviewStatus.FLAGGED)
    state = attempt_service.build_state(a, STUDENT, [sub], [r])
    standing = state.standings[0]
    assert standing.best_score is None
    assert not standing.is_settled
    assert not state.is_complete
    assert state.progress_fraction == 0.0
    # The flagged go still used an attempt.
    assert standing.attempts_used == 1


def test_flagged_result_does_not_beat_an_earlier_real_score():
    a = _assessment()
    s1, s2 = _submission(a, 1), _submission(a, 2)
    first = _result(s1.id, a.questions[0], 1)
    second = apply_teacher_decision(_result(s2.id, a.questions[0], 3), ReviewStatus.FLAGGED)
    state = attempt_service.build_state(a, STUDENT, [s1, s2], [first, second])
    assert state.standings[0].best_score == 1
    assert not state.standings[0].is_settled


def test_flagged_attempt_history_entry_is_not_settled():
    a = _assessment()
    sub = _submission(a)
    r = apply_teacher_decision(_result(sub.id, a.questions[0], 3), ReviewStatus.FLAGGED)
    history = attempt_service.attempt_history(a, a.questions[0].id, [sub], [r])
    assert history[0]["is_flagged"] is True
    assert history[0]["is_settled"] is False


def test_flagged_is_flagged_in_safe_view():
    a = _assessment()
    r = apply_teacher_decision(_result("s", a.questions[0], 3), ReviewStatus.FLAGGED)
    assert student_safe_view(r, a.questions[0])["is_flagged"] is True


# ---------------------------------------------------------------- BUG-008
def test_dashboard_metrics_count_flagged():
    a = _assessment()
    sub = _submission(a)
    r = apply_teacher_decision(_result(sub.id, a.questions[0], 1), ReviewStatus.FLAGGED)
    metrics = analytics.dashboard_metrics([a], [sub], [r])
    assert metrics["flagged"] == 1


# ---------------------------------------------------------------- BUG-009
def test_mismatch_gap_of_exactly_threshold_is_not_flagged():
    a = _assessment(marks=(10, 10))
    sub = _submission(a, teacher=10)
    rs = [_result(sub.id, q, 6.5) for q in a.questions]  # AI 65%, teacher 50%
    assert analytics.mark_mismatches([sub], rs, [a]).empty


def test_mismatch_gap_just_over_threshold_is_flagged():
    a = _assessment(marks=(10, 10))
    sub = _submission(a, teacher=10)
    rs = [_result(sub.id, a.questions[0], 6.5), _result(sub.id, a.questions[1], 6.6)]
    assert not analytics.mark_mismatches([sub], rs, [a]).empty


def test_mismatch_uses_whole_paper_marks_for_teacher_mark_on_reattempt():
    a = _assessment(marks=(10, 10))
    sub = _submission(a, number=2, teacher=16)
    rs = [_result(sub.id, a.questions[1], 8)]  # only Q2 regraded
    frame = analytics.mark_mismatches([sub], rs, [a], threshold_pct=-1)
    row = frame.iloc[0]
    assert row["teacher_pct"] == 80.0
    assert row["max_marks"] == 20
    assert row["ai_max_marks"] == 10
    assert row["gap"] == 0.0
    # And with the default threshold it is not surfaced at all.
    assert analytics.mark_mismatches([sub], rs, [a]).empty


# ---------------------------------------------------------------- BUG-026
@pytest.mark.parametrize("index,expected", [(0, 1), (1, 2), (2, 3)])
def test_question_number_is_position_in_the_set(index, expected):
    a = _assessment(marks=(1, 2, 3))
    assert attempt_service.question_number(a, a.questions[index]) == expected
