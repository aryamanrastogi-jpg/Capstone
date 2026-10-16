"""Mock exam models.

A mock exam is a timed, in-app sitting built from questions the student can
already see, marked by the same grader as everything else. The sitting itself
lives in session state. Once handed in, its answers and estimates are saved as
self-study work on the sets the questions came from, labelled as a mock exam
(see mock_exam_service.save_to_history), so the result counts in My Progress
and Study Camp without using up attempts.
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
    """One question on the paper, with the topic and set it came from."""

    topic: str
    question: Question
    # The set the question belongs to, which is where its result is saved.
    assessment_id: Optional[str] = None


class MockExam(BaseModel):
    id: str = Field(default_factory=_new_id)
    student_id: str
    topics: List[str] = Field(default_factory=list)
    items: List[MockExamItem] = Field(default_factory=list)
    time_limit_minutes: int = Field(gt=0)
    started_at: datetime
    baseline_percentage: Optional[float] = None
    # Each topic's starting point, fixed when the paper was set: once the
    # result is saved it is part of the history, and a baseline computed
    # afterwards would partly be the exam itself.
    topic_baselines: Dict[str, Optional[float]] = Field(default_factory=dict)
    answers: Dict[str, str] = Field(default_factory=dict)
    submitted_at: Optional[datetime] = None
    submitted_late: bool = False
    results: List[GradingResult] = Field(default_factory=list)
    # True when the AI could not mark and the rule-based grader stood in.
    ai_unavailable: bool = False
    # The self-study records the result was saved as; empty until saved.
    saved_submission_ids: List[str] = Field(default_factory=list)
    save_failed: bool = False

    @property
    def deadline(self) -> datetime:
        return self.started_at + timedelta(minutes=self.time_limit_minutes)

    @property
    def is_submitted(self) -> bool:
        return self.submitted_at is not None

    @property
    def total_marks(self) -> float:
        return sum(item.question.max_marks for item in self.items)
