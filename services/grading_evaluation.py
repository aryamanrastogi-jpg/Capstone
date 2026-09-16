"""Measure a grader against marks a teacher would give.

Why this exists before any AI provider does: "the AI grades well" has to be a
number, and the rule-based grader needs the same number so there is a baseline
to beat. Every grader is a plain callable `(question, answer, submission_id) ->
GradingResult`, so the rule-based grader and `grade_with_ai` are scored by
exactly the same code.

Metrics, all over the labelled dataset in `data/grading_eval.json`:

  * exact_match_rate       - suggested score equals the teacher's mark
  * within_half_mark_rate  - off by at most 0.5
  * mean_absolute_error    - average distance from the teacher's mark, in marks
  * error_category_agreement - mean Jaccard overlap of error categories
                               (both empty counts as full agreement)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Mapping, Optional, Sequence

from models import ErrorType, GradingResult, Question

DEFAULT_DATASET = Path(__file__).resolve().parent.parent / "data" / "grading_eval.json"

Grader = Callable[[Question, str, str], GradingResult]

_EPSILON = 1e-9


@dataclass(frozen=True)
class EvalItem:
    id: str
    question_id: str
    student_answer: str
    teacher_score: float
    teacher_error_types: FrozenSet[ErrorType]


@dataclass(frozen=True)
class EvalRecord:
    """One graded item: what the teacher said next to what the grader said."""

    item_id: str
    teacher_score: float
    predicted_score: float
    teacher_error_types: FrozenSet[ErrorType]
    predicted_error_types: FrozenSet[ErrorType]
    path: Optional[str] = None  # which grading path produced it, when known


@dataclass(frozen=True)
class EvalMetrics:
    count: int
    exact_match_rate: float
    within_half_mark_rate: float
    mean_absolute_error: float
    error_category_agreement: float
    path_counts: Dict[str, int] = field(default_factory=dict)


def load_dataset(path: Path = DEFAULT_DATASET) -> List[EvalItem]:
    """Read and check the labelled dataset. Raises ValueError on bad rows."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items: List[EvalItem] = []
    seen: set = set()
    for row in raw.get("items", []):
        item_id = str(row["id"])
        if item_id in seen:
            raise ValueError(f"Duplicate evaluation item id '{item_id}'.")
        seen.add(item_id)
        score = float(row["teacher_score"])
        if score < 0 or abs(score * 2 - round(score * 2)) > _EPSILON:
            raise ValueError(f"Item '{item_id}': teacher_score must be a non-negative half mark.")
        items.append(
            EvalItem(
                id=item_id,
                question_id=str(row["question_id"]),
                student_answer=str(row.get("student_answer", "")),
                teacher_score=score,
                teacher_error_types=frozenset(
                    ErrorType(value) for value in row.get("teacher_error_types", [])
                ),
            )
        )
    return items


def _jaccard(a: FrozenSet[ErrorType], b: FrozenSet[ErrorType]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def compute_metrics(records: Sequence[EvalRecord]) -> EvalMetrics:
    """Summarise graded records. An empty input is an error, not a 100% score."""
    if not records:
        raise ValueError("Cannot compute grading metrics over zero records.")
    n = len(records)
    diffs = [abs(r.predicted_score - r.teacher_score) for r in records]
    path_counts: Dict[str, int] = {}
    for r in records:
        if r.path is not None:
            path_counts[r.path] = path_counts.get(r.path, 0) + 1
    return EvalMetrics(
        count=n,
        exact_match_rate=sum(d < _EPSILON for d in diffs) / n,
        within_half_mark_rate=sum(d <= 0.5 + _EPSILON for d in diffs) / n,
        mean_absolute_error=sum(diffs) / n,
        error_category_agreement=sum(
            _jaccard(r.teacher_error_types, r.predicted_error_types) for r in records
        ) / n,
        path_counts=path_counts,
    )


def evaluate(
    items: Sequence[EvalItem],
    questions: Mapping[str, Question],
    grader: Grader,
    path_of: Optional[Callable[[str], Optional[str]]] = None,
) -> List[EvalRecord]:
    """Run `grader` over every item. `path_of(item_id)` may report the path used."""
    records: List[EvalRecord] = []
    for item in items:
        question = questions.get(item.question_id)
        if question is None:
            raise ValueError(
                f"Item '{item.id}' refers to unknown question '{item.question_id}'."
            )
        if item.teacher_score > question.max_marks:
            raise ValueError(
                f"Item '{item.id}': teacher_score exceeds {question.max_marks} marks."
            )
        result = grader(question, item.student_answer, f"eval_{item.id}")
        records.append(
            EvalRecord(
                item_id=item.id,
                teacher_score=item.teacher_score,
                predicted_score=result.suggested_score,
                teacher_error_types=item.teacher_error_types,
                predicted_error_types=frozenset(e.error_type for e in result.errors),
                path=path_of(item.id) if path_of else None,
            )
        )
    return records


def sample_questions() -> Dict[str, Question]:
    """Every question in the seeded sample assessments, by id."""
    from data.sample_data import build_sample_data  # heavy; only when needed

    assessments = build_sample_data()[0]
    return {q.id: q for a in assessments for q in a.questions}


def format_report(metrics: EvalMetrics, grader_name: str) -> str:
    lines = [
        f"Grader: {grader_name}",
        f"Items: {metrics.count}",
        f"Exact match:              {metrics.exact_match_rate:6.1%}",
        f"Within half a mark:       {metrics.within_half_mark_rate:6.1%}",
        f"Mean absolute error:      {metrics.mean_absolute_error:6.2f} marks",
        f"Error-category agreement: {metrics.error_category_agreement:6.1%}",
    ]
    if metrics.path_counts:
        paths = ", ".join(f"{k}={v}" for k, v in sorted(metrics.path_counts.items()))
        lines.append(f"Grading paths used:       {paths}")
    return "\n".join(lines)
