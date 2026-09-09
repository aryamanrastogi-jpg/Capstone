"""Assessment and submission storage service.

Every read and write in the application goes through this module. What it does
NOT do any more is decide where the data lives - that is `services.repository`,
which offers one interface over session state (demo mode) and Supabase.

WHAT CHANGED IN THE PORT, AND WHY IT MATTERS TO CALLERS
  The session-state store handed back live references: mutating a returned model
  mutated the store, so a page could change a field and the change simply stuck.
  A database cannot behave that way - a row does not update because a Python
  object did. Anything that mutates now saves explicitly, and the functions
  below do that on the caller's behalf.

The pure helpers (`build_assessment`, `build_submission`) contain no Streamlit
dependency and are unit-testable on their own.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from models import (
    Assessment,
    AssessmentType,
    GradingResult,
    Question,
    StudyCamp,
    Subject,
    Submission,
    SubmissionStatus,
    User,
    students_of,
)
from services.repository import get_repository
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
    assessment_type: str | AssessmentType = AssessmentType.HOMEWORK,
    owner_id: Optional[str] = None,
    student_created: bool = False,
) -> Assessment:
    """Build a validated Assessment. Raises pydantic.ValidationError if invalid.

    Pass `owner_id` and `student_created=True` for a set a student typed up
    themselves; that pair is what the scoped listings below read.
    """
    if isinstance(assessment_type, str):
        try:
            assessment_type = AssessmentType(assessment_type)
        except ValueError:
            assessment_type = AssessmentType.from_label(assessment_type)
    return Assessment(
        title=title,
        subject=Subject(subject) if not isinstance(subject, Subject) else subject,
        curriculum=curriculum,
        grade_level=int(grade_level),
        topic=topic,
        assessment_type=assessment_type,
        questions=build_questions(rows),
        owner_id=owner_id,
        student_created=student_created,
    )


def build_submission(
    assessment_id: str,
    student_identifier: str,
    submission_text: str = "",
    uploaded_filename: Optional[str] = None,
    student_id: Optional[str] = None,
    is_self_study: bool = False,
    teacher_awarded_score: Optional[float] = None,
    answers: Optional[Dict[str, str]] = None,
    questions: Optional[Sequence[Question]] = None,
    attempt_number: int = 1,
) -> Submission:
    """Build a validated Submission.

    Pass `answers` (question_id -> answer) for a per-question submission. If
    `submission_text` is then left empty it is composed from those answers, so
    the review page and the analytics still have one readable block to show.
    Pass `questions` alongside to get the numbering and order right.
    """
    answers = dict(answers or {})
    if not (submission_text or "").strip() and answers:
        submission_text = compose_submission_text(answers, questions)
    return Submission(
        assessment_id=assessment_id,
        student_identifier=student_identifier,
        submission_text=submission_text,
        answers=answers,
        uploaded_filename=uploaded_filename,
        student_id=student_id,
        is_self_study=is_self_study,
        teacher_awarded_score=teacher_awarded_score,
        attempt_number=attempt_number,
    )


def compose_submission_text(
    answers: Dict[str, str],
    questions: Optional[Sequence[Question]] = None,
) -> str:
    """Readable transcript of a per-question submission.

    Ordered by the assessment's questions when they are supplied, otherwise by
    the order the answers were collected in.
    """
    if questions:
        ordered = [(q.id, answers.get(q.id, "")) for q in questions if q.id in answers]
    else:
        ordered = list(answers.items())

    blocks = [
        f"Q{index}. {(answer or '').strip() or '(left blank)'}"
        for index, (_, answer) in enumerate(ordered, start=1)
    ]
    return "\n\n".join(blocks)


# --------------------------------------------------------------------------
# Assessments
# --------------------------------------------------------------------------
def list_assessments() -> List[Assessment]:
    """Every assessment, unscoped. Prefer one of the scoped listings below."""
    return get_repository().list_assessments()


def list_assessments_for_student(student_id: str) -> List[Assessment]:
    """What one student is allowed to work from.

    Their teacher's assessments, plus the question sets they typed up
    themselves - and nobody else's. The scoping lives here rather than in the
    page so a student's own worksheet can never appear in another's list.

    On the Supabase backend `assessments_select` in db/policies.sql enforces the
    same rule, so the database would not return the rows either. The filter is
    kept because it is the only thing enforcing it in demo mode.
    """
    return [
        a
        for a in get_repository().list_assessments()
        if not a.student_created or a.owner_id == student_id
    ]


def list_assessments_for_teacher() -> List[Assessment]:
    """The teacher-authored set.

    Student-created question sets are left out: they have no model answers and
    no marks to sign off, so they would only clutter the review queue.
    """
    return [a for a in get_repository().list_assessments() if not a.student_created]


def list_assessments_owned_by(owner_id: str) -> List[Assessment]:
    """Only the question sets this user created themselves."""
    return [a for a in get_repository().list_assessments() if a.owner_id == owner_id]


def list_shared_library(exclude_owner_id: Optional[str] = None) -> List[Assessment]:
    """Question sets other students have shared publicly, newest first.

    Pass `exclude_owner_id` to leave out the viewer's own sets - they already
    have those on My Questions, and repeating them in the library is noise.
    """
    shared = [
        a
        for a in get_repository().list_assessments()
        if a.is_shared and a.student_created and a.owner_id != exclude_owner_id
    ]
    return sorted(shared, key=lambda a: a.created_at, reverse=True)


def set_shared(assessment_id: str, shared: bool) -> Optional[Assessment]:
    """Share a set into the public library, or take it back out."""
    assessment = get_assessment(assessment_id)
    if assessment is None:
        return None
    assessment.is_shared = bool(shared)
    return save_assessment(assessment)


def copy_assessment_to(assessment: Assessment, owner_id: str) -> Assessment:
    """Take a copy of a shared set for another student to work through.

    A copy, not a reference. Two reasons, and both matter:

      * The new owner gets their own attempt history. Question ids are minted
        fresh so two students' progress can never collide on a shared id.
      * Editing the copy - adding the answers, fixing a typo - must not reach
        back into someone else's set.

    The copy is private. Sharing it on is the new owner's decision.
    """
    duplicate = Assessment(
        title=assessment.title,
        subject=assessment.subject,
        curriculum=assessment.curriculum,
        grade_level=assessment.grade_level,
        topic=assessment.topic,
        assessment_type=assessment.assessment_type,
        questions=[
            Question(
                question_text=q.question_text,
                model_answer=q.model_answer,
                marking_criteria=q.marking_criteria,
                max_marks=q.max_marks,
            )
            for q in assessment.questions
        ],
        owner_id=owner_id,
        student_created=True,
        is_shared=False,
        copied_from_id=assessment.id,
    )
    return save_assessment(duplicate)


def get_assessment(assessment_id: str) -> Optional[Assessment]:
    return get_repository().get_assessment(assessment_id)


def save_assessment(assessment: Assessment) -> Assessment:
    return get_repository().save_assessment(assessment)


def delete_assessment(assessment_id: str) -> bool:
    return get_repository().delete_assessment(assessment_id)


# --------------------------------------------------------------------------
# Submissions
# --------------------------------------------------------------------------
def list_submissions(
    assessment_id: Optional[str] = None,
    student_id: Optional[str] = None,
) -> List[Submission]:
    """Submissions, optionally scoped to an assessment and/or one student.

    Pass `student_id` for anything a student sees: scoping here rather than in
    the page means one student's work can never leak into another's view.
    """
    return get_repository().list_submissions(
        assessment_id=assessment_id, student_id=student_id
    )


def get_submission(submission_id: str) -> Optional[Submission]:
    return get_repository().get_submission(submission_id)


def save_submission(submission: Submission) -> Submission:
    return get_repository().save_submission(submission)


def set_submission_status(submission_id: str, status: SubmissionStatus) -> None:
    get_repository().set_submission_status(submission_id, status)


# --------------------------------------------------------------------------
# Grading results
# --------------------------------------------------------------------------
def list_grading_results(
    submission_id: Optional[str] = None,
    student_id: Optional[str] = None,
) -> List[GradingResult]:
    """Grading results, optionally scoped to a submission and/or one student."""
    results = get_repository().list_grading_results(submission_id=submission_id)
    if student_id:
        owned = {s.id for s in list_submissions(student_id=student_id)}
        results = [r for r in results if r.submission_id in owned]
    return results


def get_grading_result(submission_id: str, question_id: str) -> Optional[GradingResult]:
    return next(
        (
            r
            for r in get_repository().list_grading_results(submission_id=submission_id)
            if r.question_id == question_id
        ),
        None,
    )


def save_grading_result(result: GradingResult) -> GradingResult:
    saved = get_repository().save_grading_result(result)
    _refresh_submission_status(result.submission_id)
    return saved


def _refresh_submission_status(submission_id: str) -> None:
    """Keep a submission's status in step with its grading results.

    The status is written through the repository rather than assigned on the
    model. Under session state those were the same thing; against a database
    they are not, and assigning would have left the column stale.
    """
    repository = get_repository()
    submission = repository.get_submission(submission_id)
    if submission is None:
        return

    results = repository.list_grading_results(submission_id=submission_id)
    if not results:
        status = SubmissionStatus.PENDING
    elif all(r.is_finalised for r in results):
        # Flagged results are not finalised, so a submission holding one stays
        # in the "awaiting review" state until the teacher settles it.
        status = SubmissionStatus.REVIEWED
    else:
        status = SubmissionStatus.GRADED

    if submission.status is not status:
        repository.set_submission_status(submission_id, status)


# --------------------------------------------------------------------------
# Users, rosters and study camps
# --------------------------------------------------------------------------
def list_users() -> List[User]:
    return get_repository().list_users()


def get_user(user_id: str) -> Optional[User]:
    return next((u for u in get_repository().list_users() if u.id == user_id), None)


def list_students_for_teacher(teacher_id: str) -> List[User]:
    """Every student on one teacher's roster."""
    return students_of(get_repository().list_users(), teacher_id)


def save_user(user: User) -> User:
    return get_repository().save_user(user)


def list_study_camps(student_id: Optional[str] = None) -> List[StudyCamp]:
    return get_repository().list_study_camps(student_id=student_id)


def active_camp_for(student_id: str) -> Optional[StudyCamp]:
    """The student's most recent camp, if they have one."""
    camps = list_study_camps(student_id)
    if not camps:
        return None
    return sorted(camps, key=lambda c: c.started_on, reverse=True)[0]


def save_study_camp(camp: StudyCamp) -> StudyCamp:
    return get_repository().save_study_camp(camp)


def delete_study_camp(camp_id: str) -> bool:
    return get_repository().delete_study_camp(camp_id)
