"""Mock exam models.

A mock exam is a timed, in-app sitting built from questions the student can
already see, marked by the same grader as everything else. It lives in session
state only: it is practice, not a record, so it never feeds the class analytics.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from models.assessment import Question
from models.grading import GradingResult


def _new_id() -> str:
    return f"mx_{uuid.uuid4().hex[:8]}"


class MockExamItem(BaseModel):
    """One question on the paper, with the topic it came from."""

    topic: str
    question: Question


class MockExam(BaseModel):
    id: str = Field(default_factory=_new_id)
    student_id: str
    topics: List[str] = Field(default_factory=list)
    items: List[MockExamItem] = Field(default_factory=list)
    time_limit_minutes: int = Field(gt=0)
    started_at: datetime
    baseline_percentage: Optional[float] = None
    answers: Dict[str, str] = Field(default_factory=dict)
    submitted_at: Optional[datetime] = None
    submitted_late: bool = False
    results: List[GradingResult] = Field(default_factory=list)

    @property
    def deadline(self) -> datetime:
        return self.started_at + timedelta(minutes=self.time_limit_minutes)

    @property
    def is_submitted(self) -> bool:
        return self.submitted_at is not None

    @property
    def total_marks(self) -> float:
        return sum(item.question.max_marks for item in self.items)
