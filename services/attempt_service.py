"""The attempt loop: re-try only what you got wrong.

WHAT THIS IS FOR
  A student works a set, settles some questions and misses others, then comes
  back. Rather than re-marking the whole set, the next attempt covers only the
  questions still outstanding. Settled questions drop out and stay out.

  This is the loop the product is built around, and it is what a general
  chatbot cannot do: it needs memory of every previous attempt on the same
  question.

WHY THERE IS A CAP
  Ten attempts. Past that, another guess at the same question is not learning -
  it is grinding, and it usually means the question is above where the student
  currently is. The app stops and says so rather than letting them keep going.

NO STREAMLIT IN HERE
  Pure functions over models, so every rule below is unit-testable on its own.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

from models import Assessment, GradingResult, Question, Submission
from models.attempt import AttemptState, QuestionStanding, is_settling_score

# Ten attempts per question set. See the module docstring for why.
MAX_ATTEMPTS = 10


def attempts_for(
    student_id: str,
    assessment_id: str,
    submissions: Iterable[Submission],
) -> List[Submission]:
    """Every attempt one student has made at one set, oldest first."""
    mine = [
        s
        for s in submissions
        if s.student_id == student_id and s.assessment_id == assessment_id
    ]
    return sorted(mine, key=lambda s: (s.attempt_number, s.submitted_at))


def build_state(
    assessment: Assessment,
    student_id: str,
    submissions: Iterable[Submission],
    results: Iterable[GradingResult],
    max_attempts: int = MAX_ATTEMPTS,
) -> AttemptState:
    """Where this student stands on this set.

    `submissions` and `results` may be the student's whole history; everything
    not belonging to this set is filtered out here.
    """
    attempts = attempts_for(student_id, assessment.id, submissions)
    attempt_ids = {s.id for s in attempts}
    relevant = [r for r in results if r.submission_id in attempt_ids]

    by_question: Dict[str, List[GradingResult]] = {}
    for result in relevant:
        by_question.setdefault(result.question_id, []).append(result)

    attempt_number_of = {s.id: s.attempt_number for s in attempts}

    standings: List[QuestionStanding] = []
    for question in assessment.questions:
        scored = by_question.get(question.id, [])
        standing = QuestionStanding(
            question_id=question.id,
            max_marks=question.max_marks,
            attempts_used=len(scored),
        )
        if scored:
            # Best result wins, not the latest: a student who got it right and
            # then fumbled a re-run has still shown they can do it.
            best = max(scored, key=lambda r: r.effective_score)
            standing.best_score = best.effective_score
            standing.best_on_attempt = attempt_number_of.get(best.submission_id)
        standings.append(standing)

    return AttemptState(
        assessment_id=assessment.id,
        student_id=student_id,
        max_attempts=max_attempts,
        attempts_used=len(attempts),
        standings=standings,
    )


def outstanding_questions(
    assessment: Assessment,
    state: AttemptState,
) -> List[Question]:
    """The questions the next attempt should cover, in the set's own order."""
    wanted = set(state.outstanding_question_ids)
    return [q for q in assessment.questions if q.id in wanted]


def settled_questions(assessment: Assessment, state: AttemptState) -> List[Question]:
    """The questions already got right, in the set's own order."""
    done = {s.question_id for s in state.settled}
    return [q for q in assessment.questions if q.id in done]


def standing_for(state: AttemptState, question_id: str) -> QuestionStanding | None:
    return next((s for s in state.standings if s.question_id == question_id), None)


def attempt_history(
    assessment: Assessment,
    question_id: str,
    attempts: Sequence[Submission],
    results: Iterable[GradingResult],
) -> List[dict]:
    """Every attempt at one question, oldest first.

    Each entry carries the attempt number, what the student wrote that time and
    what it scored - which is what lets a student compare their attempts side
    by side rather than only seeing the latest.
    """
    by_submission = {}
    for result in results:
        by_submission.setdefault(result.submission_id, {})[result.question_id] = result

    history: List[dict] = []
    for submission in attempts:
        result = by_submission.get(submission.id, {}).get(question_id)
        if result is None:
            # This attempt did not cover the question - it was already settled.
            continue
        history.append(
            {
                "attempt_number": submission.attempt_number,
                "submitted_at": submission.submitted_at,
                "answer": submission.answer_for(question_id),
                "score": result.effective_score,
                "max_marks": result.max_marks,
                "is_settled": is_settling_score(result.effective_score, result.max_marks),
                "result": result,
            }
        )
    return history
