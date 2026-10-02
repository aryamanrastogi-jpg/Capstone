"""CampPrep AI - teacher-facing AI-assisted assessment platform.

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
from components.navigation import (  # noqa: E402
    PAGE_SPECS,
    REQUESTED_PAGE,
    build_navigation,
    pages_for,
)
from services.state import (  # noqa: E402
    get_current_role,
    init_session_state,
    should_show_landing,
)
from utils.config import APP_NAME, APP_TAGLINE  # noqa: E402

st.set_page_config(
    # No page_title: each st.Page's own title names the browser tab (BUG-031).
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
    welcome = st.Page(
        os.path.join(PROJECT_ROOT, "pages", "landing.py"), title="Welcome", default=True
    )

    def _remember_and_welcome(path: str):
        def _page() -> None:
            st.session_state[REQUESTED_PAGE] = path
            st.switch_page(welcome)

        return _page

    deep_links = [
        st.Page(
            _remember_and_welcome(spec["path"]),
            title=spec["title"],
            url_path=os.path.splitext(os.path.basename(spec["path"]))[0],
        )
        for spec in PAGE_SPECS
    ]
    st.navigation([welcome, *deep_links], position="hidden").run()
    st.stop()

# The sidebar owns the demo role switch, so it must run before navigation is
# built - switching role changes which pages exist.
sidebar_status()

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

# Finish a deep link that had to pass through the welcome page first, as long
# as the page exists for this role.
_requested = st.session_state.pop(REQUESTED_PAGE, None)
if _requested and _requested in {spec["path"] for spec in pages_for(_role, _signed_in)}:
    st.switch_page(_requested)

navigation.run()
