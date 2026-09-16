"""The structured output an AI grader must return.

Why a separate schema from GradingResult: GradingResult carries identity and
review state (submission id, teacher decisions) that a model must never
decide. This schema is only what the model is trusted to propose, and it is
strict - unknown fields are rejected, so a model drifting from the prompt is
caught rather than quietly half-parsed.

Range checks that depend on the question (score <= max_marks) live in the
validator in `services.ai_grading_service`, because the schema alone does not
know the question.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.grading import ErrorType


class AIErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_type: ErrorType
    explanation: str = Field(min_length=1)

    @field_validator("explanation")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("explanation must not be blank")
        return value.strip()


class AIGradingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggested_score: float
    confidence: float = Field(ge=0.0, le=1.0)
    correct_elements: List[str] = Field(default_factory=list)
    errors: List[AIErrorItem] = Field(default_factory=list)
    student_feedback: str = Field(min_length=1)
    teacher_note: str = ""

    @field_validator("suggested_score", "confidence", mode="before")
    @classmethod
    def _real_number(cls, value: object) -> object:
        # Pydantic would coerce "2" or True; a model that returns those is not
        # following the prompt, so refuse instead of guessing.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("must be a JSON number")
        return value

    @field_validator("student_feedback")
    @classmethod
    def _feedback_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("student_feedback must not be blank")
        return value.strip()
