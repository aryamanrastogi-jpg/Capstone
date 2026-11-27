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
    "views/student_home.py",
    "views/my_questions.py",
    "views/study_camp.py",
    "views/practice_generator.py",
    "views/mock_exam.py",
]

TEACHER_PAGES = [
    "views/dashboard.py",
    "views/create_assessment.py",
    "views/upload_responses.py",
    "views/review_grading.py",
    "views/analytics.py",
    "views/practice_generator.py",
]


def _app_as(role: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception

    users = at.session_state["users"]
    wanted = next(u for u in users if u.role.value == role)
    at.session_state["current_user_id"] = wanted.id
    at.session_state["entered_demo"] = True
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


def test_the_app_opens_on_the_welcome_page():
    """A visitor who has not signed in sees the landing page, not a dashboard."""
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception, at.exception
    assert "Explore the demo" in [b.label for b in at.button]


def test_exploring_the_demo_leaves_the_welcome_page():
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    next(b for b in at.button if b.label == "Explore the demo").click().run()
    assert not at.exception, at.exception
    assert at.session_state["entered_demo"] is True
    assert "Explore the demo" not in [b.label for b in at.button]


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

    assert "views/dashboard.py" not in student_paths
    assert "views/review_grading.py" not in student_paths
    assert "views/create_assessment.py" not in student_paths
    assert "views/study_camp.py" not in teacher_paths
    assert "views/student_home.py" not in teacher_paths
    # The practice generator is deliberately shared.
    assert "views/practice_generator.py" in student_paths & teacher_paths


def _page_as(page: str, role: str) -> AppTest:
    """One page script run on its own, as the sample person of the given role.

    This is a direct hit on the page, which is how the in-page guard is reached.
    These tests used to get there through `at.switch_page(page)` and a change of
    identity, which only worked because a `pages/` folder made Streamlit run page
    scripts directly (BUG-009, since closed by renaming it to `views/`). The page
    is now run by itself, with the sample people seeded, to the same effect.
    """
    from data.sample_data import build_sample_data

    users = build_sample_data()[3]
    who = next(u for u in users if u.role.value == role)
    at = AppTest.from_file(str(Path(APP).parent / page), default_timeout=90)
    at.session_state["users"] = users
    at.session_state["current_user_id"] = who.id
    at.run()
    return at


@pytest.mark.parametrize("page", ["views/dashboard.py", "views/create_assessment.py"])
def test_teacher_pages_refuse_a_student_who_reaches_them_directly(page):
    """Defence in depth: the in-page guard shows a message, not a traceback."""
    at = _page_as(page, "student")

    assert not at.exception
    assert any("teacher" in e.value.lower() for e in at.error)


@pytest.mark.parametrize("page", STUDENT_PAGES[:3])
def test_student_pages_refuse_a_teacher_who_reaches_them_directly(page):
    at = _page_as(page, "teacher")

    assert not at.exception
    assert any("student" in e.value.lower() for e in at.error)




def test_a_student_can_build_a_study_camp_from_seeded_data():
    at = _app_as("student")
    at.switch_page("views/study_camp.py")
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


# ---------------------------------------------------------------------------
# Student-authored question sets
# ---------------------------------------------------------------------------
def _add_student_set(at, owner_id, *, with_answers):
    from models import Assessment, Question

    assessment = Assessment(
        title="My worksheet",
        grade_level=9,
        topic="Algebra",
        owner_id=owner_id,
        student_created=True,
        questions=[
            Question(
                question_text="Solve 5x - 3 = 17.",
                model_answer="Add 3 to both sides to get 5x = 20, then divide by 5 "
                "to get x = 4." if with_answers else "",
                max_marks=3,
            )
        ],
    )
    at.session_state["assessments"].append(assessment)
    return assessment


def test_my_work_gives_guidance_instead_of_a_score_when_there_are_no_answers():
    """The honest branch: guide the student rather than invent a score."""
    at = _app_as("student")
    student_id = at.session_state["current_user_id"]

    # Drop the seeded assessments so the student's own set is the only option.
    at.session_state["assessments"] = []
    _add_student_set(at, student_id, with_answers=False)

    at.switch_page("views/student_home.py")
    at.run()

    assert not at.exception, at.exception
    notices = " ".join(i.value for i in at.info)
    assert "cannot score it" in notices

    body = " ".join(m.value for m in at.markdown)
    assert "How to go at it" in body, "guidance should be rendered, not a dead end"

    # And it must still not offer to mark anything.
    assert "Get my estimate" not in [b.label for b in at.button]


def test_my_work_accepts_a_student_set_that_has_answers():
    at = _app_as("student")
    student_id = at.session_state["current_user_id"]

    at.session_state["assessments"] = []
    _add_student_set(at, student_id, with_answers=True)

    at.switch_page("views/student_home.py")
    at.run()

    assert not at.exception, at.exception
    warnings = " ".join(w.value for w in at.warning)
    assert "cannot be scored yet" not in warnings


def test_my_work_points_a_student_with_nothing_at_my_questions():
    at = _app_as("student")
    at.session_state["assessments"] = []

    at.switch_page("views/student_home.py")
    at.run()

    assert not at.exception, at.exception
    labels = [b.label for b in at.button]
    assert "Add my questions" in labels, (
        "the empty state must offer a way out, not a dead end"
    )


def test_students_and_teachers_get_separate_menus():
    """Progress across the class is the teacher's view; students have none."""
    from components.navigation import pages_for
    from models import Role

    student = {spec["title"] for spec in pages_for(Role.STUDENT)}
    teacher = {spec["title"] for spec in pages_for(Role.TEACHER)}

    assert "My Progress" not in student
    assert {"My Work", "Mock Exam", "Study Camp"} <= student
    assert {"Class Overview", "Review Grading", "Class Analytics"} <= teacher
    assert not student & {"Class Overview", "Review Grading", "Class Analytics"}
    assert not teacher & {"My Work", "Mock Exam", "Study Camp"}
