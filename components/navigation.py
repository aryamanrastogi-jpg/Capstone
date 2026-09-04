"""Navigation definition.

Uses Streamlit's current multipage API (`st.Page` + `st.navigation`). Because
`st.navigation` is called from app.py, Streamlit's automatic `pages/` directory
discovery is bypassed and this file is the single source of truth for the menu.
"""

from __future__ import annotations

from typing import Dict, List

import streamlit as st

PAGE_SPECS = [
    {
        "path": "pages/dashboard.py",
        "title": "Dashboard",
        "icon": ":material/dashboard:",
        "section": "Overview",
        "default": True,
    },
    {
        "path": "pages/create_assessment.py",
        "title": "Create Assessment",
        "icon": ":material/note_add:",
        "section": "Assessment workflow",
        "default": False,
    },
    {
        "path": "pages/upload_responses.py",
        "title": "Upload Responses",
        "icon": ":material/upload_file:",
        "section": "Assessment workflow",
        "default": False,
    },
    {
        "path": "pages/review_grading.py",
        "title": "Review Grading",
        "icon": ":material/fact_check:",
        "section": "Assessment workflow",
        "default": False,
    },
    {
        "path": "pages/analytics.py",
        "title": "Analytics",
        "icon": ":material/insights:",
        "section": "Insight",
        "default": False,
    },
    {
        "path": "pages/practice_generator.py",
        "title": "Practice Generator",
        "icon": ":material/auto_awesome:",
        "section": "Insight",
        "default": False,
    },
]


def build_navigation():
    """Build the grouped navigation object for app.py."""
    sections: Dict[str, List] = {}
    for spec in PAGE_SPECS:
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
