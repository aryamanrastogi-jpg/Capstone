"""Assessment and submission storage service.

Phase 1 stores everything in Streamlit session state. Every read/write goes
through this module so that a Supabase-backed implementation can be dropped in
behind the same function signatures in Phase 2.

The pure helpers (`build_assessment`, `build_submission`) contain no Streamlit
dependency and are unit-testable on their own.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from models import (
    Assessment,
    GradingResult,
    Question,
    Submission,
    SubmissionStatus,
    Subject,
)
from services import state as store
from services.supabase_client import get_supabase_client
from utils.validation import usable_question_rows


# --------------------------------------------------------------------------
# Pure builders (no Streamlit)
# --------------------------------------------------------------------------
def build_questions(rows: Sequence[Dict[str, Any]]) -> List[Question]:
    """Turn data_editor rows into validated Question models."""
    questions: List[Question] = []
    for row in usable_question_rows(list(rows)):
        questions.append(
            Question(
                question_text=str(row.get("question_text", "")),
                model_answer=str(row.get("model_answer", "")),
                marking_criteria=str(row.get("marking_criteria") or ""),
                max_marks=float(row.get("max_marks") or 0),
            )
        )
    return questions


def build_assessment(
    title: str,
    subject: str | Subject,
    curriculum: str,
    grade_level: int,
    topic: str,
    rows: Sequence[Dict[str, Any]],
) -> Assessment:
    """Build a validated Assessment. Raises pydantic.ValidationError if invalid."""
    return Assessment(
        title=title,
        subject=Subject(subject) if not isinstance(subject, Subject) else subject,
        curriculum=curriculum,
        grade_level=int(grade_level),
        topic=topic,
        questions=build_questions(rows),
    )


def build_submission(
    assessment_id: str,
    student_identifier: str,
    submission_text: str,
    uploaded_filename: Optional[str] = None,
) -> Submission:
    return Submission(
        assessment_id=assessment_id,
        student_identifier=student_identifier,
        submission_text=submission_text,
        uploaded_filename=uploaded_filename,
    )


# --------------------------------------------------------------------------
# Assessments
# --------------------------------------------------------------------------
def list_assessments() -> List[Assessment]:
    return list(store.get_assessments())


def get_assessment(assessment_id: str) -> Optional[Assessment]:
    return next((a for a in store.get_assessments() if a.id == assessment_id), None)


def save_assessment(assessment: Assessment) -> Assessment:
    """Persist an assessment. Session state today, Supabase later."""
    _ = get_supabase_client()  # Phase 2 hook; returns None in demo mode.
    assessments = store.get_assessments()
    for index, existing in enumerate(assessments):
        if existing.id == assessment.id:
            assessments[index] = assessment
            return assessment
    assessments.append(assessment)
    return assessment


def delete_assessment(assessment_id: str) -> bool:
    assessments = store.get_assessments()
    for index, existing in enumerate(assessments):
        if existing.id == assessment_id:
            assessments.pop(index)
            return True
    return False


# --------------------------------------------------------------------------
# Submissions
# --------------------------------------------------------------------------
def list_submissions(assessment_id: Optional[str] = None) -> List[Submission]:
    subs = list(store.get_submissions())
    if assessment_id:
        subs = [s for s in subs if s.assessment_id == assessment_id]
    return subs


def get_submission(submission_id: str) -> Optional[Submission]:
    return next((s for s in store.get_submissions() if s.id == submission_id), None)


def save_submission(submission: Submission) -> Submission:
    _ = get_supabase_client()
    submissions = store.get_submissions()
    for index, existing in enumerate(submissions):
        if existing.id == submission.id:
            submissions[index] = submission
            return submission
    submissions.append(submission)
    return submission


def set_submission_status(submission_id: str, status: SubmissionStatus) -> None:
    submission = get_submission(submission_id)
    if submission is not None:
        submission.status = status


# --------------------------------------------------------------------------
# Grading results
# --------------------------------------------------------------------------
def list_grading_results(submission_id: Optional[str] = None) -> List[GradingResult]:
    results = list(store.get_grading_results())
    if submission_id:
        results = [r for r in results if r.submission_id == submission_id]
    return results


def get_grading_result(submission_id: str, question_id: str) -> Optional[GradingResult]:
    return next(
        (
            r
            for r in store.get_grading_results()
            if r.submission_id == submission_id and r.question_id == question_id
        ),
        None,
    )


def save_grading_result(result: GradingResult) -> GradingResult:
    _ = get_supabase_client()
    results = store.get_grading_results()
    for index, existing in enumerate(results):
        if (
            existing.submission_id == result.submission_id
            and existing.question_id == result.question_id
        ):
            results[index] = result
            _refresh_submission_status(result.submission_id)
            return result
    results.append(result)
    _refresh_submission_status(result.submission_id)
    return result


def _refresh_submission_status(submission_id: str) -> None:
    """Keep a submission's status in step with its grading results."""
    submission = get_submission(submission_id)
    if submission is None:
        return
    results = list_grading_results(submission_id)
    if not results:
        submission.status = SubmissionStatus.PENDING
    elif all(r.is_finalised for r in results):
        # Flagged results are not finalised, so a submission holding one stays
        # in the "awaiting review" state until the teacher settles it.
        submission.status = SubmissionStatus.REVIEWED
    else:
        submission.status = SubmissionStatus.GRADED
