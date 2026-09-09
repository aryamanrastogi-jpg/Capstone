"""Round-trip tests for the Supabase row mappers.

Every model that will be persisted has to survive the trip to rows and back
unchanged. An asymmetry here does not fail loudly - it shows up weeks later as
a field that quietly resets on reload - so each pair is asserted directly.

These tests touch no network and no Streamlit: the mappers are pure functions,
which is why they are worth having as a separate layer at all.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from models import (
    Assessment,
    AssessmentType,
    ErrorItem,
    ErrorType,
    GradingResult,
    Question,
    ReviewStatus,
    Role,
    StudyCamp,
    StudySession,
    Subject,
    Submission,
    SubmissionStatus,
    User,
)
from services import mappers


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture()
def assessment() -> Assessment:
    return Assessment(
        id="as_test01",
        title="Linear Equations",
        subject=Subject.MATHEMATICS,
        curriculum="Cambridge IGCSE",
        grade_level=10,
        topic="Algebra",
        assessment_type=AssessmentType.HOMEWORK,
        created_at=datetime(2026, 3, 4, 9, 30),
        owner_id="usr_teacher01",
        questions=[
            Question(
                id="q_1",
                question_text="Solve 2x + 5 = 17",
                model_answer="x = 6",
                marking_criteria="1 mark rearranging, 1 mark answer",
                max_marks=2,
            ),
            Question(
                id="q_2",
                question_text="Solve 3(x - 1) = 12",
                model_answer="x = 5",
                max_marks=3,
            ),
        ],
    )


@pytest.fixture()
def submission() -> Submission:
    return Submission(
        id="sub_test01",
        assessment_id="as_test01",
        student_identifier="S-1102",
        submission_text="Q1. x = 6\n\nQ2. x = 4",
        answers={"q_1": "x = 6", "q_2": ""},
        uploaded_filename="homework.pdf",
        submitted_at=datetime(2026, 3, 5, 14, 0),
        status=SubmissionStatus.GRADED,
        student_id="usr_s02",
        is_self_study=True,
        teacher_awarded_score=4.0,
    )


# --------------------------------------------------------------------------
# Assessment
# --------------------------------------------------------------------------
def test_assessment_round_trips(assessment: Assessment) -> None:
    row, question_rows = mappers.assessment_to_rows(assessment)
    restored = mappers.assessment_from_rows(row, question_rows)

    assert restored.id == assessment.id
    assert restored.title == assessment.title
    assert restored.subject is assessment.subject
    assert restored.grade_level == assessment.grade_level
    assert restored.topic == assessment.topic
    assert restored.assessment_type is assessment.assessment_type
    assert restored.owner_id == assessment.owner_id
    assert restored.student_created == assessment.student_created
    assert restored.created_at == assessment.created_at
    assert restored.max_marks == assessment.max_marks
    assert [q.id for q in restored.questions] == [q.id for q in assessment.questions]
    assert [q.model_answer for q in restored.questions] == [
        q.model_answer for q in assessment.questions
    ]


def test_question_order_survives_shuffled_rows(assessment: Assessment) -> None:
    """Rows come back in no guaranteed order; `position` is what restores it."""
    row, question_rows = mappers.assessment_to_rows(assessment)
    restored = mappers.assessment_from_rows(row, list(reversed(question_rows)))

    assert [q.id for q in restored.questions] == ["q_1", "q_2"]


def test_question_rows_carry_their_position(assessment: Assessment) -> None:
    _, question_rows = mappers.assessment_to_rows(assessment)

    assert [r["position"] for r in question_rows] == [0, 1]
    assert all(r["assessment_id"] == "as_test01" for r in question_rows)


def test_student_question_view_row_yields_no_model_answer() -> None:
    """A row from public.student_questions has no answer columns at all.

    This is the mapper half of the academic-integrity rule: even handed a row
    the view produced, nothing reconstructs a model answer out of thin air.
    """
    view_row = {
        "id": "q_1",
        "assessment_id": "as_test01",
        "position": 0,
        "question_text": "Solve 2x + 5 = 17",
        "max_marks": 2,
    }

    question = mappers.question_from_row(view_row)

    assert question.question_text == "Solve 2x + 5 = 17"
    assert question.model_answer == ""
    assert question.marking_criteria == ""
    assert question.has_model_answer is False


def test_assessment_built_from_view_rows_is_not_gradable(
    assessment: Assessment,
) -> None:
    """Marking cannot start from what a student is allowed to read."""
    row, question_rows = mappers.assessment_to_rows(assessment)
    view_rows = [
        {k: v for k, v in r.items() if k not in ("model_answer", "marking_criteria")}
        for r in question_rows
    ]

    restored = mappers.assessment_from_rows(row, view_rows)

    assert restored.is_gradable is False
    assert len(restored.questions_missing_model_answers) == 2


# --------------------------------------------------------------------------
# Submission
# --------------------------------------------------------------------------
def test_submission_round_trips(submission: Submission) -> None:
    row, answer_rows = mappers.submission_to_rows(submission)
    restored = mappers.submission_from_rows(row, answer_rows)

    assert restored.id == submission.id
    assert restored.assessment_id == submission.assessment_id
    assert restored.student_identifier == submission.student_identifier
    assert restored.submission_text == submission.submission_text
    assert restored.answers == submission.answers
    assert restored.uploaded_filename == submission.uploaded_filename
    assert restored.submitted_at == submission.submitted_at
    assert restored.status is submission.status
    assert restored.student_id == submission.student_id
    assert restored.is_self_study == submission.is_self_study
    assert restored.teacher_awarded_score == submission.teacher_awarded_score


def test_blank_answer_is_stored_but_unattempted_question_is_absent(
    submission: Submission,
) -> None:
    """"Left blank" and "never attempted" are different facts about a topic."""
    _, answer_rows = mappers.submission_to_rows(submission)
    by_question = {r["question_id"]: r["answer_text"] for r in answer_rows}

    assert by_question == {"q_1": "x = 6", "q_2": ""}
    assert "q_3" not in by_question

    restored = mappers.submission_from_rows(*mappers.submission_to_rows(submission))
    assert restored.answer_for("q_2") == ""
    assert restored.answer_for("q_3") == ""


def test_legacy_unsegmented_submission_round_trips() -> None:
    """A submission with no per-question answers still restores as one block."""
    legacy = Submission(
        id="sub_legacy",
        assessment_id="as_test01",
        student_identifier="S-1101",
        submission_text="all my working, one block",
        student_id="usr_s01",
    )

    restored = mappers.submission_from_rows(*mappers.submission_to_rows(legacy))

    assert restored.is_segmented is False
    assert restored.answer_for("q_1") == "all my working, one block"


def test_numeric_columns_arriving_as_strings_are_parsed() -> None:
    """PostgREST renders `numeric` as a string, not a float."""
    row = {
        "id": "sub_x",
        "assessment_id": "as_test01",
        "student_identifier": "S-1101",
        "submission_text": "x = 6",
        "submitted_at": "2026-03-05T14:00:00+00:00",
        "status": "pending",
        "student_id": "usr_s01",
        "is_self_study": False,
        "teacher_awarded_score": "4.50",
    }

    restored = mappers.submission_from_rows(row, [])

    assert restored.teacher_awarded_score == 4.5


def test_trailing_z_timestamp_is_accepted() -> None:
    row = {
        "id": "sub_z",
        "assessment_id": "as_test01",
        "student_identifier": "S-1101",
        "submission_text": "x = 6",
        "submitted_at": "2026-03-05T14:00:00Z",
        "status": "pending",
    }

    restored = mappers.submission_from_rows(row, [])

    assert restored.submitted_at.year == 2026
    assert restored.submitted_at.hour == 14


# --------------------------------------------------------------------------
# GradingResult
# --------------------------------------------------------------------------
def test_grading_result_round_trips() -> None:
    result = GradingResult(
        submission_id="sub_test01",
        question_id="q_1",
        max_marks=5,
        suggested_score=3,
        confidence=0.82,
        correct_elements=["Correct rearrangement"],
        errors=[
            ErrorItem(
                error_type=ErrorType.ARITHMETIC_ERROR,
                explanation="17 - 5 is 12, not 11.",
            )
        ],
        student_feedback="Check the subtraction in line two.",
        teacher_note="Watch this one.",
        review_status=ReviewStatus.EDITED,
        teacher_approved_score=4,
        teacher_approved_feedback="Method was sound.",
    )

    restored = mappers.grading_result_from_row(mappers.grading_result_to_row(result))

    assert restored.submission_id == result.submission_id
    assert restored.question_id == result.question_id
    assert restored.max_marks == result.max_marks
    assert restored.suggested_score == result.suggested_score
    assert restored.confidence == result.confidence
    assert restored.correct_elements == result.correct_elements
    assert restored.review_status is ReviewStatus.EDITED
    assert restored.teacher_approved_score == 4
    assert restored.teacher_approved_feedback == "Method was sound."
    assert len(restored.errors) == 1
    assert restored.errors[0].error_type is ErrorType.ARITHMETIC_ERROR
    assert restored.errors[0].explanation == "17 - 5 is 12, not 11."
    assert restored.final_score == 4


def test_awaiting_review_result_round_trips_without_a_final_score() -> None:
    """An unreviewed row must not come back looking settled."""
    result = GradingResult(
        submission_id="sub_test01",
        question_id="q_2",
        max_marks=3,
        suggested_score=2,
        confidence=0.4,
    )

    restored = mappers.grading_result_from_row(mappers.grading_result_to_row(result))

    assert restored.review_status is ReviewStatus.AWAITING_REVIEW
    assert restored.teacher_approved_score is None
    assert restored.final_score is None


def test_errors_serialise_to_plain_jsonb_shapes() -> None:
    result = GradingResult(
        submission_id="sub_test01",
        question_id="q_1",
        max_marks=2,
        suggested_score=1,
        confidence=0.5,
        errors=[
            ErrorItem(error_type=ErrorType.UNIT_ERROR, explanation="Missing cm."),
        ],
    )

    row = mappers.grading_result_to_row(result)

    assert row["errors"] == [
        {"error_type": "unit_error", "explanation": "Missing cm."}
    ]
    assert row["correct_elements"] == []


# --------------------------------------------------------------------------
# StudyCamp
# --------------------------------------------------------------------------
def test_study_camp_round_trips() -> None:
    camp = StudyCamp(
        id="camp_test01",
        student_id="usr_s02",
        topics=["Algebra", "Ratio"],
        started_on=date(2026, 4, 1),
        duration_days=3,
        baseline_percentage=58.5,
        sessions=[
            StudySession(
                day=1,
                topic="Algebra",
                questions=["Solve 2x = 8", "Solve x + 3 = 10"],
                method_hints=["Isolate x"],
                skill_focus="Rearranging",
                completed=True,
                score=2,
            ),
            StudySession(day=2, topic="Ratio", questions=["Share 20 in 2:3"]),
        ],
    )

    restored = mappers.study_camp_from_rows(*mappers.study_camp_to_rows(camp))

    assert restored.id == camp.id
    assert restored.student_id == camp.student_id
    assert restored.topics == camp.topics
    assert restored.started_on == camp.started_on
    assert restored.duration_days == camp.duration_days
    assert restored.baseline_percentage == camp.baseline_percentage
    assert [s.day for s in restored.sessions] == [1, 2]
    assert restored.sessions[0].completed is True
    assert restored.sessions[0].score == 2
    assert restored.sessions[1].score is None
    assert restored.baseline_percentage == 58.5


def test_session_order_survives_shuffled_rows() -> None:
    camp = StudyCamp(
        id="camp_test02",
        student_id="usr_s02",
        duration_days=3,
        baseline_percentage=50,
        sessions=[
            StudySession(day=1, topic="A", questions=["q"]),
            StudySession(day=2, topic="B", questions=["q"]),
            StudySession(day=3, topic="C", questions=["q"]),
        ],
    )
    row, session_rows = mappers.study_camp_to_rows(camp)

    restored = mappers.study_camp_from_rows(row, list(reversed(session_rows)))

    assert [s.topic for s in restored.sessions] == ["A", "B", "C"]


# --------------------------------------------------------------------------
# User
# --------------------------------------------------------------------------
def test_user_round_trips() -> None:
    user = User(
        id="usr_s02",
        display_name="S-1102",
        role=Role.STUDENT,
        teacher_id="usr_teacher01",
        year_group=10,
    )

    restored = mappers.user_from_row(mappers.user_to_row(user))

    assert restored == user


def test_teacher_row_has_no_roster() -> None:
    teacher = User(id="usr_teacher01", display_name="Ms Rao", role=Role.TEACHER)

    row = mappers.user_to_row(teacher)
    restored = mappers.user_from_row(row)

    assert row["role"] == "teacher"
    assert restored.is_teacher is True
    assert restored.teacher_id is None
