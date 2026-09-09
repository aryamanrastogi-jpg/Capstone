"""Student submission model.

Student identifiers are anonymous by design (e.g. "S-2117"). The prototype must
never carry real student names.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Optional

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

    # --- Per-question answers -------------------------------------------
    # question_id -> that question's answer. Empty for a legacy submission,
    # where `submission_text` is one block covering every question.
    #
    # This is what makes the attempt loop possible: to re-try only the
    # questions you got wrong, an answer has to belong to *one* question.
    answers: Dict[str, str] = Field(default_factory=dict)

    uploaded_filename: Optional[str] = None
    submitted_at: datetime = Field(default_factory=datetime.now)

    # Which go at this question set this is. 1 for a first attempt. A later
    # attempt normally covers only the questions still outstanding - see
    # `services/attempt_service.py`.
    attempt_number: int = Field(default=1, ge=1)
    status: SubmissionStatus = SubmissionStatus.PENDING

    # --- Ownership -------------------------------------------------------
    # Which user this belongs to. Set for everything a student uploads, so
    # one student can never be shown another student's work.
    student_id: Optional[str] = None

    # True when a student uploaded their own past work to study from, rather
    # than a teacher collecting it for marking. Self-study results are AI
    # estimates and never become official marks.
    is_self_study: bool = False

    # The mark the teacher actually wrote on the paper, if the student knows
    # it. Comparing this against the AI estimate is what surfaces a possible
    # marking mismatch for the teacher to re-check.
    teacher_awarded_score: Optional[float] = Field(default=None, ge=0)

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

    @field_validator("answers")
    @classmethod
    def _clean_answers(cls, value: Dict[str, str]) -> Dict[str, str]:
        """Strip every answer and drop entries with a blank question id.

        A blank *answer* is kept deliberately: "this question was left blank"
        is real information, and the grader already handles it.
        """
        cleaned: Dict[str, str] = {}
        for question_id, answer in (value or {}).items():
            key = (question_id or "").strip()
            if not key:
                raise ValueError("An answer must be attached to a question id.")
            cleaned[key] = (answer or "").strip()
        return cleaned

    @property
    def is_segmented(self) -> bool:
        """True when answers are held per question rather than as one block."""
        return bool(self.answers)

    def answer_for(self, question_id: str) -> str:
        """The answer to one question.

        Segmented submission: the stored answer, or "" if that question was
        left blank - a missing key means unanswered, not "use everything".
        Legacy submission: the whole text, as every question shares it.
        """
        if self.is_segmented:
            return self.answers.get(question_id, "")
        return self.submission_text
