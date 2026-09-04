"""Student submission model.

Student identifiers are anonymous by design (e.g. "S-2117"). The prototype must
never carry real student names.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SubmissionStatus(str, Enum):
    PENDING = "pending"          # received, not graded yet
    GRADED = "graded"            # AI suggestions exist, awaiting teacher review
    REVIEWED = "reviewed"        # teacher has signed off on every question


class Submission(BaseModel):
    id: str = Field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:8]}")
    assessment_id: str
    student_identifier: str = Field(min_length=1, max_length=40)
    submission_text: str = Field(min_length=1)
    uploaded_filename: Optional[str] = None
    submitted_at: datetime = Field(default_factory=datetime.now)
    status: SubmissionStatus = SubmissionStatus.PENDING

    @field_validator("student_identifier")
    @classmethod
    def _anonymous_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Student identifier must not be blank.")
        return cleaned

    @field_validator("submission_text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Submission text must not be empty.")
        return cleaned
