"""Translation between the domain models and Supabase rows.

WHY THIS IS ITS OWN MODULE
  The models are nested - an Assessment holds its Questions, a Submission holds
  a dict of answers, a StudyCamp holds its sessions. The database is flat: those
  are separate tables, because the questions are what the weakness analysis and
  the model-answer rules are actually about (see db/schema.sql).

  Something has to bridge the two shapes. Putting that in the repository would
  mix "how do I talk to Postgres" with "what shape is an Assessment", and would
  make the shape conversion untestable without a live database. So it lives
  here: pure functions, no network, no Streamlit, fully unit-testable.

THE RULE THESE FUNCTIONS FOLLOW
  Every `*_to_rows` / `*_from_rows` pair round-trips. Take a model, write it to
  rows, read it back, and you have the same model. tests/test_mappers.py asserts
  exactly that for each pair, because a silent asymmetry here would show up much
  later as data that vanishes on reload.

WHAT IS DELIBERATELY NOT HERE
  No scoping, no permission checks. Which rows a user may see is settled in
  db/policies.sql and re-stated in the service layer; a mapper that also had an
  opinion would be a third place for those rules to disagree.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from models import (
    Assessment,
    AssessmentType,
    ErrorItem,
    ErrorType,
    GradingResult,
    Question,
    Role,
    StudyCamp,
    StudySession,
    Subject,
    Submission,
    SubmissionStatus,
    User,
)

Row = Dict[str, Any]


# --------------------------------------------------------------------------
# Small shared helpers
# --------------------------------------------------------------------------
def _as_datetime(value: Any) -> datetime:
    """Parse a timestamptz coming back from PostgREST.

    Postgres renders microseconds and a "+00:00" offset; older rows may carry a
    trailing "Z", which fromisoformat rejects before Python 3.11. Both are
    handled so the mapper does not depend on the interpreter version.
    """
    if isinstance(value, datetime):
        return value
    if not value:
        return datetime.now()
    text = str(value).strip().replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return date.today()
    return date.fromisoformat(str(value).strip()[:10])


def _as_float(value: Any, default: float = 0.0) -> float:
    """numeric columns arrive as strings from PostgREST, not floats."""
    if value is None:
        return default
    return float(value)


def _optional_float(value: Any) -> Optional[float]:
    return None if value is None else float(value)


# --------------------------------------------------------------------------
# User <-> profiles
# --------------------------------------------------------------------------
def user_to_row(user: User) -> Row:
    return {
        "id": user.id,
        "display_name": user.display_name,
        "role": user.role.value,
        "teacher_id": user.teacher_id,
        "year_group": user.year_group,
    }


def user_from_row(row: Row) -> User:
    return User(
        id=row["id"],
        display_name=row["display_name"],
        role=Role(row.get("role") or Role.STUDENT.value),
        teacher_id=row.get("teacher_id"),
        year_group=row.get("year_group"),
    )


# --------------------------------------------------------------------------
# Assessment <-> assessments + questions
# --------------------------------------------------------------------------
def question_to_row(question: Question, assessment_id: str, position: int) -> Row:
    """One question row.

    `position` is passed in rather than read off the Question because order is a
    property of the list, not of the question. Rows have no inherent order, so
    without this column a reloaded assessment would come back shuffled.
    """
    return {
        "id": question.id,
        "assessment_id": assessment_id,
        "position": position,
        "question_text": question.question_text,
        "model_answer": question.model_answer,
        "marking_criteria": question.marking_criteria,
        "max_marks": question.max_marks,
    }


def question_from_row(row: Row) -> Question:
    """Rebuild a Question.

    Tolerates a row from `student_questions`, which has no model_answer or
    marking_criteria columns at all - that view is the whole point of the
    student read path. The result is a question that reports
    `has_model_answer == False`, which is exactly what a student should see.
    """
    return Question(
        id=row["id"],
        question_text=row["question_text"],
        model_answer=row.get("model_answer") or "",
        marking_criteria=row.get("marking_criteria") or "",
        max_marks=_as_float(row.get("max_marks")),
    )


def assessment_to_rows(assessment: Assessment) -> Tuple[Row, List[Row]]:
    """Split an Assessment into its own row plus one row per question."""
    row: Row = {
        "id": assessment.id,
        "title": assessment.title,
        "subject": assessment.subject.value,
        "curriculum": assessment.curriculum,
        "grade_level": assessment.grade_level,
        "topic": assessment.topic,
        "assessment_type": assessment.assessment_type.value,
        "max_marks": assessment.max_marks,
        "created_at": assessment.created_at.isoformat(),
        "owner_id": assessment.owner_id,
        "student_created": assessment.student_created,
        "is_shared": assessment.is_shared,
        "copied_from_id": assessment.copied_from_id,
    }
    question_rows = [
        question_to_row(question, assessment.id, position)
        for position, question in enumerate(assessment.questions)
    ]
    return row, question_rows


def assessment_from_rows(row: Row, question_rows: Sequence[Row]) -> Assessment:
    """Rebuild an Assessment from its row and its question rows.

    Question rows are sorted by `position` here rather than trusting the order
    PostgREST returned them in.
    """
    ordered = sorted(question_rows, key=lambda r: r.get("position") or 0)
    return Assessment(
        id=row["id"],
        title=row["title"],
        subject=Subject(row.get("subject") or Subject.MATHEMATICS.value),
        curriculum=row.get("curriculum") or "Cambridge IGCSE",
        grade_level=int(row["grade_level"]),
        topic=row["topic"],
        assessment_type=AssessmentType(
            row.get("assessment_type") or AssessmentType.HOMEWORK.value
        ),
        created_at=_as_datetime(row.get("created_at")),
        questions=[question_from_row(q) for q in ordered],
        owner_id=row.get("owner_id"),
        student_created=bool(row.get("student_created")),
        is_shared=bool(row.get("is_shared")),
        copied_from_id=row.get("copied_from_id"),
    )


# --------------------------------------------------------------------------
# Submission <-> submissions + submission_answers
# --------------------------------------------------------------------------
def submission_to_rows(submission: Submission) -> Tuple[Row, List[Row]]:
    row: Row = {
        "id": submission.id,
        "assessment_id": submission.assessment_id,
        "student_identifier": submission.student_identifier,
        "submission_text": submission.submission_text,
        "uploaded_filename": submission.uploaded_filename,
        "submitted_at": submission.submitted_at.isoformat(),
        "status": submission.status.value,
        "student_id": submission.student_id,
        "is_self_study": submission.is_self_study,
        "teacher_awarded_score": submission.teacher_awarded_score,
    }
    # A blank answer is written; an unattempted question has no row at all.
    # Submission.answer_for depends on that difference.
    answer_rows = [
        {
            "submission_id": submission.id,
            "question_id": question_id,
            "answer_text": answer,
        }
        for question_id, answer in submission.answers.items()
    ]
    return row, answer_rows


def submission_from_rows(row: Row, answer_rows: Sequence[Row]) -> Submission:
    return Submission(
        id=row["id"],
        assessment_id=row["assessment_id"],
        student_identifier=row["student_identifier"],
        submission_text=row["submission_text"],
        answers={
            r["question_id"]: (r.get("answer_text") or "") for r in answer_rows
        },
        uploaded_filename=row.get("uploaded_filename"),
        submitted_at=_as_datetime(row.get("submitted_at")),
        status=SubmissionStatus(row.get("status") or SubmissionStatus.PENDING.value),
        student_id=row.get("student_id"),
        is_self_study=bool(row.get("is_self_study")),
        teacher_awarded_score=_optional_float(row.get("teacher_awarded_score")),
    )


# --------------------------------------------------------------------------
# GradingResult <-> grading_results
# --------------------------------------------------------------------------
def grading_result_to_row(result: GradingResult) -> Row:
    return {
        "submission_id": result.submission_id,
        "question_id": result.question_id,
        "max_marks": result.max_marks,
        "suggested_score": result.suggested_score,
        "confidence": result.confidence,
        "correct_elements": list(result.correct_elements),
        "errors": [
            {"error_type": e.error_type.value, "explanation": e.explanation}
            for e in result.errors
        ],
        "student_feedback": result.student_feedback,
        "teacher_note": result.teacher_note,
        "review_status": result.review_status.value,
        "teacher_approved_score": result.teacher_approved_score,
        "teacher_approved_feedback": result.teacher_approved_feedback,
    }


def grading_result_from_row(row: Row) -> GradingResult:
    return GradingResult(
        submission_id=row["submission_id"],
        question_id=row["question_id"],
        max_marks=_as_float(row.get("max_marks")),
        suggested_score=_as_float(row.get("suggested_score")),
        confidence=_as_float(row.get("confidence")),
        correct_elements=list(row.get("correct_elements") or []),
        errors=[
            ErrorItem(
                error_type=ErrorType(e["error_type"]),
                explanation=e["explanation"],
            )
            for e in (row.get("errors") or [])
        ],
        student_feedback=row.get("student_feedback") or "",
        teacher_note=row.get("teacher_note") or "",
        review_status=row.get("review_status") or "awaiting_review",
        teacher_approved_score=_optional_float(row.get("teacher_approved_score")),
        teacher_approved_feedback=row.get("teacher_approved_feedback"),
    )


# --------------------------------------------------------------------------
# StudyCamp <-> study_camps + study_sessions
# --------------------------------------------------------------------------
def study_camp_to_rows(camp: StudyCamp) -> Tuple[Row, List[Row]]:
    row: Row = {
        "id": camp.id,
        "student_id": camp.student_id,
        "topics": list(camp.topics),
        "started_on": camp.started_on.isoformat(),
        "duration_days": camp.duration_days,
        "baseline_percentage": camp.baseline_percentage,
    }
    session_rows = [
        {
            "camp_id": camp.id,
            "day": session.day,
            "topic": session.topic,
            "questions": list(session.questions),
            "method_hints": list(session.method_hints),
            "skill_focus": session.skill_focus,
            "completed": session.completed,
            "score": session.score,
        }
        for session in camp.sessions
    ]
    return row, session_rows


def study_camp_from_rows(row: Row, session_rows: Sequence[Row]) -> StudyCamp:
    ordered = sorted(session_rows, key=lambda r: r.get("day") or 0)
    return StudyCamp(
        id=row["id"],
        student_id=row["student_id"],
        topics=list(row.get("topics") or []),
        started_on=_as_date(row.get("started_on")),
        duration_days=int(row["duration_days"]),
        baseline_percentage=_as_float(row.get("baseline_percentage")),
        sessions=[
            StudySession(
                day=int(s["day"]),
                topic=s["topic"],
                questions=list(s.get("questions") or []),
                method_hints=list(s.get("method_hints") or []),
                skill_focus=s.get("skill_focus") or "",
                completed=bool(s.get("completed")),
                score=None if s.get("score") is None else int(s["score"]),
            )
            for s in ordered
        ],
    )
