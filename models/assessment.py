"""Assessment and Question models.

The subject is modelled as a permissive enum-like string so that additional
subjects (science, economics, ...) can be added later without a schema change.
Mathematics is the only subject exercised in Phase 1.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class Subject(str, Enum):
    """Subjects the platform knows about. Extend this list to add subjects."""

    MATHEMATICS = "Mathematics"
    SCIENCE = "Science"
    ENGLISH = "English"

    @classmethod
    def values(cls) -> List[str]:
        return [member.value for member in cls]


class AssessmentType(str, Enum):
    """What kind of work this is.

    The type matters for the weakness analysis: a mock exam is stronger
    evidence of exam readiness than a piece of homework, and being able to
    separate them is what makes a term of history readable.
    """

    HOMEWORK = "homework"
    EXERCISE = "exercise"
    MOCK_EXAM = "mock_exam"
    EXAM = "exam"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()

    @classmethod
    def labels(cls) -> List[str]:
        return [member.label for member in cls]

    @classmethod
    def from_label(cls, label: str) -> "AssessmentType":
        for member in cls:
            if member.label == label:
                return member
        raise ValueError(f"Unknown assessment type '{label}'.")


GRADE_LEVELS: List[int] = [7, 8, 9, 10, 11]

# Cambridge IGCSE is the focus curriculum; the others are here so the model
# does not have to change when a second curriculum is added.
CURRICULA: List[str] = [
    "Cambridge IGCSE",
    "CBSE",
    "ICSE",
    "IB MYP",
    "State Board",
    "Other",
]

DEFAULT_CURRICULUM = "Cambridge IGCSE"


class Question(BaseModel):
    """A single question with its model answer and marking criteria."""

    id: str = Field(default_factory=lambda: _new_id("q"))
    question_text: str = Field(min_length=1)
    model_answer: str = Field(min_length=1)
    marking_criteria: str = ""
    max_marks: float = Field(gt=0, le=100)

    @field_validator("question_text", "model_answer")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be blank.")
        return cleaned

    @field_validator("marking_criteria")
    @classmethod
    def _strip_criteria(cls, value: str) -> str:
        return value.strip()


class Assessment(BaseModel):
    """A teacher-authored assessment made up of one or more questions."""

    id: str = Field(default_factory=lambda: _new_id("as"))
    title: str = Field(min_length=1)
    subject: Subject = Subject.MATHEMATICS
    curriculum: str = DEFAULT_CURRICULUM
    grade_level: int = Field(ge=7, le=11)
    topic: str = Field(min_length=1)
    assessment_type: AssessmentType = AssessmentType.HOMEWORK
    max_marks: float = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=datetime.now)
    questions: List[Question] = Field(default_factory=list)

    @field_validator("title", "topic", "curriculum")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be blank.")
        return cleaned

    @model_validator(mode="after")
    def _sync_total_marks(self) -> "Assessment":
        """Total marks are always derived from the questions."""
        if not self.questions:
            raise ValueError("An assessment must contain at least one question.")
        total = round(sum(q.max_marks for q in self.questions), 2)
        object.__setattr__(self, "max_marks", total)
        return self

    @property
    def question_count(self) -> int:
        return len(self.questions)

    def get_question(self, question_id: str) -> Question | None:
        return next((q for q in self.questions if q.id == question_id), None)
