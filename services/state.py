"""Central Streamlit session-state initialisation.

This is the ONLY module that seeds session state. Pages must call
`init_session_state()` (app.py does it once per run) and then use the accessors
here rather than touching st.session_state keys directly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from data.sample_data import DEMO_STUDENT_ID, build_sample_data
from models import Assessment, GradingResult, Role, StudyCamp, Submission, User
from services.supabase_client import get_connection_status

ASSESSMENTS = "assessments"
SUBMISSIONS = "submissions"
GRADING_RESULTS = "grading_results"
USERS = "users"
STUDY_CAMPS = "study_camps"
CURRENT_USER_ID = "current_user_id"
DEMO_MODE = "demo_mode"
BACKEND_MESSAGE = "backend_message"
BACKEND_IS_ERROR = "backend_is_error"
INITIALISED = "_assessai_initialised"


def init_session_state(load_samples: bool = True) -> None:
    """Seed session state exactly once per browser session."""
    if st.session_state.get(INITIALISED):
        return

    status = get_connection_status()

    assessments: List[Assessment] = []
    submissions: List[Submission] = []
    results: List[GradingResult] = []
    users: List[User] = []

    if load_samples:
        assessments, submissions, results, users = build_sample_data()

    st.session_state[ASSESSMENTS] = assessments
    st.session_state[SUBMISSIONS] = submissions
    st.session_state[GRADING_RESULTS] = results
    st.session_state[USERS] = users
    st.session_state[STUDY_CAMPS] = []
    # Start as a student - they are the primary users of the app.
    student_ids = [u.id for u in users if u.is_student]
    st.session_state[CURRENT_USER_ID] = (
        DEMO_STUDENT_ID
        if DEMO_STUDENT_ID in student_ids
        else (student_ids[0] if student_ids else None)
    )
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


def get_users() -> List[User]:
    return st.session_state.setdefault(USERS, [])


def get_study_camps() -> List[StudyCamp]:
    return st.session_state.setdefault(STUDY_CAMPS, [])


def get_current_user() -> Optional[User]:
    user_id = st.session_state.get(CURRENT_USER_ID)
    return next((u for u in get_users() if u.id == user_id), None)


def set_current_user(user_id: str) -> None:
    st.session_state[CURRENT_USER_ID] = user_id


def get_current_role() -> Role:
    user = get_current_user()
    return user.role if user else Role.STUDENT


def is_student() -> bool:
    return get_current_role() is Role.STUDENT


def is_teacher() -> bool:
    return get_current_role() is Role.TEACHER


def get_current_teacher() -> str:
    """Display name of the signed-in teacher, for the sidebar."""
    user = get_current_user()
    return user.display_name if user else "Unknown"


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
