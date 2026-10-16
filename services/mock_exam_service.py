"""Mock exam builder, timer and marker.

Builds a timed paper from questions the student can already see, marks it with
`grading_service.grade_submission`, and compares the result with the student's
baseline on the same topics. Only questions with a model answer are used: the
grader refuses anything else, and a paper it could not mark would be a lie.

Timing is computed from timestamps, never from a ticking widget - Streamlit
reruns the script on every interaction, so time left is always
`deadline - now`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Sequence

import pandas as pd

from models import Assessment, GradingResult
from models.mock_exam import MockExam, MockExamItem
from models.submission import MOCK_EXAM_SOURCE
from services import assessment_service, grading_service
from services.study_camp_service import baseline_for

DEFAULT_QUESTION_COUNT = 5
MAX_QUESTION_COUNT = 15
MINUTES_PER_QUESTION = 4
# A small allowance so a submit pressed as the clock hits zero still counts.
GRACE_SECONDS = 30


def available_topics(assessments: Sequence[Assessment]) -> List[str]:
    """Topics with at least one markable question."""
    topics: List[str] = []
    for assessment in assessments:
        if assessment.topic not in topics and any(
            q.has_model_answer for q in assessment.questions
        ):
            topics.append(assessment.topic)
    return topics


def default_topics(camp_topics: Sequence[str], assessments: Sequence[Assessment]) -> List[str]:
    """The camp's topics, where there is something to examine them with."""
    supported = set(available_topics(assessments))
    return [t for t in camp_topics if t in supported]


def question_pool(assessments: Sequence[Assessment], topics: Sequence[str]) -> List[MockExamItem]:
    """Every markable question on the chosen topics, without duplicates."""
    wanted = set(topics)
    seen = set()
    pool: List[MockExamItem] = []
    for assessment in assessments:
        if assessment.topic not in wanted:
            continue
        for question in assessment.questions:
            if not question.has_model_answer:
                continue
            key = " ".join(question.question_text.lower().split())
            if key in seen:
                continue
            seen.add(key)
            pool.append(
                MockExamItem(
                    topic=assessment.topic, question=question, assessment_id=assessment.id
                )
            )
    return pool


def _interleave(pool: List[MockExamItem], topics: Sequence[str], count: int) -> List[MockExamItem]:
    """Round-robin across topics so one topic cannot crowd out the rest."""
    queues = {t: [i for i in pool if i.topic == t] for t in topics}
    chosen: List[MockExamItem] = []
    while len(chosen) < count and any(queues.values()):
        for topic in topics:
            if queues[topic] and len(chosen) < count:
                chosen.append(queues[topic].pop(0))
    return chosen


def build_exam(
    student_id: str,
    assessments: Sequence[Assessment],
    topics: Sequence[str],
    frame: pd.DataFrame,
    question_count: int = DEFAULT_QUESTION_COUNT,
    minutes_per_question: int = MINUTES_PER_QUESTION,
    now: Optional[datetime] = None,
) -> MockExam:
    """Build a paper and start its clock. Raises ValueError when there is
    nothing to examine."""
    topics = list(dict.fromkeys(topics))
    if not topics:
        raise ValueError("Pick at least one topic for the mock exam.")
    count = max(1, min(int(question_count), MAX_QUESTION_COUNT))
    items = _interleave(question_pool(assessments, topics), topics, count)
    if not items:
        raise ValueError(
            "There are no questions with model answers on those topics yet, so "
            "a mock exam could not be marked."
        )
    baseline = None
    if not frame.empty and frame["topic"].isin(topics).any():
        baseline = baseline_for(frame, topics)
    return MockExam(
        student_id=student_id,
        topics=topics,
        items=items,
        time_limit_minutes=max(1, len(items) * int(minutes_per_question)),
        started_at=now or datetime.now(),
        baseline_percentage=baseline,
        topic_baselines=topic_baselines(frame, topics),
    )


def seconds_remaining(exam: MockExam, now: Optional[datetime] = None) -> int:
    """Whole seconds left, never negative."""
    now = now or datetime.now()
    return max(0, int((exam.deadline - now).total_seconds()))


def is_expired(exam: MockExam, now: Optional[datetime] = None) -> bool:
    """True once the time limit and the grace allowance have both passed."""
    now = now or datetime.now()
    return (now - exam.deadline).total_seconds() > GRACE_SECONDS


def format_remaining(seconds: int) -> str:
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{secs:02d}"


def submit_exam(
    exam: MockExam,
    answers: Dict[str, str],
    now: Optional[datetime] = None,
) -> MockExam:
    """Lock the paper and mark it.

    Past the time limit the answers are still marked, but the sitting is
    flagged late so the score is not mistaken for a timed one.
    """
    if exam.is_submitted:
        raise ValueError("This mock exam has already been submitted.")
    now = now or datetime.now()
    exam.submitted_late = is_expired(exam, now)
    exam.answers = {
        item.question.id: (answers.get(item.question.id) or "").strip()
        for item in exam.items
    }
    outcomes = [
        grading_service.grade_submission_outcomes(
            [item.question], "", exam.id, answers=exam.answers
        )[0]
        for item in exam.items
    ]
    exam.results = [outcome.result for outcome in outcomes]
    exam.ai_unavailable = any(outcome.ai_was_unavailable for outcome in outcomes)
    exam.submitted_at = now
    return exam


def save_to_history(
    exam: MockExam,
    student_label: str,
    assessments: Sequence[Assessment] = (),
) -> List[str]:
    """Save a handed-in paper as the student's own work, so it counts.

    One self-study record per set the questions came from - the shape My
    Work already saves, so My Progress, Study Camp and the database rules need
    nothing new. Each is labelled as a mock exam (MOCK_EXAM_SOURCE), which
    keeps it out of the attempt loop: a timed paper must not use up attempts
    on, or settle questions in, the sets it borrowed from.

    All or nothing: if any write fails, the records already written are taken
    back out and the error is raised. Returns the new records' ids.
    """
    if not exam.is_submitted:
        raise ValueError("Hand the paper in before saving it.")
    if exam.saved_submission_ids:
        return list(exam.saved_submission_ids)

    set_of = {q.id: a.id for a in assessments for q in a.questions}
    results_by_question = {r.question_id: r for r in exam.results}
    groups: Dict[str, List[MockExamItem]] = {}
    for item in exam.items:
        set_id = item.assessment_id or set_of.get(item.question.id)
        if set_id and item.question.id in results_by_question:
            groups.setdefault(set_id, []).append(item)

    saved: List[str] = []
    try:
        for set_id, items in groups.items():
            submission = assessment_service.build_submission(
                assessment_id=set_id,
                student_identifier=student_label,
                answers={i.question.id: exam.answers.get(i.question.id, "") for i in items},
                questions=[i.question for i in items],
                uploaded_filename=MOCK_EXAM_SOURCE,
                student_id=exam.student_id,
                is_self_study=True,
            )
            submission.submitted_at = exam.submitted_at or datetime.now()
            assessment_service.save_submission(submission)
            saved.append(submission.id)
            for item in items:
                result = results_by_question[item.question.id]
                assessment_service.save_grading_result(
                    result.model_copy(update={"submission_id": submission.id})
                )
    except Exception:
        for submission_id in saved:
            try:
                assessment_service.delete_submission(submission_id)
            except Exception:  # noqa: BLE001 - best effort; the first error matters
                pass
        raise
    exam.saved_submission_ids = saved
    exam.save_failed = False
    return saved


def _percentage(results: Sequence[GradingResult]) -> Optional[float]:
    total = sum(r.max_marks for r in results)
    if not total:
        return None
    return round(100 * sum(r.suggested_score for r in results) / total, 1)


def topic_baselines(frame: pd.DataFrame, topics: Sequence[str]) -> Dict[str, Optional[float]]:
    """Per-topic starting points, None where the student has no history."""
    out: Dict[str, Optional[float]] = {}
    for topic in topics:
        rows = frame[frame["topic"] == topic] if not frame.empty else frame
        out[topic] = round(float(rows["percentage"].mean()), 1) if not rows.empty else None
    return out


def score_summary(exam: MockExam, frame: Optional[pd.DataFrame] = None) -> Dict[str, object]:
    """Overall and per-topic AI-estimated scores, against the baseline."""
    by_id = {r.question_id: r for r in exam.results}
    if exam.topic_baselines:
        baselines = exam.topic_baselines
    else:  # a paper set before the baselines were stored with it
        baselines = topic_baselines(frame, exam.topics) if frame is not None else {}
    topics = []
    for topic in exam.topics:
        topic_results = [
            by_id[i.question.id]
            for i in exam.items
            if i.topic == topic and i.question.id in by_id
        ]
        if not topic_results:
            continue
        pct = _percentage(topic_results)
        before = baselines.get(topic)
        topics.append(
            {
                "topic": topic,
                "questions": len(topic_results),
                "before": before,
                "after": pct,
                "change": round(pct - before, 1) if before is not None and pct is not None else None,
            }
        )
    overall = _percentage(exam.results)
    baseline = exam.baseline_percentage
    return {
        "score": round(sum(r.suggested_score for r in exam.results), 1),
        "max_score": exam.total_marks,
        "percentage": overall,
        "baseline": baseline,
        "change": round(overall - baseline, 1)
        if overall is not None and baseline is not None
        else None,
        "topics": topics,
        "late": exam.submitted_late,
    }
