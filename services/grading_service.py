"""Deterministic mock grading service (Phase 1).

This module makes NO network calls and uses NO LLM. It applies transparent,
repeatable rules so that the review workflow, the analytics page and the tests
all have realistic structured data to work with.

In Phase 2 `grade_answer` is the single function to replace with a real LLM
call: its signature and its GradingResult return type are the contract.

Everything it produces is a *recommendation* - `review_status` always starts at
AWAITING_REVIEW and `teacher_approved_score` always starts as None.
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Optional, Sequence, Set, Tuple

from models import ErrorItem, ErrorType, GradingResult, Question, ReviewStatus

MOCK_ENGINE_NAME = "Rule-based mock grader v1 (no LLM)"

_STOPWORDS: Set[str] = {
    "the", "and", "for", "with", "that", "this", "from", "then", "than", "into",
    "each", "have", "has", "are", "is", "was", "were", "be", "been", "of", "to",
    "in", "on", "at", "by", "we", "so", "as", "it", "its", "a", "an", "you",
    "your", "answer", "step", "steps", "hence", "therefore", "thus", "get",
    "gives", "give", "find", "value", "values", "using", "use",
}

_UNIT_PATTERN = re.compile(
    r"\b(cm|mm|m|km|kg|g|ml|l|s|sec|min|hr|hrs|units?|degrees?|rupees?|rs)\b"
    r"|(?:cm|m|mm)\s*\^?[23]|²|³|%|°",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
_WORKING_PATTERN = re.compile(r"[=+\-x*/]|×|÷|\bbecause\b|\bsince\b", re.IGNORECASE)
_METHOD_KEYWORDS = (
    "formula", "substitute", "solve", "factor", "expand", "simplify", "ratio",
    "proportion", "theorem", "area", "perimeter", "volume", "mean", "median",
    "probability", "equation", "graph", "gradient", "slope", "percentage",
)


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z]+", (text or "").lower())


def _keywords(text: str) -> List[str]:
    seen: List[str] = []
    for token in _tokens(text):
        if len(token) > 2 and token not in _STOPWORDS and token not in seen:
            seen.append(token)
    return seen


def _numbers(text: str) -> List[str]:
    return _NUMBER_PATTERN.findall(text or "")


def _has_units(text: str) -> bool:
    return bool(_UNIT_PATTERN.search(text or ""))


def _has_working(text: str) -> bool:
    return bool(_WORKING_PATTERN.search(text or ""))


def _stable_fraction(*parts: str) -> float:
    """A deterministic value in [0, 1) derived from the inputs."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _round_half(value: float) -> float:
    return round(value * 2) / 2


# --------------------------------------------------------------------------
# The grader
# --------------------------------------------------------------------------
def grade_answer(
    question: Question,
    student_answer: str,
    submission_id: str,
) -> GradingResult:
    """Produce a GradingResult recommendation for one question."""
    student_answer = (student_answer or "").strip()

    if not student_answer:
        return GradingResult(
            submission_id=submission_id,
            question_id=question.id,
            max_marks=question.max_marks,
            suggested_score=0.0,
            confidence=0.95,
            correct_elements=[],
            errors=[
                ErrorItem(
                    error_type=ErrorType.INCOMPLETE_ANSWER,
                    explanation="No response was provided for this question.",
                )
            ],
            student_feedback=(
                "This question was left blank. Have another go - start by writing "
                "down what the question gives you and what it asks for."
            ),
            teacher_note="Blank response. Confirm whether the student ran out of time.",
        )

    model_keywords = _keywords(question.model_answer) + _keywords(question.marking_criteria)
    model_keywords = list(dict.fromkeys(model_keywords))
    student_tokens = set(_tokens(student_answer))

    matched = [kw for kw in model_keywords if kw in student_tokens]
    missing = [kw for kw in model_keywords if kw not in student_tokens]
    coverage = len(matched) / len(model_keywords) if model_keywords else 0.5

    model_numbers = _numbers(question.model_answer)
    student_numbers = _numbers(student_answer)
    shared_numbers = [n for n in model_numbers if n in student_numbers]
    number_coverage = len(shared_numbers) / len(model_numbers) if model_numbers else None

    alignment = _alignment(coverage, number_coverage)

    correct_elements, errors, penalty = _assess(
        question=question,
        student_answer=student_answer,
        matched=matched,
        missing=missing,
        coverage=coverage,
        alignment=alignment,
        student_numbers=student_numbers,
        shared_numbers=shared_numbers,
        number_coverage=number_coverage,
    )

    raw_score = question.max_marks * max(0.0, alignment - penalty)
    suggested = max(0.0, min(_round_half(raw_score), question.max_marks))

    confidence = _confidence(
        coverage=alignment,
        number_coverage=number_coverage,
        error_count=len(errors),
        seed=(submission_id, question.id),
    )

    return GradingResult(
        submission_id=submission_id,
        question_id=question.id,
        max_marks=question.max_marks,
        suggested_score=suggested,
        confidence=confidence,
        correct_elements=correct_elements,
        errors=errors,
        student_feedback=_student_feedback(
            suggested, question.max_marks, correct_elements, errors
        ),
        teacher_note=_teacher_note(confidence, errors, missing),
    )


def _alignment(coverage: float, number_coverage: Optional[float]) -> float:
    """How close the response is to the model answer, in [0, 1].

    Two independent channels of evidence: wording (keyword coverage) and
    results (numeric agreement). A maths answer can be entirely correct while
    using almost none of the model answer's words - "350/100 = 3.5, x 20 = 70"
    is a complete solution - so numeric agreement alone must be able to earn
    most of the marks, and neither channel is allowed to veto the other.
    """
    if number_coverage is None:
        return coverage
    blended = 0.5 * coverage + 0.5 * number_coverage
    strongest = 0.85 * max(coverage, number_coverage)
    return min(1.0, max(blended, strongest))


def _assess(
    question: Question,
    student_answer: str,
    matched: Sequence[str],
    missing: Sequence[str],
    coverage: float,
    alignment: float,
    student_numbers: Sequence[str],
    shared_numbers: Sequence[str],
    number_coverage: Optional[float],
) -> Tuple[List[str], List[ErrorItem], float]:
    """Return (correct elements, detected errors, score penalty in [0, 1])."""
    correct: List[str] = []
    errors: List[ErrorItem] = []
    penalty = 0.0

    if matched:
        correct.append("Uses the expected ideas: " + ", ".join(list(matched)[:5]) + ".")
    if shared_numbers:
        correct.append(
            "Reaches expected values: " + ", ".join(list(shared_numbers)[:5]) + "."
        )
    if _has_working(student_answer):
        correct.append("Working is shown rather than a bare answer.")
    if _has_units(student_answer) and _has_units(question.model_answer):
        correct.append("Units are stated with the answer.")

    # --- Missing working ---
    if not _has_working(student_answer) and len(student_answer.split()) < 25:
        errors.append(
            ErrorItem(
                error_type=ErrorType.MISSING_WORKING,
                explanation=(
                    "The answer is given without any visible working, so the method "
                    "cannot be credited."
                ),
            )
        )
        penalty += 0.15

    # --- Arithmetic vs conceptual, judged on numeric agreement ---
    if number_coverage is not None:
        if number_coverage == 0 and student_numbers:
            if coverage >= 0.4:
                errors.append(
                    ErrorItem(
                        error_type=ErrorType.ARITHMETIC_ERROR,
                        explanation=(
                            "The method looks reasonable but none of the calculated "
                            "values match the expected results - check the computation."
                        ),
                    )
                )
                penalty += 0.20
            else:
                errors.append(
                    ErrorItem(
                        error_type=ErrorType.CONCEPTUAL_ERROR,
                        explanation=(
                            "Neither the reasoning nor the values match the expected "
                            "solution, which suggests the underlying concept is unclear."
                        ),
                    )
                )
                penalty += 0.30
        elif 0 < number_coverage < 1:
            errors.append(
                ErrorItem(
                    error_type=ErrorType.ARITHMETIC_ERROR,
                    explanation=(
                        "Some intermediate values match the expected solution and "
                        "others do not - one of the calculation steps is likely wrong."
                    ),
                )
            )
            penalty += 0.10

    # --- Incorrect method ---
    expected_methods = [kw for kw in _METHOD_KEYWORDS if kw in question.model_answer.lower()]
    if (
        expected_methods
        and alignment < 0.7
        and not any(m in student_answer.lower() for m in expected_methods)
    ):
        errors.append(
            ErrorItem(
                error_type=ErrorType.INCORRECT_METHOD,
                explanation=(
                    "The expected approach ("
                    + ", ".join(expected_methods[:3])
                    + ") does not appear in the response."
                ),
            )
        )
        penalty += 0.15

    # --- Incomplete answer ---
    if alignment < 0.5 and missing:
        errors.append(
            ErrorItem(
                error_type=ErrorType.INCOMPLETE_ANSWER,
                explanation=(
                    "Key parts of the expected answer are not addressed: "
                    + ", ".join(list(missing)[:4])
                    + "."
                ),
            )
        )
        penalty += 0.10

    # --- Conceptual error on very low coverage ---
    if alignment < 0.2 and not any(e.error_type == ErrorType.CONCEPTUAL_ERROR for e in errors):
        errors.append(
            ErrorItem(
                error_type=ErrorType.CONCEPTUAL_ERROR,
                explanation=(
                    "The response does not engage with the concept the question is "
                    "testing."
                ),
            )
        )
        penalty += 0.25

    # --- Unit error ---
    if _has_units(question.model_answer) and not _has_units(student_answer):
        errors.append(
            ErrorItem(
                error_type=ErrorType.UNIT_ERROR,
                explanation=(
                    "The expected answer carries a unit, but no unit is given in the "
                    "response."
                ),
            )
        )
        penalty += 0.10

    if not correct:
        correct.append("An attempt was made at the question.")

    return correct, errors, min(penalty, 1.0)


def _confidence(
    coverage: float,
    number_coverage: Optional[float],
    error_count: int,
    seed: Tuple[str, str],
) -> float:
    """Deterministic confidence in [0.35, 0.97].

    High when the response is clearly close to (or clearly far from) the model
    answer; lower when the evidence is mixed or many error types fired.
    """
    decisiveness = abs(coverage - 0.5) * 2  # 0 when ambiguous, 1 at the extremes
    if number_coverage is not None:
        decisiveness = 0.6 * decisiveness + 0.4 * abs(number_coverage - 0.5) * 2

    base = 0.55 + 0.35 * decisiveness
    base -= 0.05 * max(0, error_count - 1)
    jitter = (_stable_fraction(*seed) - 0.5) * 0.06  # stable across runs
    return round(min(0.97, max(0.35, base + jitter)), 2)


def _student_feedback(
    score: float,
    max_marks: float,
    correct_elements: Sequence[str],
    errors: Sequence[ErrorItem],
) -> str:
    ratio = score / max_marks if max_marks else 0.0
    if ratio >= 0.85:
        opener = "Really strong work here."
    elif ratio >= 0.6:
        opener = "Good effort - you are most of the way there."
    elif ratio >= 0.3:
        opener = "You have made a start, and there is a clear way to improve."
    else:
        opener = "This one needs another look, and that is completely fine."

    praise = ""
    if correct_elements:
        first = correct_elements[0]
        praise = "What worked: " + first[0].lower() + first[1:]

    tips = {
        ErrorType.ARITHMETIC_ERROR: "Re-check each calculation line by line.",
        ErrorType.INCORRECT_METHOD: "Revisit which method this type of question needs.",
        ErrorType.CONCEPTUAL_ERROR: "Go back over the idea being tested before retrying.",
        ErrorType.INCOMPLETE_ANSWER: "Make sure every part of the question is answered.",
        ErrorType.MISSING_WORKING: "Show your working so each step can earn marks.",
        ErrorType.UNIT_ERROR: "Always finish with the correct unit.",
    }
    next_steps = list(
        dict.fromkeys(tips[e.error_type] for e in errors if e.error_type in tips)
    )[:2]

    parts = [opener]
    if praise:
        parts.append(praise)
    if next_steps:
        parts.append("Next step: " + " ".join(next_steps))
    return " ".join(parts)


def _teacher_note(
    confidence: float,
    errors: Sequence[ErrorItem],
    missing: Sequence[str],
) -> str:
    if confidence < 0.5:
        note = "Low confidence - please read the full response before deciding."
    elif confidence < 0.75:
        note = "Moderate confidence - worth a quick check against the marking criteria."
    else:
        note = "High confidence, but the score is still only a recommendation."
    if len(errors) >= 3:
        note += " Several error types fired; the response may be partially off-topic."
    elif missing:
        note += " Unmatched criteria terms: " + ", ".join(list(missing)[:3]) + "."
    return note


def apply_teacher_decision(
    result: GradingResult,
    status: ReviewStatus,
    score: Optional[float] = None,
    feedback: Optional[str] = None,
) -> GradingResult:
    """Record a teacher's review decision on a grading result.

    This is the only place a result stops being a recommendation, so the rules
    live here rather than in the page:

      * FLAGGED clears any approved score - a flagged result must never count.
      * Approving or editing always stores a score inside [0, max_marks].
      * A decision identical to the AI suggestion is APPROVED, not EDITED.
    """
    if status == ReviewStatus.FLAGGED:
        result.teacher_approved_score = None
        result.teacher_approved_feedback = None
        result.review_status = ReviewStatus.FLAGGED
        return result

    if status == ReviewStatus.AWAITING_REVIEW:
        result.teacher_approved_score = None
        result.teacher_approved_feedback = None
        result.review_status = ReviewStatus.AWAITING_REVIEW
        return result

    chosen_score = result.suggested_score if score is None else float(score)
    chosen_score = round(max(0.0, min(chosen_score, result.max_marks)), 2)
    chosen_feedback = (feedback if feedback is not None else result.student_feedback).strip()

    unchanged = (
        abs(chosen_score - result.suggested_score) < 1e-9
        and chosen_feedback == result.student_feedback.strip()
    )

    result.teacher_approved_score = chosen_score
    result.teacher_approved_feedback = chosen_feedback
    result.review_status = ReviewStatus.APPROVED if unchanged else ReviewStatus.EDITED
    return result


def grade_submission(
    questions: Sequence[Question],
    submission_text: str,
    submission_id: str,
) -> List[GradingResult]:
    """Grade a whole submission.

    A submission is one block of text covering every question, so each question
    is assessed against the same response. This mirrors the shape a real LLM
    call would take and keeps the review UI honest.
    """
    return [grade_answer(q, submission_text, submission_id) for q in questions]
