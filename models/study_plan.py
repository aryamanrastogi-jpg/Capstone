"""Study camps.

A study camp is the "do something about it" half of the product: once the
weakness dashboard shows which topics a student is behind on, the camp turns
that into a short, dated, day-by-day plan built from practice questions.

The improvement story (started at 60%, now at 90%) has to be real, so
`baseline_percentage` is captured once when the camp is created and never
recalculated. `latest_percentage` is derived from the sessions the student has
actually completed.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field


class StudySession(BaseModel):
    """One day of the camp, focused on a single topic."""

    day: int = Field(ge=1)
    topic: str
    questions: List[str] = Field(default_factory=list)
    method_hints: List[str] = Field(default_factory=list)
    skill_focus: str = ""
    completed: bool = False
    # Questions the student got right, self-reported. None until completed.
    score: Optional[int] = None

    @property
    def question_count(self) -> int:
        return len(self.questions)

    @property
    def percentage(self) -> Optional[float]:
        if self.score is None or not self.questions:
            return None
        return round(100 * self.score / len(self.questions), 1)

    @property
    def scheduled_for(self) -> timedelta:
        return timedelta(days=self.day - 1)


class StudyCamp(BaseModel):
    """A short, targeted revision programme for one student."""

    id: str = Field(default_factory=lambda: f"camp_{uuid.uuid4().hex[:8]}")
    student_id: str
    topics: List[str] = Field(default_factory=list)
    started_on: date = Field(default_factory=date.today)
    duration_days: int = Field(ge=1, le=14)
    # Where the student stood when the camp was created. Fixed forever.
    baseline_percentage: float = Field(ge=0, le=100)
    sessions: List[StudySession] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ends_on(self) -> date:
        return self.started_on + timedelta(days=max(0, self.duration_days - 1))

    @property
    def completed_sessions(self) -> List[StudySession]:
        return [s for s in self.sessions if s.completed and s.percentage is not None]

    @property
    def latest_percentage(self) -> Optional[float]:
        """Average across completed sessions, or None if nothing is done yet."""
        done = self.completed_sessions
        if not done:
            return None
        return round(sum(s.percentage for s in done) / len(done), 1)  # type: ignore[misc]

    @property
    def improvement(self) -> Optional[float]:
        """Percentage points gained since the camp started."""
        latest = self.latest_percentage
        if latest is None:
            return None
        return round(latest - self.baseline_percentage, 1)

    @property
    def progress(self) -> float:
        """Fraction of sessions completed, 0.0 to 1.0."""
        if not self.sessions:
            return 0.0
        return len(
            [s for s in self.sessions if s.completed]
        ) / len(self.sessions)

    @property
    def is_complete(self) -> bool:
        return bool(self.sessions) and all(s.completed for s in self.sessions)

    def get_session(self, day: int) -> Optional[StudySession]:
        return next((s for s in self.sessions if s.day == day), None)
