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


GRADE_LEVELS: List[int] = [7, 8, 9]

CURRICULA: List[str] = [
    "CBSE",
    "ICSE",
    "Cambridge IGCSE",
    "IB MYP",
    "State Board",
    "Other",
]


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
    curriculum: str = "CBSE"
    grade_level: int = Field(ge=7, le=9)
    topic: str = Field(min_length=1)
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
