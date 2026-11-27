"""Camp Prep AI - teacher-facing AI-assisted assessment platform.

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

from components.layout import inject_styles, scroll_to_top, sidebar_status  # noqa: E402
from components.navigation import (  # noqa: E402
    PAGE_SPECS,
    REQUESTED_PAGE,
    build_exam_navigation,
    build_navigation,
    pages_for,
    run_page,
)
from services.state import (  # noqa: E402
    get_current_role,
    init_session_state,
    should_show_landing,
)
from utils.config import APP_NAME, APP_SLOGAN, APP_TAGLINE  # noqa: E402

st.set_page_config(
    # No page_title here: run_page() sets it for the page being shown, so each
    # tab reads "<page> · Camp Prep AI" (BUG-031, BUG-021).
    page_icon=os.path.join(PROJECT_ROOT, "assets", "icon.svg"),
    layout="wide",
    # "auto", not "expanded": on a phone an expanded sidebar covers the page,
    # and the student has to dismiss it before they can read anything.
    initial_sidebar_state="auto",
    menu_items={"about": f"{APP_NAME} - {APP_SLOGAN}. {APP_TAGLINE}"},
)

# One style block per rerun, before anything draws.
inject_styles()

# Which screen the last run drew: the welcome page, or the app.
SCREEN = "_screen"


def _arrive_on(screen: str) -> None:
    """Scroll to the top when the visitor moves between the welcome page and the
    app (demo, sign in, sign out, the Welcome page button). Streamlit keeps the
    scroll position across that swap, so somebody who scrolled down to a button
    opened the next screen mid-page (BUG-023). Not on the first load, not on
    every run: only when the screen changes."""
    if st.session_state.get(SCREEN) not in (None, screen):
        scroll_to_top()
    st.session_state[SCREEN] = screen


# Seed assessments, submissions, grading results, users and demo-mode flag.
init_session_state()

# Anyone who has not signed in or chosen the demo lands on the welcome page,
# which carries the sign-in and sign-up forms. No sidebar, no other pages.
#
# BUG-006 / BUG-036: every inner page is also registered here, hidden, so a
# refresh or a bookmarked /study_camp resolves instead of raising Streamlit's
# "Page not found" modal. Those entries never render their page: they remember
# which page was asked for and send the visitor to the welcome page, and once
# they are in (demo or signed in) they are taken to it.
#
# KNOWN LIMITATION: a refresh is a new Streamlit session. Demo data lives in
# st.session_state by design, so it starts again from the samples, and the
# Supabase client (and its tokens) also lives only in the session, so a
# refresh signs a real user out. Persisting the refresh token in a cookie or
# the URL would make it readable by any script on the page, so it is not done.
# A path that matches no page at all still gets Streamlit's own modal; there
# is no catch-all route to hook.
if should_show_landing():
    _arrive_on("welcome")
    welcome = st.Page(
        os.path.join(PROJECT_ROOT, "views", "landing.py"), title="Welcome", default=True
    )

    def _remember_and_welcome(path: str):
        def _page() -> None:
            st.session_state[REQUESTED_PAGE] = path
            st.switch_page(welcome)

        return _page

    # A page marked `without_account` (Admin, opened with a passkey) renders
    # itself here instead of bouncing to the welcome page.
    deep_links = [
        st.Page(
            os.path.join(PROJECT_ROOT, spec["path"])
            if spec.get("without_account")
            else _remember_and_welcome(spec["path"]),
            title=spec["title"],
            url_path=os.path.splitext(os.path.basename(spec["path"]))[0],
        )
        for spec in PAGE_SPECS
    ]
    run_page(st.navigation([welcome, *deep_links], position="hidden"))
    st.stop()

_arrive_on("app")

# An account an admin created still has the admin's temporary password. Until its
# owner has chosen their own, that is the only page they can reach: no menu, no
# other page (ARY-002). Saving a password clears the flag and the next run opens
# the app.
from components.navigation import build_password_navigation  # noqa: E402
from services import auth_service  # noqa: E402

if auth_service.must_change_password():
    run_page(build_password_navigation())
    st.stop()

# A Streamlit text area only commits its latest draft to session state on blur.
# Hide every navigation affordance while a paper is in progress, so a click on
# another page cannot race that commit and discard the student's answer.
from services.state import get_current_user, get_mock_exam  # noqa: E402

_active_exam = get_mock_exam()
_active_user = get_current_user()
if (
    _active_exam is not None
    and not _active_exam.is_submitted
    and _active_user is not None
    and _active_user.is_student
    and _active_exam.student_id == _active_user.id
):
    run_page(build_exam_navigation())
    st.stop()

# No st.logo: the sidebar starts straight at the menu (the emblem took a
# fifth of the rail and said nothing the page banner does not).

from services.auth_service import current_user as signed_in_user  # noqa: E402
from services.supabase_client import get_connection_status  # noqa: E402

_signed_in = signed_in_user() is not None
_role = get_current_role()
navigation = build_navigation(
    _role,
    signed_in=_signed_in,
    # BUG-032: without Supabase there is nothing to sign in to.
    accounts_available=get_connection_status().connected,
)

# Identity changes trigger a rerun, which rebuilds the role-specific menu.
sidebar_status()

# Finish a deep link that had to pass through the welcome page first, as long
# as the page exists for this role.
_requested = st.session_state.pop(REQUESTED_PAGE, None)
if _requested and _requested in {spec["path"] for spec in pages_for(_role, _signed_in)}:
    st.switch_page(_requested)

run_page(navigation)
