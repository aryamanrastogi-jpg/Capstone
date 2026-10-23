"""The survey dialog behind the sidebar's Feedback button."""

from __future__ import annotations

import streamlit as st

from services import feedback_service
from services.feedback_service import MAX_FEEDBACK_CHARS

_FIELDS = ("feedback_rating", "feedback_suggestion", "feedback_comments")
_NOTICE = "feedback_notice"
_ICONS = {"success": ":material/check_circle:", "info": ":material/info:"}


@st.dialog("Tell us what you think")
def feedback_dialog() -> None:
    """Three questions; nothing is required except the rating."""
    # The result of the last send, shown above a now-empty form.
    notice = st.session_state.pop(_NOTICE, None)
    if notice:
        level, message = notice
        show = st.success if level == "success" else st.info
        show(message, icon=_ICONS[level])

    with st.form("feedback_form", border=False):
        st.markdown("**1. How would you rate the app?**")
        stars = st.feedback("stars", key="feedback_rating")
        suggestion = st.text_area(
            "2. What do you think we should include in the app?",
            max_chars=MAX_FEEDBACK_CHARS,
            placeholder="A feature, a topic, a kind of practice...",
            key="feedback_suggestion",
        )
        comments = st.text_area(
            "3. Any feedback?",
            max_chars=MAX_FEEDBACK_CHARS,
            placeholder="What works, what doesn't, anything else.",
            key="feedback_comments",
        )
        sent = st.form_submit_button("Send feedback", type="primary", width="stretch")

    if not sent:
        return

    # st.feedback counts stars from 0.
    rating = None if stars is None else stars + 1
    outcome = feedback_service.submit(rating, suggestion, comments)
    if outcome.level == "error":
        # Keep what they typed: a missing star should not cost them their text.
        st.error(outcome.message, icon=":material/error:")
        return

    # Sent (or the demo's "not sent"): empty the form so a second click cannot
    # send the same answer again.
    for key in _FIELDS:
        st.session_state.pop(key, None)
    st.session_state[_NOTICE] = (outcome.level, outcome.message)
    st.rerun(scope="fragment")
