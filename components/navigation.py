"""Navigation definition.

Uses Streamlit's current multipage API (`st.Page` + `st.navigation`). Because
`st.navigation` is called from app.py, this file is the single source of truth for
the menu. The page scripts live in `views/`, deliberately not `pages/`: with a
folder named `pages/` beside app.py, Streamlit runs those files directly after
every server start (until somebody opens "/"), which listed every file, Admin
included, in a raw menu with dead-end errors (BUG-009).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from models import Role
from utils.config import APP_NAME

STUDENT = Role.STUDENT
TEACHER = Role.TEACHER

# Session key holding the page a visitor asked for before they were signed in
# or in the demo (BUG-006). app.py sets it on the welcome page and honours it
# once they are in.
REQUESTED_PAGE = "_requested_page"

# `roles` controls who sees each page. `default` is per role: the first page
# listed for a role that has default=True becomes its landing page.
PAGE_SPECS: List[Dict[str, Any]] = [
    # --- Student ---------------------------------------------------------
    {
        "path": "views/student_home.py",
        "title": "My Work",
        "icon": ":material/home:",
        "section": "My study",
        "roles": [STUDENT],
        "default": True,
    },
    {
        "path": "views/my_questions.py",
        "title": "My Questions",
        "icon": ":material/edit_note:",
        "section": "My study",
        "roles": [STUDENT],
        "default": False,
    },
    {
        "path": "views/study_camp.py",
        "title": "Study Camp",
        "icon": ":material/local_fire_department:",
        "section": "My study",
        "roles": [STUDENT],
        "default": False,
    },
    {
        "path": "views/mock_exam.py",
        "title": "Mock Exam",
        "icon": ":material/timer:",
        "section": "My study",
        "roles": [STUDENT],
        "default": False,
    },
    # --- Teacher ---------------------------------------------------------
    {
        "path": "views/dashboard.py",
        "title": "Class Overview",
        "icon": ":material/dashboard:",
        "section": "Overview",
        "roles": [TEACHER],
        "default": True,
    },
    {
        "path": "views/create_assessment.py",
        "title": "Create Assessment",
        "icon": ":material/note_add:",
        "section": "Assessment workflow",
        "roles": [TEACHER],
        "default": False,
    },
    {
        "path": "views/upload_responses.py",
        "title": "Upload Responses",
        "icon": ":material/upload_file:",
        "section": "Assessment workflow",
        "roles": [TEACHER],
        "default": False,
    },
    {
        "path": "views/review_grading.py",
        "title": "Review Grading",
        "icon": ":material/fact_check:",
        "section": "Assessment workflow",
        "roles": [TEACHER],
        "default": False,
    },
    {
        "path": "views/analytics.py",
        "title": "Class Analytics",
        "icon": ":material/insights:",
        "section": "Insight",
        "roles": [TEACHER],
        "default": False,
    },
    # --- Both ------------------------------------------------------------
    {
        "path": "views/practice_generator.py",
        "title": "Practice Generator",
        # A plain question-paper icon: the sparkle is the "AI product" cliche.
        "icon": ":material/quiz:",
        "section": "Insight",
        "roles": [STUDENT, TEACHER],
        "default": False,
    },
    {
        "path": "views/my_class.py",
        "title": "My Class",
        "icon": ":material/groups:",
        "section": "Account",
        "roles": [STUDENT, TEACHER],
        "default": False,
    },
    # Listed last and in its own section: signing in is not part of either
    # journey, it is how you leave the sample data behind.
    {
        "path": "views/profile.py",
        "title": "Profile",
        "icon": ":material/account_circle:",
        "section": "Account",
        "roles": [STUDENT, TEACHER],
        "default": False,
        "signed_in": True,
    },
    {
        "path": "views/sign_in.py",
        "title": "Sign In",
        "icon": ":material/login:",
        "section": "Account",
        "roles": [STUDENT, TEACHER],
        "default": False,
        "signed_in": False,
    },
    # Opened with the ADMIN_PASSKEY secret, not an account (services/
    # admin_service.py), so it is registered for everybody but never listed in
    # the menu: it is reached at /admin or from the link on the sign-in form.
    # `without_account` lets it open from the welcome screen too.
    {
        "path": "views/admin.py",
        "title": "Admin",
        "icon": ":material/admin_panel_settings:",
        "section": "Account",
        "roles": [STUDENT, TEACHER],
        "default": False,
        "hidden": True,
        "without_account": True,
    },
    {
        "path": "views/schools.py",
        "title": "Schools",
        "icon": ":material/school:",
        "section": "Account",
        "roles": [STUDENT, TEACHER],
        "default": False,
        # Public like Privacy: names of schools with a teacher on the app, at
        # /schools, linked from the welcome footer.
        "without_account": True,
    },
    {
        "path": "views/privacy.py",
        "title": "Privacy",
        "icon": ":material/lock:",
        # The sidebar's only route to the privacy details.
        "section": "Account",
        "roles": [STUDENT, TEACHER],
        "default": False,
        # A parent or a school reads this before anyone makes an account, so it
        # opens from the welcome screen too, at /privacy (BUG-017).
        "without_account": True,
    },
]


def pages_for(
    role: Role, signed_in: Optional[bool] = None, accounts_available: bool = True
) -> List[Dict[str, Any]]:
    """Pages for a role. With `signed_in` given, pages marked for the other
    state are left out: Profile only when signed in, Sign In only when not.
    With `accounts_available=False` (no Supabase) Sign In is left out too, since
    it could only say that accounts are unavailable (BUG-032)."""
    return [
        spec
        for spec in PAGE_SPECS
        if role in spec["roles"]
        and (signed_in is None or spec.get("signed_in", signed_in) == signed_in)
        and (accounts_available or spec["path"] != "views/sign_in.py")
    ]


def build_navigation(
    role: Role, signed_in: bool = False, accounts_available: bool = True
):
    """Build the grouped navigation object for the signed-in role."""
    sections: Dict[str, List] = {}
    for spec in pages_for(role, signed_in, accounts_available):
        page = st.Page(
            spec["path"],
            title=spec["title"],
            icon=spec["icon"],
            default=spec["default"],
            visibility="hidden" if spec.get("hidden") else "visible",
        )
        sections.setdefault(spec["section"], []).append(page)
    return st.navigation(sections)


def build_exam_navigation():
    """Keep the active timed paper as the only reachable app page."""
    page = st.Page(
        "views/mock_exam.py",
        title="Mock Exam",
        icon=":material/timer:",
        default=True,
    )
    return st.navigation([page], position="hidden")


def tab_title(page_title: str) -> str:
    """The browser tab and bookmark title: the app's name, after the page's own
    (BUG-021). The welcome page is just the app's name."""
    return APP_NAME if page_title == "Welcome" else f"{page_title} · {APP_NAME}"


def run_page(page) -> None:
    """Name the browser tab after the page, then run the page.

    `st.set_page_config` can be called again on every run in this version of
    Streamlit, and once a page title is set Streamlit stops deriving one from
    the page, so each run sets it afresh for the page it is about to show.
    """
    st.set_page_config(page_title=tab_title(page.title))
    page.run()


def build_password_navigation():
    """The only page an account can reach until it has chosen its own password.

    Used by app.py for an account an admin created (see
    services/auth_service.must_change_password). Hidden, so no menu offers a way
    round it, and not in PAGE_SPECS, so it is not a deep link either.
    """
    page = st.Page(
        "views/change_password.py",
        title="Choose your password",
        icon=":material/lock_reset:",
        default=True,
    )
    return st.navigation([page], position="hidden")


def goto(title: str) -> None:
    """Switch to a page by its title - used by call-to-action buttons."""
    match = next((spec for spec in PAGE_SPECS if spec["title"] == title), None)
    if match is None:
        st.warning(f"Unknown page '{title}'.")
        return
    st.switch_page(match["path"])
