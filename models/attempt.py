"""Where a student stands on one question set, across every attempt.

THE IDEA
  A student works a set, gets some questions right and some wrong, and comes
  back to re-try only the ones they got wrong. The ones they have settled drop
  out and stay out. That repeats until either everything is settled or they hit
  the attempt cap.

  This module holds the *shape* of that state. `services/attempt_service.py`
  computes it from the submissions and grading results.

WHEN A QUESTION "SETTLES"
  At `SETTLE_FRACTION` of the marks - 80%, not 100%. The loop is meant to run
  until a student has each question right, but insisting on the very last half
  mark turns it into a grind against the grader's phrasing rather than against
  the maths: the rule-based grader gives 2.5 out of 3 for a fully correct
  answer, and at full marks that never settled.

  The value is chosen around how the marks round rather than picked for being
  a round number - see the comment on the constant.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

# What fraction of the marks counts as having got a question right.
#
# Set to 80% rather than 90% because of how the marks round. Scores come back
# to the nearest half mark, so at 90% a 3-mark question needs 2.7 - and the
# only score at or above that is 3.0, which is full marks by another name.
# At 80% the threshold is 2.4, so 2.5 out of 3 settles, which is what a
# correct-but-differently-worded answer actually scores.
SETTLE_FRACTION = 0.80


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
        """Got it right. Settled questions drop out of the next attempt."""
        if self.best_score is None:
            return False
        return is_settling_score(self.best_score, self.max_marks)

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


def is_settling_score(score: float, max_marks: float) -> bool:
    """Is this score good enough to count the question as done?

    The single definition of settling. `attempt_service` reads it too, so a
    per-attempt result and the standing built from it can never disagree.
    """
    if not max_marks:
        return False
    return score >= SETTLE_FRACTION * max_marks
