"""Guidance: what a student gets when they have a question and no answer.

This is the deliberate counterpart to `GradingResult`. A GradingResult says
"here is how your attempt scored". A Guidance says "here is how to go at this",
and it is produced *before* any attempt exists.

The hard rule: Guidance is derived from the question text alone. It never sees
a model answer, so it cannot leak one. That is not a convention to remember -
it is enforced by `hint_service.guidance_for`, which is only ever passed the
question, and by a test that feeds it a question whose model answer is known
and checks none of those values come back.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class Guidance(BaseModel):
    """How to approach one question, without answering it."""

    question_id: str
    question_text: str

    # What kind of question this looks like ("linear equation", "area and
    # perimeter", ...). Shown to the student so they can tell us when the
    # reading is wrong.
    shape: str

    # The method, in order. Steps describe what to *do*, never what the answer
    # comes out as.
    approach: List[str] = Field(default_factory=list)

    # What a full answer contains - the things that earn the marks.
    include: List[str] = Field(default_factory=list)

    # Mistakes this kind of question invites.
    watch_out_for: List[str] = Field(default_factory=list)

    @property
    def is_specific(self) -> bool:
        """False when we fell back to generic advice rather than recognising it.

        Worth surfacing: generic guidance is honest but much less useful, and a
        lot of it means the shape rules need widening.
        """
        return self.shape != GENERIC_SHAPE


GENERIC_SHAPE = "general"
