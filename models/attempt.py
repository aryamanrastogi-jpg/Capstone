"""Where a student stands on one question set, across every attempt.

THE IDEA
  A student works a set, gets some questions right and some wrong, and comes
  back to re-try only the ones they got wrong. The ones they have settled drop
  out and stay out. That repeats until either everything is settled or they hit
  the attempt cap.

  This module holds the *shape* of that state. `services/attempt_service.py`
  computes it from the submissions and grading results.

WHY A QUESTION "SETTLES" AT FULL MARKS
  The rule is deliberately strict: a question is settled when the student has
  scored full marks on it, not most of them. The whole point of the loop is to
  keep going "until you get everything correct", and a 2.5-out-of-3 that
  quietly counted as done would leave exactly the gap the student came here to
  close.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class QuestionStanding(BaseModel):
    """Where one question has got to across all attempts so far."""

    question_id: str
    max_marks: float = Field(gt=0)

    # The best score reached on this question in any attempt. None if the
    # question has never been attempted.
    best_score: Optional[float] = None

    # Which attempt produced that best score.
    best_on_attempt: Optional[int] = None

    # How many attempts have included this question.
    attempts_used: int = 0

    @property
    def is_settled(self) -> bool:
        """Full marks reached. Settled questions drop out of the next attempt."""
        return self.best_score is not None and self.best_score >= self.max_marks

    @property
    def has_been_attempted(self) -> bool:
        return self.attempts_used > 0

    @property
    def best_percentage(self) -> Optional[float]:
        if self.best_score is None or not self.max_marks:
            return None
        return round(100 * self.best_score / self.max_marks, 1)


class AttemptState(BaseModel):
    """One student's position on one question set."""

    assessment_id: str
    student_id: str
    max_attempts: int

    # Attempts already made. The next one is this + 1.
    attempts_used: int = 0

    standings: List[QuestionStanding] = Field(default_factory=list)

    # ---------------------------------------------------------------- reads
    @property
    def next_attempt_number(self) -> int:
        return self.attempts_used + 1

    @property
    def attempts_remaining(self) -> int:
        return max(0, self.max_attempts - self.attempts_used)

    @property
    def has_started(self) -> bool:
        return self.attempts_used > 0

    @property
    def settled(self) -> List[QuestionStanding]:
        return [s for s in self.standings if s.is_settled]

    @property
    def outstanding(self) -> List[QuestionStanding]:
        """Questions still to get right - what the next attempt covers."""
        return [s for s in self.standings if not s.is_settled]

    @property
    def outstanding_question_ids(self) -> List[str]:
        return [s.question_id for s in self.outstanding]

    @property
    def is_complete(self) -> bool:
        """Every question settled. Nothing left to attempt."""
        return bool(self.standings) and not self.outstanding

    @property
    def is_exhausted(self) -> bool:
        """Out of attempts with questions still outstanding.

        Not a failure state so much as a signal to stop and get help from
        somewhere other than another guess at the same question.
        """
        return not self.is_complete and self.attempts_remaining <= 0

    @property
    def can_attempt(self) -> bool:
        return not self.is_complete and not self.is_exhausted

    @property
    def settled_count(self) -> int:
        return len(self.settled)

    @property
    def progress_fraction(self) -> float:
        """Settled questions as a fraction of the set, in [0, 1]."""
        if not self.standings:
            return 0.0
        return len(self.settled) / len(self.standings)
