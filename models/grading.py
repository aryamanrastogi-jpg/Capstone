"""Grading models.

Every GradingResult is a *recommendation*. Nothing here is final until a
teacher moves review_status away from AWAITING_REVIEW and supplies (or accepts)
an approved score.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class ErrorType(str, Enum):
    ARITHMETIC_ERROR = "arithmetic_error"
    INCORRECT_METHOD = "incorrect_method"
    CONCEPTUAL_ERROR = "conceptual_error"
    INCOMPLETE_ANSWER = "incomplete_answer"
    MISSING_WORKING = "missing_working"
    UNIT_ERROR = "unit_error"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


class ReviewStatus(str, Enum):
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"          # AI recommendation accepted as-is
    EDITED = "edited"              # teacher changed score and/or feedback
    FLAGGED = "flagged"            # teacher rejected / needs another look

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


class ErrorItem(BaseModel):
    error_type: ErrorType
    explanation: str = Field(min_length=1)


class GradingResult(BaseModel):
    submission_id: str
    question_id: str
    max_marks: float = Field(gt=0)
    suggested_score: float = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    correct_elements: List[str] = Field(default_factory=list)
    errors: List[ErrorItem] = Field(default_factory=list)
    student_feedback: str = ""
    teacher_note: str = ""
    review_status: ReviewStatus = ReviewStatus.AWAITING_REVIEW
    teacher_approved_score: Optional[float] = None
    teacher_approved_feedback: Optional[str] = None

    @model_validator(mode="after")
    def _scores_within_bounds(self) -> "GradingResult":
        if self.suggested_score > self.max_marks:
            raise ValueError(
                f"Suggested score ({self.suggested_score}) exceeds the maximum "
                f"marks available ({self.max_marks})."
            )
        approved = self.teacher_approved_score
        if approved is not None:
            if approved < 0:
                raise ValueError("Teacher-approved score cannot be negative.")
            if approved > self.max_marks:
                raise ValueError(
                    f"Teacher-approved score ({approved}) exceeds the maximum "
                    f"marks available ({self.max_marks})."
                )
        return self

    @property
    def is_reviewed(self) -> bool:
        """A teacher has looked at this result (approved, edited or flagged)."""
        return self.review_status != ReviewStatus.AWAITING_REVIEW

    @property
    def is_finalised(self) -> bool:
        """A teacher has settled on a score. Flagged results are NOT finalised."""
        return self.review_status in (ReviewStatus.APPROVED, ReviewStatus.EDITED)

    @property
    def final_score(self) -> Optional[float]:
        """The score that counts, or None if no teacher has settled on one.

        A flagged result deliberately returns None: flagging is a decision to
        withhold approval, so the AI's suggestion must never leak through as
        though it were a real mark.
        """
        if not self.is_finalised:
            return None
        if self.teacher_approved_score is not None:
            return self.teacher_approved_score
        return self.suggested_score

    @property
    def final_feedback(self) -> str:
        return self.teacher_approved_feedback or self.student_feedback
