"""Preview of how an uploaded block of text was split into per-question answers.

Drawing only. The splitting rules live in `services/answer_splitter.py`.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, Optional, Sequence

import streamlit as st

from models import Question
from services.answer_splitter import split_answers

SPLIT_TOGGLE_LABEL = "Grade each question against its own answer"


def _shorten(text: str, limit: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def split_answer_editor(
    text: str,
    questions: Sequence[Question],
    key_prefix: str,
    only_question_ids: Optional[Iterable[str]] = None,
) -> Optional[Dict[str, str]]:
    """Show which text goes to which question, editable, and return the answers.

    Returns question_id -> answer when the split is used, or None when every
    question should be graded against the whole text (the split was not
    confident, or the user turned it off).

    `only_question_ids` limits the editors - and the returned answers - to a
    subset, e.g. the questions still outstanding in a re-attempt. Numbering
    always follows the whole assessment, so Q4 stays Q4.
    """
    split = split_answers(text, questions)
    if not split.confident:
        st.info(
            "**Not split per question.** " + split.message,
            icon=":material/call_split:",
        )
        return None

    use_split = st.toggle(SPLIT_TOGGLE_LABEL, value=True, key=f"{key_prefix}_use_split")
    if not use_split:
        st.caption("Every question will be graded against the whole text above.")
        return None

    st.success(split.message, icon=":material/call_split:")
    st.caption(
        "Check that each answer landed on the right question, and fix anything "
        "that did not before grading."
    )
    if split.preamble:
        with st.expander("Text before the first question marker (not graded)"):
            st.text(split.preamble)

    wanted = set(only_question_ids) if only_question_ids is not None else None
    # Keyed by the source text, so editing the full text above re-splits it
    # rather than leaving stale boxes behind.
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    answers: Dict[str, str] = {}
    for number, question in enumerate(questions, start=1):
        if wanted is not None and question.id not in wanted:
            continue
        answers[question.id] = st.text_area(
            f"Q{number}. {_shorten(question.question_text)}",
            value=split.answers.get(question.id, ""),
            height=110,
            key=f"{key_prefix}_{question.id}_{digest}",
        )
    return answers
