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

from components.layout import inject_styles, sidebar_status  # noqa: E402
from components.navigation import build_navigation  # noqa: E402
from services.state import get_current_role, init_session_state  # noqa: E402
from utils.config import APP_NAME, APP_TAGLINE  # noqa: E402

st.set_page_config(
    page_title=APP_NAME,
    page_icon=os.path.join(PROJECT_ROOT, "assets", "icon.svg"),
    layout="wide",
    # "auto", not "expanded": on a phone an expanded sidebar covers the page,
    # and the student has to dismiss it before they can read anything.
    initial_sidebar_state="auto",
    menu_items={"about": f"{APP_NAME} - {APP_TAGLINE}"},
)

# The wordmark sits above the navigation, where a brand belongs; the square
# mark is what shows once the sidebar is collapsed.
st.logo(
    os.path.join(PROJECT_ROOT, "assets", "logo.svg"),
    icon_image=os.path.join(PROJECT_ROOT, "assets", "icon.svg"),
    size="large",
)

# One style block per rerun, before anything draws.
inject_styles()

# Seed assessments, submissions, grading results, users and demo-mode flag.
init_session_state()

# The sidebar owns the demo role switch, so it must run before navigation is
# built - switching role changes which pages exist.
sidebar_status()

build_navigation(get_current_role()).run()
