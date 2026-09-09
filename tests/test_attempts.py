"""Tests for the attempt loop.

The loop is the thing a general chatbot cannot do: it remembers every previous
attempt at the same question, drops the ones you have settled, and stops you
grinding forever on the ones you have not.
"""

from __future__ import annotations

import pytest

from models import Assessment, GradingResult, Question, Submission
from models.attempt import SETTLE_FRACTION, is_settling_score
from services import attempt_service
from services.attempt_service import (
    MAX_ATTEMPTS,
    attempt_history,
    attempts_for,
    build_state,
    outstanding_questions,
    settled_questions,
)

STUDENT = "usr_student"


@pytest.fixture
def assessment() -> Assessment:
    return Assessment(
        title="Algebra worksheet",
        grade_level=9,
        topic="Linear Equations",
        questions=[
            Question(
                id="q1",
                question_text="Solve 3x + 7 = 22.",
                model_answer="x = 5.",
                max_marks=3,
            ),
            Question(
                id="q2",
                question_text="Solve 2y = 10.",
                model_answer="y = 5.",
                max_marks=2,
            ),
        ],
    )


def _attempt(assessment, number, answers):
    return Submission(
        id=f"sub_{number}",
        assessment_id=assessment.id,
        student_identifier="S-1",
        student_id=STUDENT,
        submission_text="answers",
        answers=answers,
        attempt_number=number,
    )


def _result(submission_id, question_id, score, max_marks):
    return GradingResult(
        submission_id=submission_id,
        question_id=question_id,
        max_marks=max_marks,
        suggested_score=score,
        confidence=0.8,
    )


# ---------------------------------------------------------------------------
# 1. A fresh set
# ---------------------------------------------------------------------------
def test_a_set_never_attempted_has_everything_outstanding(assessment):
    state = build_state(assessment, STUDENT, [], [])
    assert not state.has_started
    assert state.attempts_used == 0
    assert state.next_attempt_number == 1
    assert len(state.outstanding) == 2
    assert not state.settled
    assert not state.is_complete
    assert state.can_attempt


# ---------------------------------------------------------------------------
# 2. Settling drops a question out
# ---------------------------------------------------------------------------
def test_full_marks_settles_a_question(assessment):
    subs = [_attempt(assessment, 1, {"q1": "x = 5", "q2": "y = 3"})]
    results = [_result("sub_1", "q1", 3, 3), _result("sub_1", "q2", 0, 2)]

    state = build_state(assessment, STUDENT, subs, results)

    assert state.outstanding_question_ids == ["q2"]
    assert [s.question_id for s in state.settled] == ["q1"]
    assert [q.id for q in outstanding_questions(assessment, state)] == ["q2"]
    assert [q.id for q in settled_questions(assessment, state)] == ["q1"]


def test_marks_below_the_threshold_do_not_settle_a_question(assessment):
    """1.5 out of 3 is half the marks - nowhere near done."""
    subs = [_attempt(assessment, 1, {"q1": "x = 5"})]
    results = [_result("sub_1", "q1", 1.5, 3)]

    state = build_state(assessment, STUDENT, subs, results)

    standing = attempt_service.standing_for(state, "q1")
    assert standing.best_score == 1.5
    assert not standing.is_settled
    assert "q1" in state.outstanding_question_ids


def test_a_settled_question_stays_settled_after_a_worse_later_attempt(assessment):
    """Best result wins, not the latest.

    A student who got it right and then fumbled a re-run has still shown they
    can do it, so the question must not reopen.
    """
    subs = [
        _attempt(assessment, 1, {"q1": "x = 5", "q2": "y = 5"}),
        _attempt(assessment, 2, {"q1": "no idea"}),
    ]
    results = [
        _result("sub_1", "q1", 3, 3),
        _result("sub_1", "q2", 2, 2),
        _result("sub_2", "q1", 0, 3),
    ]

    state = build_state(assessment, STUDENT, subs, results)

    assert state.is_complete
    assert attempt_service.standing_for(state, "q1").best_score == 3


def test_the_loop_completes_when_every_question_is_settled(assessment):
    subs = [
        _attempt(assessment, 1, {"q1": "x = 5", "q2": "wrong"}),
        _attempt(assessment, 2, {"q2": "y = 5"}),
    ]
    results = [
        _result("sub_1", "q1", 3, 3),
        _result("sub_1", "q2", 0, 2),
        _result("sub_2", "q2", 2, 2),
    ]

    state = build_state(assessment, STUDENT, subs, results)

    assert state.is_complete
    assert not state.can_attempt
    assert state.progress_fraction == 1.0
    assert state.attempts_used == 2


def test_best_on_attempt_records_which_go_settled_it(assessment):
    subs = [
        _attempt(assessment, 1, {"q1": "wrong"}),
        _attempt(assessment, 2, {"q1": "x = 5"}),
    ]
    results = [_result("sub_1", "q1", 1, 3), _result("sub_2", "q1", 3, 3)]

    state = build_state(assessment, STUDENT, subs, results)
    standing = attempt_service.standing_for(state, "q1")

    assert standing.best_on_attempt == 2
    assert standing.attempts_used == 2


# ---------------------------------------------------------------------------
# 3. The cap
# ---------------------------------------------------------------------------
def test_the_attempt_cap_stops_the_loop(assessment):
    subs = []
    results = []
    for number in range(1, MAX_ATTEMPTS + 1):
        subs.append(_attempt(assessment, number, {"q1": "wrong", "q2": "wrong"}))
        results.append(_result(f"sub_{number}", "q1", 0, 3))
        results.append(_result(f"sub_{number}", "q2", 0, 2))

    state = build_state(assessment, STUDENT, subs, results)

    assert state.attempts_used == MAX_ATTEMPTS
    assert state.attempts_remaining == 0
    assert state.is_exhausted
    assert not state.can_attempt
    assert not state.is_complete


def test_a_finished_set_is_not_reported_as_exhausted(assessment):
    """Running out of attempts and finishing are different endings."""
    subs = [_attempt(assessment, 1, {"q1": "x = 5", "q2": "y = 5"})]
    results = [_result("sub_1", "q1", 3, 3), _result("sub_1", "q2", 2, 2)]

    state = build_state(assessment, STUDENT, subs, results, max_attempts=1)

    assert state.attempts_remaining == 0
    assert state.is_complete
    assert not state.is_exhausted


# ---------------------------------------------------------------------------
# 4. Scoping
# ---------------------------------------------------------------------------
def test_another_students_attempts_are_not_counted(assessment):
    mine = _attempt(assessment, 1, {"q1": "x = 5"})
    theirs = Submission(
        id="sub_other",
        assessment_id=assessment.id,
        student_identifier="S-2",
        student_id="usr_someone_else",
        submission_text="theirs",
        answers={"q1": "x = 5"},
        attempt_number=1,
    )
    results = [_result("sub_1", "q1", 1, 3), _result("sub_other", "q1", 3, 3)]

    state = build_state(assessment, STUDENT, [mine, theirs], results)

    assert state.attempts_used == 1
    assert attempt_service.standing_for(state, "q1").best_score == 1
    assert not state.is_complete, "another student's success must not settle mine"


def test_attempts_for_another_set_are_not_counted(assessment):
    other_set = Assessment(
        title="Other",
        grade_level=9,
        topic="Ratio",
        questions=[Question(question_text="Share 20.", model_answer="10", max_marks=2)],
    )
    mine = _attempt(assessment, 1, {"q1": "x = 5"})
    elsewhere = Submission(
        assessment_id=other_set.id,
        student_identifier="S-1",
        student_id=STUDENT,
        submission_text="elsewhere",
        attempt_number=1,
    )

    assert len(attempts_for(STUDENT, assessment.id, [mine, elsewhere])) == 1


def test_attempts_are_ordered_oldest_first(assessment):
    subs = [_attempt(assessment, 3, {}), _attempt(assessment, 1, {}), _attempt(assessment, 2, {})]
    assert [s.attempt_number for s in attempts_for(STUDENT, assessment.id, subs)] == [1, 2, 3]


# ---------------------------------------------------------------------------
# 5. History, for comparing attempts
# ---------------------------------------------------------------------------
def test_attempt_history_lists_every_go_at_one_question(assessment):
    subs = [
        _attempt(assessment, 1, {"q1": "x = 6", "q2": "y = 5"}),
        _attempt(assessment, 2, {"q1": "x = 5"}),
    ]
    results = [
        _result("sub_1", "q1", 1, 3),
        _result("sub_1", "q2", 2, 2),
        _result("sub_2", "q1", 3, 3),
    ]

    history = attempt_history(assessment, "q1", subs, results)

    assert [h["attempt_number"] for h in history] == [1, 2]
    assert [h["answer"] for h in history] == ["x = 6", "x = 5"]
    assert [h["score"] for h in history] == [1, 3]
    assert [h["is_settled"] for h in history] == [False, True]


def test_attempt_history_skips_attempts_that_did_not_cover_the_question(assessment):
    """q2 settled on attempt 1, so attempt 2 never touched it."""
    subs = [
        _attempt(assessment, 1, {"q1": "wrong", "q2": "y = 5"}),
        _attempt(assessment, 2, {"q1": "x = 5"}),
    ]
    results = [
        _result("sub_1", "q1", 0, 3),
        _result("sub_1", "q2", 2, 2),
        _result("sub_2", "q1", 3, 3),
    ]

    history = attempt_history(assessment, "q2", subs, results)

    assert [h["attempt_number"] for h in history] == [1]


# ---------------------------------------------------------------------------
# 7. The settle threshold
#
# 80% of the marks, not 100%. The value is chosen around how the marks round -
# see SETTLE_FRACTION - so the tests below pin the boundary on the question
# sizes actually in use rather than only the tidy percentages.
# ---------------------------------------------------------------------------
def test_eighty_percent_or_better_settles_a_question():
    assert is_settling_score(8, 10)
    assert is_settling_score(4, 5)
    assert is_settling_score(10, 10)


def test_below_eighty_percent_does_not_settle():
    assert not is_settling_score(7.5, 10)
    assert not is_settling_score(3.5, 5)
    assert not is_settling_score(0, 3)


def test_a_correct_but_differently_worded_answer_now_settles():
    """The case that drove the threshold down from full marks.

    The rule-based grader gives 2.5 out of 3 for a fully correct answer,
    because it weighs wording against the marking criteria as well as the
    numbers. At full marks - and at 90%, since 90% of 3 rounds up to needing
    3.0 - that answer never settled and the loop could not finish.
    """
    assert is_settling_score(2.5, 3), "2.5/3 is 83%"
    assert is_settling_score(3.5, 4), "3.5/4 is 87.5%"


def test_the_threshold_is_still_strict_on_two_mark_questions():
    """Honest about where half-mark rounding still bites.

    80% of 2 is 1.6, and the nearest reachable scores are 1.5 and 2.0 - so a
    2-mark question still has to be fully right. Nothing to fix here; it is
    what a 2-mark question means.
    """
    assert not is_settling_score(1.5, 2)
    assert is_settling_score(2, 2)


def test_a_zero_mark_question_never_settles():
    assert not is_settling_score(0, 0)


def test_the_standing_and_the_history_agree_on_settling(assessment):
    """One definition, read from both places."""
    subs = [_attempt(assessment, 1, {"q1": "x = 5"})]
    results = [_result("sub_1", "q1", 3, 3)]

    state = build_state(assessment, STUDENT, subs, results)
    history = attempt_history(assessment, "q1", subs, results)

    assert attempt_service.standing_for(state, "q1").is_settled
    assert history[0]["is_settled"]
