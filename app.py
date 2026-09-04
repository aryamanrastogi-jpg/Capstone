"""AssessAI - teacher-facing AI-assisted assessment platform.

Entry point. Run with:

    streamlit run app.py

Responsibilities kept here and nowhere else:
  * page configuration
  * one-time session-state initialisation
  * navigation assembly

Every AI-produced score or comment in this application is a recommendation.
A teacher reviews and approves each one before it counts.
"""

from __future__ import annotations

import os
import sys

import streamlit as st

# Make the project root importable regardless of how Streamlit is launched.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from components.layout import sidebar_status  # noqa: E402
from components.navigation import build_navigation  # noqa: E402
from services.state import get_current_role, init_session_state  # noqa: E402
from utils.config import APP_NAME, APP_TAGLINE  # noqa: E402

st.set_page_config(
    page_title=APP_NAME,
    page_icon=":material/school:",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"about": f"{APP_NAME} - {APP_TAGLINE}"},
)

# Seed assessments, submissions, grading results, users and demo-mode flag.
init_session_state()

# The sidebar owns the demo role switch, so it must run before navigation is
# built - switching role changes which pages exist.
sidebar_status()

build_navigation(get_current_role()).run()
