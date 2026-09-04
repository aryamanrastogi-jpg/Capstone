"""Analytics computations.

Every function here is pure: it takes model objects and returns DataFrames or
plain dictionaries. Nothing touches Streamlit, so the analytics logic is
testable and reusable.

Only *approved* results (anything a teacher has reviewed) count towards class
performance. AI recommendations that nobody has looked at are deliberately
excluded.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

from models import Assessment, GradingResult, ReviewStatus, Submission

# Statuses that represent a teacher decision that a score is real.
FINALISED_STATUSES = (ReviewStatus.APPROVED, ReviewStatus.EDITED)


def approved_results(results: Iterable[GradingResult]) -> List[GradingResult]:
    """Results a teacher has signed off on (approved or edited)."""
    return [r for r in results if r.review_status in FINALISED_STATUSES]


def pending_results(results: Iterable[GradingResult]) -> List[GradingResult]:
    return [r for r in results if r.review_status == ReviewStatus.AWAITING_REVIEW]


def flagged_results(results: Iterable[GradingResult]) -> List[GradingResult]:
    return [r for r in results if r.review_status == ReviewStatus.FLAGGED]


FRAME_COLUMNS = [
    "submission_id",
    "student_id",
    "student_identifier",
    "assessment_id",
    "assessment_title",
    "assessment_type",
    "topic",
    "grade_level",
    "submitted_at",
    "question_id",
    "question_text",
    "max_marks",
    "suggested_score",
    "final_score",
    "score",
    "percentage",
    "confidence",
    "review_status",
    "is_official",
    "accepted_unedited",
    "error_types",
]


def results_dataframe(
    results: Sequence[GradingResult],
    assessments: Sequence[Assessment],
    submissions: Sequence[Submission],
    include_estimates: bool = False,
) -> pd.DataFrame:
    """Flatten grading results into a tidy DataFrame for charting.

    By default only teacher-finalised results are included - that is the
    teacher's view, where a score is an official mark.

    With `include_estimates=True` the AI's own suggestions are included too,
    scored on `suggested_score` and marked `is_official=False`. That is the
    student's view of their own work: useful for spotting weak topics, never
    presented as a real grade. Flagged results are excluded either way.

    Returns an empty DataFrame with the right columns when there is no data, so
    downstream callers never need to special-case the schema.
    """
    if include_estimates:
        usable = [r for r in results if r.review_status is not ReviewStatus.FLAGGED]
    else:
        usable = approved_results(results)

    if not usable:
        return pd.DataFrame(columns=FRAME_COLUMNS)

    submissions_by_id = {s.id: s for s in submissions}
    assessments_by_id = {a.id: a for a in assessments}
    question_lookup = {q.id: (a, q) for a in assessments for q in a.questions}

    rows: List[Dict[str, object]] = []
    for result in usable:
        submission = submissions_by_id.get(result.submission_id)
        assessment, question = question_lookup.get(result.question_id, (None, None))
        if assessment is None and submission is not None:
            assessment = assessments_by_id.get(submission.assessment_id)

        final = result.final_score
        score = final if final is not None else result.suggested_score
        if score is None:
            continue

        rows.append(
            {
                "submission_id": result.submission_id,
                "student_id": submission.student_id if submission else None,
                "student_identifier": submission.student_identifier if submission else "unknown",
                "assessment_id": assessment.id if assessment else "unknown",
                "assessment_title": assessment.title if assessment else "Unknown assessment",
                "assessment_type": (
                    assessment.assessment_type.label if assessment else "Unknown"
                ),
                "topic": assessment.topic if assessment else "Unknown topic",
                "grade_level": assessment.grade_level if assessment else None,
                "submitted_at": submission.submitted_at if submission else None,
                "question_id": result.question_id,
                "question_text": (
                    _shorten(question.question_text) if question else result.question_id
                ),
                "max_marks": result.max_marks,
                "suggested_score": result.suggested_score,
                "final_score": final,
                "score": score,
                "percentage": (
                    round(100 * score / result.max_marks, 1) if result.max_marks else 0.0
                ),
                "confidence": result.confidence,
                "review_status": result.review_status.value,
                "is_official": result.is_finalised,
                "accepted_unedited": result.review_status == ReviewStatus.APPROVED,
                "error_types": [e.error_type.value for e in result.errors],
            }
        )

    if not rows:
        return pd.DataFrame(columns=FRAME_COLUMNS)
    return pd.DataFrame(rows, columns=FRAME_COLUMNS)


def student_dataframe(
    student_id: str,
    results: Sequence[GradingResult],
    assessments: Sequence[Assessment],
    submissions: Sequence[Submission],
) -> pd.DataFrame:
    """One student's own history, including AI estimates.

    Scoped by `student_id` rather than filtered in the page, so a student can
    never be shown another student's work by accident.
    """
    own = [s for s in submissions if s.student_id == student_id]
    own_ids = {s.id for s in own}
    own_results = [r for r in results if r.submission_id in own_ids]
    return results_dataframe(own_results, assessments, own, include_estimates=True)


def _shorten(text: str, limit: int = 60) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# --------------------------------------------------------------------------
# Headline metrics
# --------------------------------------------------------------------------
def dashboard_metrics(
    assessments: Sequence[Assessment],
    submissions: Sequence[Submission],
    results: Sequence[GradingResult],
) -> Dict[str, object]:
    approved = approved_results(results)
    pending_ids = {r.submission_id for r in pending_results(results)}
    ungraded = {s.id for s in submissions} - {r.submission_id for r in results}
    awaiting = len(pending_ids | ungraded)

    reviewed_submissions = {
        r.submission_id
        for r in approved
        if r.submission_id not in pending_ids
    }

    return {
        "total_assessments": len(assessments),
        "total_submissions": len(submissions),
        "awaiting_review": awaiting,
        "reviewed_submissions": len(reviewed_submissions),
        "average_score_pct": average_percentage(approved),
        "flagged": len(flagged_results(results)),
    }


def average_percentage(results: Sequence[GradingResult]) -> Optional[float]:
    """Mean percentage across approved results, or None when there are none."""
    usable = [
        r for r in approved_results(results)
        if r.max_marks and r.final_score is not None
    ]
    if not usable:
        return None
    total_awarded = sum(r.final_score for r in usable)  # type: ignore[misc]
    total_available = sum(r.max_marks for r in usable)
    if not total_available:
        return None
    return round(100 * total_awarded / total_available, 1)


def acceptance_rate(results: Sequence[GradingResult]) -> Optional[float]:
    """Percentage of reviewed results accepted without any edit."""
    reviewed = approved_results(results)
    if not reviewed:
        return None
    accepted = sum(1 for r in reviewed if r.review_status == ReviewStatus.APPROVED)
    return round(100 * accepted / len(reviewed), 1)


# --------------------------------------------------------------------------
# Breakdowns
# --------------------------------------------------------------------------
def error_frequency(results: Sequence[GradingResult], approved_only: bool = False) -> pd.DataFrame:
    """Count each error category. Columns: error_type, label, count."""
    source = approved_results(results) if approved_only else list(results)
    counts: Dict[str, int] = {}
    for result in source:
        for error in result.errors:
            counts[error.error_type.value] = counts.get(error.error_type.value, 0) + 1

    if not counts:
        return pd.DataFrame(columns=["error_type", "label", "count"])

    frame = pd.DataFrame(
        [
            {"error_type": key, "label": key.replace("_", " ").title(), "count": value}
            for key, value in counts.items()
        ]
    )
    return frame.sort_values("count", ascending=False, ignore_index=True)


def question_difficulty(frame: pd.DataFrame) -> pd.DataFrame:
    """Average percentage per question, hardest first."""
    if frame.empty:
        return pd.DataFrame(columns=["question_text", "avg_percentage", "responses"])
    grouped = (
        frame.groupby(["question_id", "question_text"], as_index=False)
        .agg(avg_percentage=("percentage", "mean"), responses=("percentage", "size"))
    )
    grouped["avg_percentage"] = grouped["avg_percentage"].round(1)
    return grouped.sort_values("avg_percentage", ascending=True, ignore_index=True)


def topic_performance(frame: pd.DataFrame) -> pd.DataFrame:
    """Average percentage per topic, weakest first - i.e. revision priorities."""
    if frame.empty:
        return pd.DataFrame(columns=["topic", "avg_percentage", "responses"])
    grouped = (
        frame.groupby("topic", as_index=False)
        .agg(avg_percentage=("percentage", "mean"), responses=("percentage", "size"))
    )
    grouped["avg_percentage"] = grouped["avg_percentage"].round(1)
    return grouped.sort_values("avg_percentage", ascending=True, ignore_index=True)


def score_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    """Bucket percentages into readable bands. Columns: band, count."""
    bands = ["0-39", "40-54", "55-69", "70-84", "85-100"]
    if frame.empty:
        return pd.DataFrame({"band": bands, "count": [0] * len(bands)})

    edges = [-0.01, 39.999, 54.999, 69.999, 84.999, 100.0]
    binned = pd.cut(frame["percentage"], bins=edges, labels=bands)
    counts = binned.value_counts().reindex(bands, fill_value=0)
    return pd.DataFrame({"band": bands, "count": counts.to_list()})


# --------------------------------------------------------------------------
# Longitudinal views - the point of the product
# --------------------------------------------------------------------------
def topic_trend(frame: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    """Average percentage per topic over time.

    This is what turns a pile of past homework into a story: whether a topic is
    improving, flat, or getting worse across the term.

    Columns: period, topic, avg_percentage, responses.
    """
    columns = ["period", "topic", "avg_percentage", "responses"]
    if frame.empty or "submitted_at" not in frame:
        return pd.DataFrame(columns=columns)

    working = frame.dropna(subset=["submitted_at"]).copy()
    if working.empty:
        return pd.DataFrame(columns=columns)

    working["submitted_at"] = pd.to_datetime(working["submitted_at"])
    working["period"] = working["submitted_at"].dt.to_period(freq).dt.start_time

    grouped = (
        working.groupby(["period", "topic"], as_index=False)
        .agg(avg_percentage=("percentage", "mean"), responses=("percentage", "size"))
        .sort_values(["topic", "period"], ignore_index=True)
    )
    grouped["avg_percentage"] = grouped["avg_percentage"].round(1)
    return grouped[columns]


def overall_trend(frame: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    """Average percentage across all topics over time. Columns: period, avg_percentage."""
    columns = ["period", "avg_percentage", "responses"]
    trend = topic_trend(frame, freq=freq)
    if trend.empty:
        return pd.DataFrame(columns=columns)
    grouped = (
        trend.groupby("period", as_index=False)
        .agg(avg_percentage=("avg_percentage", "mean"), responses=("responses", "sum"))
        .sort_values("period", ignore_index=True)
    )
    grouped["avg_percentage"] = grouped["avg_percentage"].round(1)
    return grouped[columns]


def weakest_topics(frame: pd.DataFrame, limit: int = 3, ceiling: float = 100.0) -> List[str]:
    """The topics to revise first, weakest first.

    `ceiling` lets a caller ask only for topics below a threshold, e.g. 70.0 to
    ignore topics the student is already comfortable with.
    """
    performance = topic_performance(frame)
    if performance.empty:
        return []
    eligible = performance[performance["avg_percentage"] <= ceiling]
    return eligible.head(limit)["topic"].tolist()


def topic_strength(frame: pd.DataFrame) -> pd.DataFrame:
    """Every topic with an average and a plain-language band, weakest first."""
    performance = topic_performance(frame)
    if performance.empty:
        return pd.DataFrame(columns=["topic", "avg_percentage", "responses", "band"])
    performance["band"] = performance["avg_percentage"].apply(_band)
    return performance


def _band(percentage: float) -> str:
    if percentage >= 80:
        return "Secure"
    if percentage >= 65:
        return "Developing"
    if percentage >= 50:
        return "Needs work"
    return "Priority"


def mark_mismatches(
    submissions: Sequence[Submission],
    results: Sequence[GradingResult],
    assessments: Sequence[Assessment],
    threshold_pct: float = 15.0,
) -> pd.DataFrame:
    """Where the AI estimate and the teacher's own mark disagree.

    A second pair of eyes: if the student recorded 6/10 from their teacher but
    the AI reads the work as 9/10, that is worth the teacher re-checking. It is
    a prompt to look again, never an assertion that the teacher was wrong.

    Columns: submission_id, student_identifier, assessment_title,
             teacher_pct, ai_pct, gap, direction.
    """
    columns = [
        "submission_id",
        "student_identifier",
        "assessment_title",
        "teacher_score",
        "ai_score",
        "max_marks",
        "teacher_pct",
        "ai_pct",
        "gap",
        "direction",
    ]
    assessments_by_id = {a.id: a for a in assessments}
    results_by_submission: Dict[str, List[GradingResult]] = {}
    for result in results:
        results_by_submission.setdefault(result.submission_id, []).append(result)

    rows: List[Dict[str, object]] = []
    for submission in submissions:
        if submission.teacher_awarded_score is None:
            continue
        own = results_by_submission.get(submission.id) or []
        if not own:
            continue

        available = sum(r.max_marks for r in own)
        if not available:
            continue

        ai_total = sum(r.suggested_score for r in own)
        teacher_total = float(submission.teacher_awarded_score)
        ai_pct = round(100 * ai_total / available, 1)
        teacher_pct = round(100 * teacher_total / available, 1)
        gap = round(ai_pct - teacher_pct, 1)

        if abs(gap) < threshold_pct:
            continue

        assessment = assessments_by_id.get(submission.assessment_id)
        rows.append(
            {
                "submission_id": submission.id,
                "student_identifier": submission.student_identifier,
                "assessment_title": assessment.title if assessment else "Unknown assessment",
                "teacher_score": teacher_total,
                "ai_score": round(ai_total, 2),
                "max_marks": available,
                "teacher_pct": teacher_pct,
                "ai_pct": ai_pct,
                "gap": gap,
                "direction": "AI scored higher" if gap > 0 else "AI scored lower",
            }
        )

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns).sort_values(
        "gap", key=lambda s: s.abs(), ascending=False, ignore_index=True
    )


def submission_scores(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-student totals across approved questions."""
    if frame.empty:
        return pd.DataFrame(columns=["student_identifier", "awarded", "available", "percentage"])
    grouped = (
        frame.groupby("student_identifier", as_index=False)
        .agg(awarded=("score", "sum"), available=("max_marks", "sum"))
    )
    grouped["percentage"] = (100 * grouped["awarded"] / grouped["available"]).round(1)
    return grouped.sort_values("percentage", ascending=False, ignore_index=True)
