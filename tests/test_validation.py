"""Tests for model validation, upload validation and assessment mark totals."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models import (
    Assessment,
    ErrorItem,
    ErrorType,
    GradingResult,
    Question,
    ReviewStatus,
    Submission,
    Subject,
)
from services import assessment_service
from utils.validation import (
    clamp_score,
    sanitize_filename,
    total_marks,
    validate_assessment_draft,
    validate_upload,
)


def _question(marks: float = 4) -> Question:
    return Question(
        question_text="Solve for x: 3x + 7 = 22.",
        model_answer="Subtract 7, divide by 3, x = 5.",
        marking_criteria="1 mark per correct step.",
        max_marks=marks,
    )


# ---------------------------------------------------------------------------
# GradingResult score bounds
# ---------------------------------------------------------------------------
def test_negative_suggested_score_is_rejected():
    with pytest.raises(ValidationError):
        GradingResult(
            submission_id="sub_1",
            question_id="q_1",
            max_marks=5,
            suggested_score=-1,
            confidence=0.8,
        )


def test_suggested_score_above_max_marks_is_rejected():
    with pytest.raises(ValidationError) as exc:
        GradingResult(
            submission_id="sub_1",
            question_id="q_1",
            max_marks=5,
            suggested_score=6,
            confidence=0.8,
        )
    assert "exceeds the maximum" in str(exc.value)


def test_negative_teacher_approved_score_is_rejected():
    with pytest.raises(ValidationError):
        GradingResult(
            submission_id="sub_1",
            question_id="q_1",
            max_marks=5,
            suggested_score=3,
            confidence=0.8,
            review_status=ReviewStatus.EDITED,
            teacher_approved_score=-0.5,
        )


def test_teacher_approved_score_above_max_marks_is_rejected():
    with pytest.raises(ValidationError):
        GradingResult(
            submission_id="sub_1",
            question_id="q_1",
            max_marks=5,
            suggested_score=3,
            confidence=0.8,
            review_status=ReviewStatus.EDITED,
            teacher_approved_score=5.5,
        )


def test_valid_grading_result_passes_validation():
    result = GradingResult(
        submission_id="sub_1",
        question_id="q_1",
        max_marks=5,
        suggested_score=4,
        confidence=0.72,
        correct_elements=["Correct method used."],
        errors=[
            ErrorItem(
                error_type=ErrorType.ARITHMETIC_ERROR,
                explanation="The final division is wrong.",
            )
        ],
        student_feedback="Good method - re-check the last step.",
        teacher_note="Moderate confidence.",
    )
    assert result.suggested_score == 4
    assert result.review_status == ReviewStatus.AWAITING_REVIEW
    assert result.final_score is None  # nothing is final before review
    assert result.errors[0].error_type is ErrorType.ARITHMETIC_ERROR


def test_final_score_prefers_the_teacher_score_once_reviewed():
    result = GradingResult(
        submission_id="sub_1",
        question_id="q_1",
        max_marks=5,
        suggested_score=3,
        confidence=0.6,
        review_status=ReviewStatus.EDITED,
        teacher_approved_score=4.5,
    )
    assert result.final_score == 4.5


@pytest.mark.parametrize("confidence", [-0.01, 1.01, 2.0, -5])
def test_confidence_outside_zero_to_one_is_rejected(confidence):
    with pytest.raises(ValidationError):
        GradingResult(
            submission_id="sub_1",
            question_id="q_1",
            max_marks=5,
            suggested_score=1,
            confidence=confidence,
        )


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_confidence_at_the_boundaries_is_accepted(confidence):
    result = GradingResult(
        submission_id="sub_1",
        question_id="q_1",
        max_marks=5,
        suggested_score=1,
        confidence=confidence,
    )
    assert result.confidence == confidence


# ---------------------------------------------------------------------------
# Assessment marks
# ---------------------------------------------------------------------------
def test_assessment_total_marks_are_calculated_from_questions():
    assessment = Assessment(
        title="Mixed test",
        subject=Subject.MATHEMATICS,
        curriculum="CBSE",
        grade_level=8,
        topic="Linear Equations",
        questions=[_question(3), _question(4), _question(2.5)],
    )
    assert assessment.max_marks == 9.5
    assert assessment.question_count == 3


def test_assessment_total_marks_ignore_a_supplied_value():
    assessment = Assessment(
        title="Mixed test",
        curriculum="CBSE",
        grade_level=7,
        topic="Area",
        max_marks=999,
        questions=[_question(3), _question(2)],
    )
    assert assessment.max_marks == 5


def test_assessment_requires_at_least_one_question():
    with pytest.raises(ValidationError):
        Assessment(
            title="Empty",
            curriculum="CBSE",
            grade_level=8,
            topic="Nothing",
            questions=[],
        )


@pytest.mark.parametrize("marks", [0, -2])
def test_question_marks_must_be_positive(marks):
    with pytest.raises(ValidationError):
        Question(question_text="Q", model_answer="A", max_marks=marks)


def test_question_requires_a_model_answer():
    with pytest.raises(ValidationError):
        Question(question_text="Q", model_answer="   ", max_marks=2)


def test_total_marks_helper_sums_only_usable_rows():
    rows = [
        {"question_text": "Q1", "model_answer": "A1", "max_marks": 3},
        {"question_text": "", "model_answer": "", "marking_criteria": "", "max_marks": 0},
        {"question_text": "Q2", "model_answer": "A2", "max_marks": 2.5},
    ]
    assert total_marks(rows) == 5.5


def test_build_assessment_skips_blank_rows():
    rows = [
        {"question_text": "Q1", "model_answer": "A1", "marking_criteria": "", "max_marks": 3},
        {"question_text": "", "model_answer": "", "marking_criteria": "", "max_marks": 0},
    ]
    assessment = assessment_service.build_assessment(
        title="T", subject="Mathematics", curriculum="CBSE",
        grade_level=8, topic="Algebra", rows=rows,
    )
    assert assessment.question_count == 1
    assert assessment.max_marks == 3


# ---------------------------------------------------------------------------
# Assessment draft validation
# ---------------------------------------------------------------------------
def test_draft_validation_reports_missing_fields():
    result = validate_assessment_draft(
        title="",
        topic="",
        curriculum="CBSE",
        questions=[{"question_text": "Q", "model_answer": "", "max_marks": 0}],
    )
    assert not result.ok
    joined = " ".join(result.errors)
    assert "title is required" in joined
    assert "Topic is required" in joined
    assert "model answer is required" in joined
    assert "greater than zero" in joined


def test_draft_validation_accepts_a_good_draft():
    result = validate_assessment_draft(
        title="Test",
        topic="Algebra",
        curriculum="CBSE",
        questions=[{"question_text": "Q", "model_answer": "A", "max_marks": 3}],
    )
    assert result.ok
    assert result.errors == []


def test_draft_validation_requires_at_least_one_question():
    result = validate_assessment_draft(
        title="Test", topic="Algebra", curriculum="CBSE", questions=[]
    )
    assert not result.ok


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------
def test_unsupported_upload_format_is_rejected():
    ok, message = validate_upload("answers.docx", b"anything at all")
    assert not ok
    assert "Unsupported file type" in message


def test_executable_upload_is_rejected():
    ok, message = validate_upload("payload.exe", b"MZ\x90\x00")
    assert not ok
    assert "Unsupported file type" in message


def test_txt_upload_is_accepted():
    ok, _ = validate_upload("response.txt", "x = 5 because 3x = 15".encode("utf-8"))
    assert ok


def test_pdf_extension_without_pdf_content_is_rejected():
    """An extension alone is never treated as proof of file type."""
    ok, message = validate_upload("fake.pdf", b"this is plain text, not a pdf")
    assert not ok
    assert "not a valid PDF" in message


def test_txt_extension_with_pdf_content_is_rejected():
    ok, message = validate_upload("sneaky.txt", b"%PDF-1.7\n binary junk")
    assert not ok
    assert "are a PDF" in message


def test_empty_upload_is_rejected():
    ok, message = validate_upload("response.txt", b"")
    assert not ok
    assert "empty" in message.lower()


def test_oversized_upload_is_rejected():
    ok, message = validate_upload("big.txt", b"a" * 2048, max_bytes=1024)
    assert not ok
    assert "exceeds" in message


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        (r"C:\Users\me\answers.txt", "answers.txt"),
        ("my answers (final).pdf", "my_answers_final.pdf"),
        ("", "upload"),
    ],
)
def test_filenames_are_sanitised(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sanitised_filename_has_no_path_separators():
    assert "/" not in sanitize_filename("a/b/c.txt")
    assert "\\" not in sanitize_filename(r"a\b\c.txt")


# ---------------------------------------------------------------------------
# Score clamping
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("score", "maximum", "expected"),
    [(-3, 5, 0.0), (9, 5, 5.0), (2.5, 5, 2.5), (5, 5, 5.0)],
)
def test_clamp_score_keeps_scores_within_bounds(score, maximum, expected):
    assert clamp_score(score, maximum) == expected


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------
def test_submission_requires_non_empty_text():
    with pytest.raises(ValidationError):
        Submission(assessment_id="as_1", student_identifier="S-1", submission_text="   ")


def test_submission_requires_an_identifier():
    with pytest.raises(ValidationError):
        Submission(assessment_id="as_1", student_identifier="", submission_text="x = 5")
