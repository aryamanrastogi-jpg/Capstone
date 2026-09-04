"""Every page must open without an exception, in both roles.

A page that throws is invisible to the unit tests - they cover the services
underneath, not the Streamlit script on top. This is the cheap safety net that
catches a bad import, a renamed helper or a column that no longer exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")

STUDENT_PAGES = [
    "pages/student_home.py",
    "pages/my_progress.py",
    "pages/study_camp.py",
    "pages/practice_generator.py",
]

TEACHER_PAGES = [
    "pages/dashboard.py",
    "pages/create_assessment.py",
    "pages/upload_responses.py",
    "pages/review_grading.py",
    "pages/analytics.py",
    "pages/practice_generator.py",
]


def _app_as(role: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception

    users = at.session_state["users"]
    wanted = next(u for u in users if u.role.value == role)
    at.session_state["current_user_id"] = wanted.id
    at.run()
    assert not at.exception, at.exception
    return at


def test_the_app_starts_as_a_student():
    """Students are the primary users, so the app should land on their page."""
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception
    user = at.session_state["users"]
    current = next(
        u for u in user if u.id == at.session_state["current_user_id"]
    )
    assert current.is_student


@pytest.mark.parametrize("page", STUDENT_PAGES)
def test_student_pages_render(page):
    at = _app_as("student")
    at.switch_page(page)
    at.run()
    assert not at.exception, f"{page} raised: {at.exception}"


@pytest.mark.parametrize("page", TEACHER_PAGES)
def test_teacher_pages_render(page):
    at = _app_as("teacher")
    at.switch_page(page)
    at.run()
    assert not at.exception, f"{page} raised: {at.exception}"


def test_navigation_does_not_route_a_role_to_the_other_role_s_pages():
    """The strongest guarantee: the wrong pages are not reachable at all.

    Streamlit only registers the pages `build_navigation` was given, so a
    student has no route to the teacher pages. The role checks inside each page
    are a second line of defence for a direct URL hit, not the only one.
    """
    from components.navigation import pages_for
    from models import Role

    student_paths = {spec["path"] for spec in pages_for(Role.STUDENT)}
    teacher_paths = {spec["path"] for spec in pages_for(Role.TEACHER)}

    assert "pages/dashboard.py" not in student_paths
    assert "pages/review_grading.py" not in student_paths
    assert "pages/create_assessment.py" not in student_paths
    assert "pages/study_camp.py" not in teacher_paths
    assert "pages/student_home.py" not in teacher_paths
    # The practice generator is deliberately shared.
    assert "pages/practice_generator.py" in student_paths & teacher_paths


# review_grading is excluded: its Submission picker uses `format_func`, and
# AppTest cannot re-run a page containing one (it stores the rendered labels but
# resolves the raw value against them). The page itself is fine in a browser -
# see test_teacher_pages_render, which opens it successfully.
@pytest.mark.parametrize("page", ["pages/dashboard.py", "pages/create_assessment.py"])
def test_teacher_pages_refuse_a_student_who_reaches_them_directly(page):
    """Defence in depth: the in-page guard shows a message, not a traceback."""
    at = _app_as("teacher")
    at.switch_page(page)
    at.run()

    # Now switch identity to a student without changing page.
    student = next(u for u in at.session_state["users"] if u.role.value == "student")
    at.session_state["current_user_id"] = student.id
    at.run()

    assert not at.exception
    assert any("teacher" in e.value.lower() for e in at.error)


@pytest.mark.parametrize("page", STUDENT_PAGES[:3])
def test_student_pages_refuse_a_teacher_who_reaches_them_directly(page):
    at = _app_as("student")
    at.switch_page(page)
    at.run()

    teacher = next(u for u in at.session_state["users"] if u.role.value == "teacher")
    at.session_state["current_user_id"] = teacher.id
    at.run()

    assert not at.exception
    assert any("student" in e.value.lower() for e in at.error)


def test_seeded_student_sees_a_populated_progress_page():
    """The demo must not look broken on first launch."""
    at = _app_as("student")
    at.switch_page("pages/my_progress.py")
    at.run()

    assert not at.exception
    # An empty history would show the "nothing to chart yet" empty state.
    assert not any("nothing to chart" in i.value.lower() for i in at.info)
    assert at.metric, "the headline metrics should be present"


def test_a_student_can_build_a_study_camp_from_seeded_data():
    at = _app_as("student")
    at.switch_page("pages/study_camp.py")
    at.run()
    assert not at.exception

    start = [b for b in at.button if b.label == "Start my study camp"]
    if not start:
        # This student is above the revision threshold on every topic, which is
        # a valid state - the page says so rather than offering an empty camp.
        assert at.success or at.info
        return

    start[0].click()
    at.run()
    assert not at.exception
    camps = at.session_state["study_camps"]
    assert len(camps) == 1
    assert camps[0].sessions
