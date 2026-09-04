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


def results_dataframe(
    results: Sequence[GradingResult],
    assessments: Sequence[Assessment],
    submissions: Sequence[Submission],
) -> pd.DataFrame:
    """Flatten approved results into a tidy DataFrame for charting.

    Returns an empty DataFrame with the right columns when there is no data, so
    downstream callers never need to special-case the schema.
    """
    columns = [
        "submission_id",
        "student_identifier",
        "assessment_id",
        "assessment_title",
        "topic",
        "grade_level",
        "question_id",
        "question_text",
        "max_marks",
        "suggested_score",
        "final_score",
        "percentage",
        "confidence",
        "review_status",
        "accepted_unedited",
        "error_types",
    ]
    approved = approved_results(results)
    if not approved:
        return pd.DataFrame(columns=columns)

    submissions_by_id = {s.id: s for s in submissions}
    assessments_by_id = {a.id: a for a in assessments}
    question_lookup = {
        q.id: (a, q) for a in assessments for q in a.questions
    }

    rows: List[Dict[str, object]] = []
    for result in approved:
        submission = submissions_by_id.get(result.submission_id)
        assessment, question = question_lookup.get(result.question_id, (None, None))
        if assessment is None and submission is not None:
            assessment = assessments_by_id.get(submission.assessment_id)

        final = result.final_score
        if final is None:
            continue

        rows.append(
            {
                "submission_id": result.submission_id,
                "student_identifier": submission.student_identifier if submission else "unknown",
                "assessment_id": assessment.id if assessment else "unknown",
                "assessment_title": assessment.title if assessment else "Unknown assessment",
                "topic": assessment.topic if assessment else "Unknown topic",
                "grade_level": assessment.grade_level if assessment else None,
                "question_id": result.question_id,
                "question_text": _shorten(question.question_text) if question else result.question_id,
                "max_marks": result.max_marks,
                "suggested_score": result.suggested_score,
                "final_score": final,
                "percentage": round(100 * final / result.max_marks, 1) if result.max_marks else 0.0,
                "confidence": result.confidence,
                "review_status": result.review_status.value,
                "accepted_unedited": result.review_status == ReviewStatus.APPROVED,
                "error_types": [e.error_type.value for e in result.errors],
            }
        )

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


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


def submission_scores(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-student totals across approved questions."""
    if frame.empty:
        return pd.DataFrame(columns=["student_identifier", "awarded", "available", "percentage"])
    grouped = (
        frame.groupby("student_identifier", as_index=False)
        .agg(awarded=("final_score", "sum"), available=("max_marks", "sum"))
    )
    grouped["percentage"] = (100 * grouped["awarded"] / grouped["available"]).round(1)
    return grouped.sort_values("percentage", ascending=False, ignore_index=True)
