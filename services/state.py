"""Central Streamlit session-state initialisation.

This is the ONLY module that seeds session state. Pages must call
`init_session_state()` (app.py does it once per run) and then use the accessors
here rather than touching st.session_state keys directly.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from data.sample_data import build_sample_data
from models import Assessment, GradingResult, Submission
from services.supabase_client import get_connection_status

ASSESSMENTS = "assessments"
SUBMISSIONS = "submissions"
GRADING_RESULTS = "grading_results"
CURRENT_TEACHER = "current_teacher"
DEMO_MODE = "demo_mode"
BACKEND_MESSAGE = "backend_message"
BACKEND_IS_ERROR = "backend_is_error"
INITIALISED = "_assessai_initialised"

DEFAULT_TEACHER = "Ms. R. Kapoor"


def init_session_state(load_samples: bool = True) -> None:
    """Seed session state exactly once per browser session."""
    if st.session_state.get(INITIALISED):
        return

    status = get_connection_status()

    assessments: List[Assessment] = []
    submissions: List[Submission] = []
    results: List[GradingResult] = []

    if load_samples:
        assessments, submissions, results = build_sample_data()

    st.session_state[ASSESSMENTS] = assessments
    st.session_state[SUBMISSIONS] = submissions
    st.session_state[GRADING_RESULTS] = results
    st.session_state[CURRENT_TEACHER] = DEFAULT_TEACHER
    st.session_state[DEMO_MODE] = status.demo_mode
    st.session_state[BACKEND_MESSAGE] = status.message
    st.session_state[BACKEND_IS_ERROR] = status.is_error
    st.session_state[INITIALISED] = True


# --------------------------------------------------------------------------
# Accessors
# --------------------------------------------------------------------------
def get_assessments() -> List[Assessment]:
    return st.session_state.setdefault(ASSESSMENTS, [])


def get_submissions() -> List[Submission]:
    return st.session_state.setdefault(SUBMISSIONS, [])


def get_grading_results() -> List[GradingResult]:
    return st.session_state.setdefault(GRADING_RESULTS, [])


def get_current_teacher() -> str:
    return st.session_state.get(CURRENT_TEACHER, DEFAULT_TEACHER)


def is_demo_mode() -> bool:
    return bool(st.session_state.get(DEMO_MODE, True))


def backend_status() -> Dict[str, Any]:
    return {
        "demo_mode": is_demo_mode(),
        "message": st.session_state.get(BACKEND_MESSAGE, ""),
        "is_error": bool(st.session_state.get(BACKEND_IS_ERROR, False)),
    }


def reset_to_samples() -> None:
    """Restore the seeded demo dataset (used by the sidebar reset control)."""
    st.session_state[INITIALISED] = False
    init_session_state(load_samples=True)
