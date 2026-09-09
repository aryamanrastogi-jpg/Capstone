"""Status badges.

One place decides what colour a review status, submission status or confidence
level is shown in, so the whole app stays visually consistent.
"""

from __future__ import annotations

from typing import Tuple

import streamlit as st

from models import ReviewStatus, SubmissionStatus
from utils import palette

# status -> (background, text colour, label, icon)
_REVIEW_STYLES = {
    ReviewStatus.AWAITING_REVIEW: (*palette.TINT_WARNING, "Awaiting review", "⏳"),
    ReviewStatus.APPROVED: (*palette.TINT_CORRECT, "Approved", "✓"),
    ReviewStatus.EDITED: (*palette.TINT_PRIMARY, "Edited by teacher", "✎"),
    ReviewStatus.FLAGGED: (*palette.TINT_INCORRECT, "Flagged", "⚑"),
}

_SUBMISSION_STYLES = {
    SubmissionStatus.PENDING: (*palette.TINT_NEUTRAL, "Not graded", "•"),
    SubmissionStatus.GRADED: (*palette.TINT_WARNING, "Awaiting review", "⏳"),
    SubmissionStatus.REVIEWED: (*palette.TINT_CORRECT, "Reviewed", "✓"),
}


def _badge_html(background: str, colour: str, text: str) -> str:
    return (
        f'<span class="assessai-badge" style="background:{background};color:{colour};">'
        f"{text}</span>"
    )


def review_status_badge(status: ReviewStatus, render: bool = True) -> str:
    background, colour, label, icon = _REVIEW_STYLES[status]
    html = _badge_html(background, colour, f"{icon} {label}")
    if render:
        st.markdown(html, unsafe_allow_html=True)
    return html


def submission_status_badge(status: SubmissionStatus, render: bool = True) -> str:
    background, colour, label, icon = _SUBMISSION_STYLES[status]
    html = _badge_html(background, colour, f"{icon} {label}")
    if render:
        st.markdown(html, unsafe_allow_html=True)
    return html


def confidence_badge(confidence: float, render: bool = True) -> str:
    background, colour, label = _confidence_style(confidence)
    html = _badge_html(background, colour, f"{label} confidence · {confidence:.0%}")
    if render:
        st.markdown(html, unsafe_allow_html=True)
    return html


def _confidence_style(confidence: float) -> Tuple[str, str, str]:
    if confidence >= 0.75:
        return (*palette.TINT_CORRECT, "High")
    if confidence >= 0.5:
        return (*palette.TINT_WARNING, "Moderate")
    return (*palette.TINT_INCORRECT, "Low")


def review_status_label(status: ReviewStatus) -> str:
    """Plain-text label, for tables and select boxes."""
    return _REVIEW_STYLES[status][2]


def submission_status_label(status: SubmissionStatus) -> str:
    return _SUBMISSION_STYLES[status][2]


def outcome_badge(is_settled: bool, render: bool = True) -> str:
    """Green when a question is settled, red while it still needs another go.

    Only ever a verdict on this attempt - the wording carries no part of the
    model answer, so showing it to a student is safe.
    """
    background, colour, text = (
        (*palette.TINT_CORRECT, "✓ Settled") if is_settled
        else (*palette.TINT_INCORRECT, "↺ Another go")
    )
    html = _badge_html(background, colour, text)
    if render:
        st.markdown(html, unsafe_allow_html=True)
    return html


def error_chip(label: str, render: bool = True) -> str:
    html = _badge_html(*palette.TINT_INCORRECT, label)
    if render:
        st.markdown(html, unsafe_allow_html=True)
    return html
