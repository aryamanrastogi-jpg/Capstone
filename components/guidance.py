"""Rendering for Guidance - how to approach a question, without answering it.

Drawing only. Everything shown here comes from `services/hint_service.py`,
which builds guidance from the question text alone.
"""

from __future__ import annotations

from typing import Sequence

import streamlit as st

from components.layout import hint_note
from models.guidance import Guidance


def guidance_block(guidance: Guidance, number: int | None = None) -> None:
    """Draw the guidance for one question."""
    heading = f"**Q{number}.** " if number is not None else ""
    st.markdown(f"{heading}{guidance.question_text}")
    st.caption(f":material/category: Read as: {guidance.shape}")

    hint_note("How to go at it")
    for step_number, step in enumerate(guidance.approach, start=1):
        st.markdown(f"{step_number}. {step}")

    if guidance.include:
        st.markdown("*What a full answer contains*")
        for item in guidance.include:
            st.markdown(f"- {item}")

    if guidance.watch_out_for:
        st.markdown("*Easy marks to lose*")
        for item in guidance.watch_out_for:
            st.markdown(f"- {item}")


def guidance_list(items: Sequence[Guidance]) -> None:
    """Draw guidance for a whole set of questions."""
    for index, guidance in enumerate(items, start=1):
        with st.container(border=True):
            guidance_block(guidance, number=index)
