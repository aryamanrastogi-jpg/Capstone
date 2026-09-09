"""Rendering for the attempt loop: progress, and comparing your attempts.

Drawing only. The history comes from `services/attempt_service.py` and every
piece of feedback still goes through `grading_service.student_safe_view`, so
the comparison cannot become a way of reading the model answer.
"""

from __future__ import annotations

from typing import Sequence

import streamlit as st

from components.layout import badge_row, hint_note
from components.status_badges import error_chip, outcome_badge
from models import Question, Subject
from services import hint_service
from services.grading_service import student_safe_view

# How many attempt tiles sit side by side before the next one wraps.
_ATTEMPTS_PER_ROW = 3


def attempt_comparison(
    question: Question,
    number: int,
    history: Sequence[dict],
    subject: Subject = Subject.MATHEMATICS,
) -> None:
    """Show every go at one question side by side, oldest first.

    Seeing attempt 1 next to attempt 2 is the point: what a student changed
    between them is the actual learning, and it is invisible if they only ever
    see the latest result.
    """
    if not history:
        return

    st.markdown(f"**Q{number}.** {question.question_text}")

    # Three across is the most that stays readable on a laptop, and the layout
    # CSS collapses each row to a single column on a phone. A fourth and fifth
    # go therefore start a new row instead of shrinking every earlier one.
    entries = list(history)
    for start in range(0, len(entries), _ATTEMPTS_PER_ROW):
        chunk = entries[start : start + _ATTEMPTS_PER_ROW]
        columns = st.columns(len(chunk))
        for column, entry in zip(columns, chunk):
            with column:
                with st.container(border=True):
                    _attempt_column(history, entry, question, subject)

    latest = history[-1]
    if not latest["is_settled"]:
        # More goes at the same question earns a more pointed hint - never more
        # of the answer. See `hint_service.escalating_pointers`.
        level = hint_service.hint_level_for(len(history))
        hint_note(f"What to change next time · hint level {level}")
        view = student_safe_view(latest["result"], question, subject, hint_level=level)
        for pointer in view["pointers"]:
            st.markdown(f"- {pointer}")


def _attempt_column(
    history: Sequence[dict],
    entry: dict,
    question: Question,
    subject: Subject,
) -> None:
    """One attempt's tile: score, verdict, what was written, what was flagged."""
    previous = _previous_score(history, entry)
    delta = None
    if previous is not None:
        change = entry["score"] - previous
        delta = f"{change:+g}" if change else "no change"

    st.metric(
        f"Attempt {entry['attempt_number']}",
        f"{entry['score']:g}/{entry['max_marks']:g}",
        delta=delta,
        delta_color="normal" if delta and delta != "no change" else "off",
    )
    outcome_badge(entry["is_settled"])

    answer = (entry["answer"] or "").strip()
    st.caption("What you wrote")
    st.text(answer if answer else "(left blank)")

    view = student_safe_view(entry["result"], question, subject)
    if view["error_labels"]:
        badge_row(error_chip(label, render=False) for label in view["error_labels"])
    else:
        st.caption("Nothing flagged.")


def _previous_score(history: Sequence[dict], entry: dict) -> float | None:
    """The score on the attempt before this one, or None for the first."""
    index = list(history).index(entry)
    if index == 0:
        return None
    return history[index - 1]["score"]
