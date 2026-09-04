"""Status badges.

One place decides what colour a review status, submission status or confidence
level is shown in, so the whole app stays visually consistent.
"""

from __future__ import annotations

from typing import Tuple

import streamlit as st

from models import ReviewStatus, SubmissionStatus

# status -> (background, text colour, label, icon)
_REVIEW_STYLES = {
    ReviewStatus.AWAITING_REVIEW: ("#FEF3C7", "#92400E", "Awaiting review", "⏳"),
    ReviewStatus.APPROVED: ("#DCFCE7", "#166534", "Approved", "✓"),
    ReviewStatus.EDITED: ("#DBEAFE", "#1E40AF", "Edited by teacher", "✎"),
    ReviewStatus.FLAGGED: ("#FEE2E2", "#991B1B", "Flagged", "⚑"),
}

_SUBMISSION_STYLES = {
    SubmissionStatus.PENDING: ("#F1F5F9", "#334155", "Not graded", "•"),
    SubmissionStatus.GRADED: ("#FEF3C7", "#92400E", "Awaiting review", "⏳"),
    SubmissionStatus.REVIEWED: ("#DCFCE7", "#166534", "Reviewed", "✓"),
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
        return "#DCFCE7", "#166534", "High"
    if confidence >= 0.5:
        return "#FEF3C7", "#92400E", "Moderate"
    return "#FEE2E2", "#991B1B", "Low"


def review_status_label(status: ReviewStatus) -> str:
    """Plain-text label, for tables and select boxes."""
    return _REVIEW_STYLES[status][2]


def submission_status_label(status: SubmissionStatus) -> str:
    return _SUBMISSION_STYLES[status][2]


def error_chip(label: str, render: bool = True) -> str:
    html = _badge_html("#FEE2E2", "#991B1B", label)
    if render:
        st.markdown(html, unsafe_allow_html=True)
    return html
