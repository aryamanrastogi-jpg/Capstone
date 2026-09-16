"""AI grading pipeline, built so a provider can be plugged in later.

There is no provider today and no API key, so this module makes NO network
calls and imports NO provider SDK. What it does provide is everything around
the model call that must be right regardless of which model is used:

  * a `GradingModel` protocol - one method, `complete(system, user) -> str`;
  * a registry that picks a provider from LLM_API_KEY / LLM_MODEL;
  * a validator that turns raw model text into a GradingResult or raises
    `AIOutputError` - it never invents or quietly repairs a score;
  * `grade_with_ai`, which falls back to the rule-based grader whenever no
    provider is configured or the output fails validation, and says which path
    it took.

`grade_with_ai` returns an `AIGradingOutcome` wrapping an ordinary
GradingResult, so existing consumers of GradingResult are untouched.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from pydantic import ValidationError

from models import ErrorItem, GradingResult, Question
from models.ai_grading import AIGradingOutput
from services import grading_service
from services.grading_prompt import PROMPT_VERSION, build_grading_prompt
from utils.config import Settings, get_settings

PATH_AI = "ai"
PATH_RULE_BASED = "rule_based"

_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
# A value the model answer *arrives at*: the number after "=", "is", "get(s)",
# "are" or "to". Operands like the "2" in "2 x (12 + 5)" are method, not answer,
# and a pointer such as "double the sum" may legitimately mention them.
_RESULT_PATTERN = re.compile(
    r"(?:=|\bis\b|\bgets?\b|\bare\b|\bto\b)\s*(-?\d+(?:\.\d+)?)"
    r"(?![\d.]*(?:[a-z]|\s*[*/+×÷(-]|\s+x\s))",
    re.IGNORECASE,
)
_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


class AIOutputError(ValueError):
    """The model's output could not be trusted as a grade."""


# --------------------------------------------------------------------------
# Provider interface and registry
# --------------------------------------------------------------------------
@runtime_checkable
class GradingModel(Protocol):
    """Anything that can answer a system + user prompt with text."""

    name: str

    def complete(self, system: str, user: str) -> str: ...


ProviderFactory = Callable[[Settings], GradingModel]

_PROVIDERS: Dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Make a provider selectable via LLM_MODEL="<name>:<model id>"."""
    _PROVIDERS[name.strip().lower()] = factory


def unregister_provider(name: str) -> None:
    _PROVIDERS.pop(name.strip().lower(), None)


def registered_providers() -> List[str]:
    return sorted(_PROVIDERS)


def get_grading_model(settings: Optional[Settings] = None) -> Optional[GradingModel]:
    """The configured model, or None if AI grading is not set up.

    Needs all three: an API key, an LLM_MODEL of the form "provider:model",
    and a registered factory for that provider. Anything less returns None so
    the caller falls back to the rule-based grader rather than failing.
    """
    settings = settings or get_settings()
    if not settings.llm_api_key or not settings.llm_model:
        return None
    provider, _, _model_id = settings.llm_model.partition(":")
    factory = _PROVIDERS.get(provider.strip().lower())
    if factory is None:
        return None
    return factory(settings)


class FakeGradingModel:
    """A scripted model for tests and offline evaluation.

    Returns the given responses in order (repeating the last one), or builds
    one per call from `responder(system, user)`. Records every prompt it saw.
    """

    name = "fake"

    def __init__(
        self,
        responses: Optional[Sequence[str]] = None,
        responder: Optional[Callable[[str, str], str]] = None,
    ) -> None:
        if not responses and responder is None:
            raise ValueError("FakeGradingModel needs responses or a responder.")
        self._responses = list(responses or [])
        self._responder = responder
        self.calls: List[tuple] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self._responder is not None:
            return self._responder(system, user)
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[index]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def _extract_json(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise AIOutputError("The model returned an empty response.")
    fenced = _FENCE_PATTERN.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Tolerate prose around a single JSON object, nothing more.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise AIOutputError("The model response is not JSON.") from None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIOutputError(f"The model response is not valid JSON: {exc.msg}.") from None
    if not isinstance(data, dict):
        raise AIOutputError("The model response must be a JSON object.")
    return data


def _snap_score(score: float, max_marks: float) -> float:
    """Validate the range, then snap to the nearest half mark.

    Out-of-range scores are rejected, not clamped: a model claiming 5/3 has
    misread the question, and clamping would dress that up as full marks.
    """
    if not math.isfinite(score):
        raise AIOutputError("suggested_score must be a finite number.")
    if score < 0 or score > max_marks:
        raise AIOutputError(
            f"suggested_score {score} is outside the allowed range 0..{max_marks}."
        )
    snapped = round(score * 2) / 2
    if snapped > max_marks:  # e.g. max_marks 2.3 and score 2.3 -> 2.0
        snapped = math.floor(max_marks * 2) / 2
    return snapped


def _leaked_values(feedback: str, question: Question, student_answer: str) -> List[str]:
    """Model-answer results in the feedback the student did not already have."""
    known = set(_NUMBER_PATTERN.findall(question.question_text))
    known |= set(_NUMBER_PATTERN.findall(student_answer or ""))
    expected = set(_RESULT_PATTERN.findall(question.model_answer)) - known
    return sorted(expected.intersection(_NUMBER_PATTERN.findall(feedback)))


def parse_ai_output(
    raw: str,
    question: Question,
    student_answer: str,
    submission_id: str,
) -> GradingResult:
    """Turn raw model text into a GradingResult, or raise AIOutputError."""
    data = _extract_json(raw)
    try:
        output = AIGradingOutput.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'response'}: {err['msg']}"
            for err in exc.errors()
        )
        raise AIOutputError(f"The model response failed validation: {problems}.") from None

    score = _snap_score(output.suggested_score, question.max_marks)

    leaks = _leaked_values(output.student_feedback, question, student_answer)
    if leaks:
        raise AIOutputError(
            "student_feedback reveals values from the model answer ("
            + ", ".join(leaks)
            + "); feedback must give pointers, not answers."
        )

    return GradingResult(
        submission_id=submission_id,
        question_id=question.id,
        max_marks=question.max_marks,
        suggested_score=score,
        confidence=round(output.confidence, 2),
        correct_elements=[c.strip() for c in output.correct_elements if c.strip()],
        errors=[
            ErrorItem(error_type=e.error_type, explanation=e.explanation)
            for e in output.errors
        ],
        student_feedback=output.student_feedback,
        teacher_note=output.teacher_note.strip(),
    )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class AIGradingOutcome:
    """A GradingResult plus how it was produced."""

    result: GradingResult
    path: str  # PATH_AI or PATH_RULE_BASED
    engine: str
    prompt_version: Optional[str] = None
    fallback_reason: Optional[str] = None

    @property
    def used_ai(self) -> bool:
        return self.path == PATH_AI


def grade_with_ai(
    question: Question,
    student_answer: str,
    submission_id: str,
    model: Optional[GradingModel] = None,
    settings: Optional[Settings] = None,
) -> AIGradingOutcome:
    """Grade one answer with the AI model, falling back to the rule-based grader.

    Falls back when no model is configured, when the model call raises, or when
    its output fails validation. The reason is kept on the outcome so a teacher
    (or the evaluation script) can see how often the AI path was really used.

    A blank answer is never sent to the model: zero marks needs no judgement,
    and a model has nothing to gain there but the chance to invent credit.

    Raises ValueError for a question with no model answer, exactly like
    `grading_service.grade_answer` - neither path can mark that honestly.
    """
    model = model if model is not None else get_grading_model(settings)
    if model is None:
        return _fallback(question, student_answer, submission_id, "No AI provider is configured.")
    if not (student_answer or "").strip():
        return _fallback(
            question, student_answer, submission_id, "Blank answer - marked without the AI."
        )

    prompt = build_grading_prompt(question, student_answer)  # raises without a model answer
    try:
        raw = model.complete(prompt.system, prompt.user)
    except Exception as exc:  # provider failures must never break grading
        # Only the exception type: provider messages can echo request details.
        return _fallback(
            question, student_answer, submission_id,
            f"The AI provider call failed ({type(exc).__name__}).",
        )

    try:
        result = parse_ai_output(raw, question, student_answer, submission_id)
    except AIOutputError as exc:
        return _fallback(question, student_answer, submission_id, str(exc))

    return AIGradingOutcome(
        result=result,
        path=PATH_AI,
        engine=getattr(model, "name", type(model).__name__),
        prompt_version=prompt.version,
    )


def _fallback(
    question: Question, student_answer: str, submission_id: str, reason: str
) -> AIGradingOutcome:
    return AIGradingOutcome(
        result=grading_service.grade_answer(question, student_answer, submission_id),
        path=PATH_RULE_BASED,
        engine=grading_service.MOCK_ENGINE_NAME,
        fallback_reason=reason,
    )


__all__ = [
    "AIGradingOutcome",
    "AIOutputError",
    "FakeGradingModel",
    "GradingModel",
    "PATH_AI",
    "PATH_RULE_BASED",
    "PROMPT_VERSION",
    "get_grading_model",
    "grade_with_ai",
    "parse_ai_output",
    "register_provider",
    "registered_providers",
    "unregister_provider",
]
