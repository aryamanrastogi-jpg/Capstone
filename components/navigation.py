"""Navigation definition.

Uses Streamlit's current multipage API (`st.Page` + `st.navigation`). Because
`st.navigation` is called from app.py, Streamlit's automatic `pages/` directory
discovery is bypassed and this file is the single source of truth for the menu.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from models import Role

STUDENT = Role.STUDENT
TEACHER = Role.TEACHER

# `roles` controls who sees each page. `default` is per role: the first page
# listed for a role that has default=True becomes its landing page.
PAGE_SPECS: List[Dict[str, Any]] = [
    # --- Student ---------------------------------------------------------
    {
        "path": "pages/student_home.py",
        "title": "My Work",
        "icon": ":material/home:",
        "section": "My study",
        "roles": [STUDENT],
        "default": True,
    },
    {
        "path": "pages/my_progress.py",
        "title": "My Progress",
        "icon": ":material/trending_up:",
        "section": "My study",
        "roles": [STUDENT],
        "default": False,
    },
    {
        "path": "pages/study_camp.py",
        "title": "Study Camp",
        "icon": ":material/local_fire_department:",
        "section": "My study",
        "roles": [STUDENT],
        "default": False,
    },
    # --- Teacher ---------------------------------------------------------
    {
        "path": "pages/dashboard.py",
        "title": "Class Overview",
        "icon": ":material/dashboard:",
        "section": "Overview",
        "roles": [TEACHER],
        "default": True,
    },
    {
        "path": "pages/create_assessment.py",
        "title": "Create Assessment",
        "icon": ":material/note_add:",
        "section": "Assessment workflow",
        "roles": [TEACHER],
        "default": False,
    },
    {
        "path": "pages/upload_responses.py",
        "title": "Upload Responses",
        "icon": ":material/upload_file:",
        "section": "Assessment workflow",
        "roles": [TEACHER],
        "default": False,
    },
    {
        "path": "pages/review_grading.py",
        "title": "Review Grading",
        "icon": ":material/fact_check:",
        "section": "Assessment workflow",
        "roles": [TEACHER],
        "default": False,
    },
    {
        "path": "pages/analytics.py",
        "title": "Class Analytics",
        "icon": ":material/insights:",
        "section": "Insight",
        "roles": [TEACHER],
        "default": False,
    },
    # --- Both ------------------------------------------------------------
    {
        "path": "pages/practice_generator.py",
        "title": "Practice Generator",
        "icon": ":material/auto_awesome:",
        "section": "Insight",
        "roles": [STUDENT, TEACHER],
        "default": False,
    },
]


def pages_for(role: Role) -> List[Dict[str, Any]]:
    return [spec for spec in PAGE_SPECS if role in spec["roles"]]


def build_navigation(role: Role):
    """Build the grouped navigation object for the signed-in role."""
    sections: Dict[str, List] = {}
    for spec in pages_for(role):
        page = st.Page(
            spec["path"],
            title=spec["title"],
            icon=spec["icon"],
            default=spec["default"],
        )
        sections.setdefault(spec["section"], []).append(page)
    return st.navigation(sections)


def goto(title: str) -> None:
    """Switch to a page by its title - used by call-to-action buttons."""
    match = next((spec for spec in PAGE_SPECS if spec["title"] == title), None)
    if match is None:
        st.warning(f"Unknown page '{title}'.")
        return
    st.switch_page(match["path"])
