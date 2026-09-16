"""Targeted practice: choose what to practise from real results.

The Practice Generator used to ask the user to pick a topic, an error category
and a difficulty. That is backwards - the app already knows where the work is
going wrong. This module reads a results frame (from `analytics_service`) and
decides:

* **which topics** - the weakest first, weighted so a 35% topic gets more
  questions than a 70% one;
* **which error categories** - the ones that actually came up in that topic,
  split in proportion to how often;
* **which difficulty** - from the topic average, stepped down a level when the
  errors are about method or understanding rather than slips, because those
  are easier to fix on simpler numbers.

Every item carries a plain-language reason, so the page can say *why* it was
chosen. Nothing here shows a worked solution: questions come from
`practice_service`, whose hints are pointers only.

Pure functions, no Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import pandas as pd

from models import ErrorType
from services.practice_service import (
    DIFFICULTIES,
    PracticeQuestion,
    generate_practice_questions,
    template_topic_for,
)

DEFAULT_TOTAL = 6
MAX_TOTAL = 10
MAX_TOPICS = 3
# At most this many error categories are drilled per topic, so each one gets
# enough questions to matter.
MAX_ERRORS_PER_TOPIC = 2
# A topic averaging this or better is only practised when nothing is weaker.
SECURE_PERCENTAGE = 85.0
# Floor on a topic's weight so a strong-but-chosen topic still gets a question.
_MIN_WEIGHT = 5.0

DEFAULT_FOCUS = ErrorType.MISSING_WORKING

# Errors about *how* to approach a question, rather than slips in carrying it
# out. These are drilled one difficulty level lower.
STEP_DOWN_ERRORS = frozenset({ErrorType.CONCEPTUAL_ERROR, ErrorType.INCORRECT_METHOD})


@dataclass
class TopicEvidence:
    """What the results say about one template topic."""

    topic: str
    avg_percentage: float
    responses: int
    error_counts: List[Tuple[ErrorType, int]] = field(default_factory=list)
    source_topics: List[str] = field(default_factory=list)

    @property
    def total_errors(self) -> int:
        return sum(count for _, count in self.error_counts)

    @property
    def weight(self) -> float:
        return max(100.0 - self.avg_percentage, _MIN_WEIGHT)


@dataclass
class PracticeTarget:
    topic: str
    error_type: ErrorType
    difficulty: str
    count: int
    reason: str


@dataclass
class TargetedItem:
    question: PracticeQuestion
    reason: str


@dataclass
class TargetedPractice:
    items: List[TargetedItem]
    targets: List[PracticeTarget]
    evidence: List[TopicEvidence]
    unsupported_topics: List[str]

    @property
    def is_empty(self) -> bool:
        return not self.items


# --------------------------------------------------------------------------
# Reading the evidence
# --------------------------------------------------------------------------
def _count_errors(rows: pd.DataFrame) -> List[Tuple[ErrorType, int]]:
    counts: Dict[ErrorType, int] = {}
    for entry in rows.get("error_types", []):
        for value in entry or []:
            try:
                error = ErrorType(value)
            except ValueError:
                continue
            counts[error] = counts.get(error, 0) + 1
    # Most frequent first; ties in the enum's own order so results are stable.
    order = list(ErrorType)
    return sorted(counts.items(), key=lambda item: (-item[1], order.index(item[0])))


def topic_evidence(frame: pd.DataFrame) -> Tuple[List[TopicEvidence], List[str]]:
    """Evidence per template topic, weakest first, plus topics with no templates.

    Free-text topics are folded into the template topic they belong to, so a
    student's own "Percentage change" set counts towards "Percentages".
    """
    if frame is None or frame.empty:
        return [], []

    working = frame.copy()
    working["template_topic"] = working["topic"].map(template_topic_for)
    unsupported = sorted(
        {str(t) for t in working.loc[working["template_topic"].isna(), "topic"]}
    )
    supported = working.dropna(subset=["template_topic"])

    evidence: List[TopicEvidence] = []
    for topic, rows in supported.groupby("template_topic", sort=True):
        evidence.append(
            TopicEvidence(
                topic=str(topic),
                avg_percentage=round(float(rows["percentage"].mean()), 1),
                responses=int(len(rows)),
                error_counts=_count_errors(rows),
                source_topics=sorted({str(t) for t in rows["topic"]}),
            )
        )
    evidence.sort(key=lambda e: (e.avg_percentage, -e.total_errors, e.topic))
    return evidence, unsupported


def overall_error_counts(frame: pd.DataFrame) -> List[Tuple[ErrorType, int]]:
    """Error categories across every topic, most frequent first."""
    if frame is None or frame.empty:
        return []
    return _count_errors(frame)


# --------------------------------------------------------------------------
# Deciding
# --------------------------------------------------------------------------
def _allocate(total: int, weights: Sequence[float]) -> List[int]:
    """Split `total` in proportion to `weights`, at least one each.

    Largest-remainder rounding, so the parts always add up to `total`.
    """
    if not weights:
        return []
    slots = len(weights)
    if total <= slots:
        return [1 if index < total else 0 for index in range(slots)]
    spare = total - slots
    weight_sum = sum(weights) or float(slots)
    raw = [spare * w / weight_sum for w in weights]
    shares = [int(r) for r in raw]
    leftovers = sorted(
        range(slots), key=lambda i: (-(raw[i] - shares[i]), i)
    )[: spare - sum(shares)]
    for index in leftovers:
        shares[index] += 1
    return [1 + share for share in shares]


def base_difficulty(avg_percentage: float) -> str:
    if avg_percentage < 55:
        return "Foundation"
    if avg_percentage < 80:
        return "Core"
    return "Extension"


def difficulty_for(avg_percentage: float, error_type: ErrorType) -> str:
    """Difficulty for a topic average, one step easier for method/concept errors."""
    level = DIFFICULTIES.index(base_difficulty(avg_percentage))
    if error_type in STEP_DOWN_ERRORS:
        level = max(0, level - 1)
    return DIFFICULTIES[level]


def _choose_topics(evidence: Sequence[TopicEvidence], max_topics: int) -> List[TopicEvidence]:
    weak = [e for e in evidence if e.avg_percentage < SECURE_PERCENTAGE]
    return (weak or list(evidence[:1]))[:max_topics]


def _reason(
    evidence: TopicEvidence,
    rank: int,
    error_type: ErrorType,
    error_count: int,
    from_overall: bool,
    difficulty: str,
    whose: str,
) -> str:
    ranking = {0: "weakest topic", 1: "second-weakest topic", 2: "third-weakest topic"}
    place = ranking.get(rank, "one of the weaker topics")
    answers = f"{evidence.responses} graded answer{'s' if evidence.responses != 1 else ''}"
    parts = [
        f"{evidence.topic} is {whose} {place} ({evidence.avg_percentage:g}% across {answers})."
    ]
    if error_count and not from_overall:
        parts.append(
            f"{error_type.label} came up {error_count} time{'s' if error_count != 1 else ''} "
            f"in this topic, out of {evidence.total_errors} error(s) recorded."
        )
    elif error_count:
        parts.append(
            f"No errors were recorded in this topic, so it targets {error_type.label}, "
            f"{whose} most common error elsewhere ({error_count} time{'s' if error_count != 1 else ''})."
        )
    else:
        parts.append(
            "No specific error pattern was recorded, so it practises showing full working."
        )
    base = base_difficulty(evidence.avg_percentage)
    if difficulty != base:
        parts.append(
            f"Set at {difficulty} rather than {base}: method and understanding errors "
            "are easier to fix on simpler numbers."
        )
    else:
        parts.append(f"Set at {difficulty} to match that average.")
    return " ".join(parts)


def build_targets(
    frame: pd.DataFrame,
    total: int = DEFAULT_TOTAL,
    max_topics: int = MAX_TOPICS,
    whose: str = "your",
) -> Tuple[List[PracticeTarget], List[TopicEvidence], List[str]]:
    """Decide what to practise. Returns (targets, evidence, unsupported topics).

    `whose` is the possessive used in the reasons: "your" for a student,
    "the class's" or "S-1102's" for a teacher.
    """
    total = max(1, min(int(total), MAX_TOTAL))
    evidence, unsupported = topic_evidence(frame)
    if not evidence:
        return [], evidence, unsupported

    chosen = _choose_topics(evidence, max(1, int(max_topics)))
    overall = overall_error_counts(frame)
    per_topic = _allocate(total, [e.weight for e in chosen])

    targets: List[PracticeTarget] = []
    for rank, (topic_evidence_item, topic_count) in enumerate(zip(chosen, per_topic)):
        if topic_count <= 0:
            continue
        errors = topic_evidence_item.error_counts[:MAX_ERRORS_PER_TOPIC]
        from_overall = False
        if not errors and overall:
            errors, from_overall = overall[:1], True
        if not errors:
            errors = [(DEFAULT_FOCUS, 0)]

        split = _allocate(topic_count, [float(count or 1) for _, count in errors])
        for (error_type, error_count), count in zip(errors, split):
            if count <= 0:
                continue
            difficulty = difficulty_for(topic_evidence_item.avg_percentage, error_type)
            targets.append(
                PracticeTarget(
                    topic=topic_evidence_item.topic,
                    error_type=error_type,
                    difficulty=difficulty,
                    count=count,
                    reason=_reason(
                        topic_evidence_item, rank, error_type, error_count,
                        from_overall, difficulty, whose,
                    ),
                )
            )
    return targets, evidence, unsupported


def generate_targeted_practice(
    frame: pd.DataFrame,
    total: int = DEFAULT_TOTAL,
    max_topics: int = MAX_TOPICS,
    whose: str = "your",
) -> TargetedPractice:
    """Build practice questions aimed at the weaknesses in `frame`.

    Deterministic: the same results always give the same questions. Questions
    for one topic continue a single template rotation, so two error categories
    in the same topic do not both start with the same kind of question.
    """
    targets, evidence, unsupported = build_targets(frame, total, max_topics, whose)

    items: List[TargetedItem] = []
    next_index: Dict[str, int] = {}
    for target in targets:
        start = next_index.get(target.topic, 0)
        questions = generate_practice_questions(
            topic=target.topic,
            error_type=target.error_type,
            difficulty=target.difficulty,
            count=target.count,
            start=start,
        )
        next_index[target.topic] = start + len(questions)
        items.extend(TargetedItem(question=q, reason=target.reason) for q in questions)

    for number, item in enumerate(items, start=1):
        item.question.number = number
    return TargetedPractice(
        items=items, targets=targets, evidence=evidence, unsupported_topics=unsupported
    )
