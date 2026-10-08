"""Regression coverage for the remaining round-three UI fixes."""

from __future__ import annotations

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from components.navigation import PAGE_SPECS, pages_for
from models import ReviewStatus, Role
from services import analytics_service
from services import state
from utils.config import PRIVACY_DETAILS
from utils.validation import validate_assessment_draft

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _app_as(role: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90).run()
    user = next(u for u in at.session_state["users"] if u.role.value == role)
    at.session_state["current_user_id"] = user.id
    at.session_state["entered_demo"] = True
    at.run()
    assert not at.exception, at.exception
    return at


def test_student_draft_error_only_requires_text_and_marks_without_model_answers():
    result = validate_assessment_draft(
        title="", topic="Algebra", curriculum="CBSE", questions=[],
        require_model_answers=False, title_label="Question set name",
    )

    assert not result.ok
    message = " ".join(result.errors)
    assert "Question set name is required" in message
    assert "question text and marks" in message
    assert "model answer" not in message


def test_teacher_empty_draft_still_explains_that_model_answers_are_required():
    result = validate_assessment_draft(
        title="T", topic="Algebra", curriculum="CBSE", questions=[]
    )
    assert "model answer" in " ".join(result.errors)


def test_landing_heading_levels_follow_the_page_title():
    source = (Path(__file__).resolve().parent.parent / "pages" / "landing.py").read_text(
        encoding="utf-8"
    )
    assert "<h1 class=\"campprep-hero-title\"" in source
    assert "<h2>Add your work</h2>" in source
    assert "<h2>See what slipped</h2>" in source
    assert "<h2>Fix it in camp</h2>" in source
    assert "<h5>" not in source


def test_sidebar_theme_copy_meets_contrast_and_size_requirements():
    source = (Path(__file__).resolve().parent.parent / "components" / "layout.py").read_text(
        encoding="utf-8"
    )
    foreground, background = "#E9ECFF", "#141E8C"

    def luminance(colour: str) -> float:
        rgb = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
        return sum(c * v for c, v in zip((0.2126, 0.7152, 0.0722), linear))

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    assert (light + 0.05) / (dark + 0.05) >= 4.5
    assert "font-size: max(12px, 0.8rem) !important" in source
    assert "[data-testid=\"stSidebar\"] a[aria-current=\"page\"]" in source


def test_privacy_page_is_registered_for_signed_out_and_signed_in_visitors():
    path = "pages/privacy.py"
    assert any(spec["path"] == path for spec in PAGE_SPECS)
    for signed_in in (False, True):
        assert path in {spec["path"] for spec in pages_for(Role.STUDENT, signed_in)}
        assert path in {spec["path"] for spec in pages_for(Role.TEACHER, signed_in)}


def test_privacy_page_renders_the_read_only_configured_details():
    at = _app_as("student")
    at.switch_page("pages/privacy.py").run()
    assert not at.exception, at.exception
    rendered = " ".join(item.value for item in at.markdown)
    for line in PRIVACY_DETAILS:
        assert line.strip("*")[:24] in rendered


def test_study_camp_copy_describes_its_template_questions_without_ai_claims():
    at = _app_as("student")
    at.switch_page("pages/study_camp.py").run()
    assert not at.exception, at.exception
    captions = " ".join(c.value for c in at.caption)
    assert "built-in practice templates" in captions
    assert "does not send your work to Gemini" in captions


def test_demo_reset_clears_exam_and_teacher_class_codes(monkeypatch: pytest.MonkeyPatch):
    fake = {}
    monkeypatch.setattr(st, "session_state", fake)
    state.init_session_state()
    teacher = next(u for u in state.get_users() if u.is_teacher)
    fake["current_user_id"] = teacher.id
    fake["mock_exam"] = object()
    fake["class_codes"] = {teacher.id: "demo-code"}
    state.reset_to_samples()
    assert fake["current_user_id"] == teacher.id
    assert "mock_exam" not in fake
    assert "class_codes" not in fake


def test_review_edits_remain_in_keyed_widgets_after_accept_or_flag():
    for action in ("Accept as-is", "Flag for review"):
        at = _app_as("teacher")
        at.switch_page("pages/review_grading.py").run()
        assert not at.exception, at.exception

        score_widget = next(w for w in at.number_input if w.label == "Score to award")
        feedback_widget = next(
            w for w in at.text_area if w.label == "Feedback the student will see"
        )
        score_key, feedback_key = score_widget.key, feedback_widget.key
        score_widget.set_value(0.5).run()
        feedback_widget = next(
            w for w in at.text_area if w.label == "Feedback the student will see"
        )
        feedback_widget.set_value("Retain this draft").run()

        action_button = next(b for b in at.button if b.label == action)
        action_button.click().run()

        assert at.session_state[score_key] == 0.5
        assert at.session_state[feedback_key] == "Retain this draft"


def test_orphaned_review_result_is_visible_as_read_only():
    at = _app_as("teacher")
    assessments = at.session_state["assessments"]
    at.session_state["assessments"] = [
        assessment.model_copy(update={"questions": []}) for assessment in assessments
    ]

    at.switch_page("pages/review_grading.py").run()
    assert not at.exception, at.exception
    assert any("saved result is shown below read-only" in w.value for w in at.warning)
    assert any("Removed question · read-only result" in m.value for m in at.markdown)
    assert any(m.label == "Suggested score" for m in at.metric)


def test_retry_result_keeps_its_original_question_number():
    at = _app_as("teacher")
    assessments = at.session_state["assessments"]
    submissions = at.session_state["submissions"]
    results = at.session_state["grading_results"]
    submissions_by_id = {submission.id: submission for submission in submissions}
    candidate = next(
        (assessment, question, result, submissions_by_id[result.submission_id])
        for assessment in assessments
        for question in assessment.questions[1:]
        for result in results
        if result.question_id == question.id
        and result.submission_id in submissions_by_id
        and submissions_by_id[result.submission_id].assessment_id == assessment.id
        and not result.is_finalised
    )
    assessment, question, result, submission = candidate
    at.session_state["assessments"] = [assessment]
    at.session_state["submissions"] = [submission]
    at.session_state["grading_results"] = [result]

    at.switch_page("pages/review_grading.py").run()
    assert not at.exception, at.exception
    assert any("Question 2 ·" in item.value for item in at.markdown)


def test_progress_error_chart_excludes_flagged_items(monkeypatch):
    at = _app_as("student")
    student_id = at.session_state["current_user_id"]
    submissions = {s.id: s for s in at.session_state["submissions"]}
    own_result = next(
        result for result in at.session_state["grading_results"]
        if result.submission_id in submissions
        and submissions[result.submission_id].student_id == student_id
    )
    flagged = own_result.model_copy(update={"review_status": ReviewStatus.FLAGGED})
    at.session_state["grading_results"] = [*at.session_state["grading_results"], flagged]

    chart_inputs = []
    original = analytics_service.error_frequency

    def record_inputs(results, *args, **kwargs):
        materialized = list(results)
        chart_inputs.extend(materialized)
        return original(materialized, *args, **kwargs)

    monkeypatch.setattr(analytics_service, "error_frequency", record_inputs)
    at.switch_page("pages/my_progress.py").run()

    assert not at.exception, at.exception
    assert flagged not in chart_inputs
    assert chart_inputs


def test_mock_exam_navigation_remains_hidden_when_registered():
    from components import navigation

    registered, options = [], {}

    class Page:
        def __init__(self, path, **kwargs):
            self.path = path
            self.kwargs = kwargs

    class Nav:
        def run(self):
            return None

    old_page, old_navigation = navigation.st.Page, navigation.st.navigation
    try:
        navigation.st.Page = Page
        navigation.st.navigation = lambda pages, **kwargs: (
            registered.extend(pages), options.update(kwargs), Nav()
        )[-1]
        navigation.build_exam_navigation()
    finally:
        navigation.st.Page, navigation.st.navigation = old_page, old_navigation

    assert [page.path for page in registered] == ["pages/mock_exam.py"]
    assert options == {"position": "hidden"}


def test_active_mock_exam_keeps_hidden_navigation_error_free():
    at = _app_as("student")
    at.switch_page("pages/mock_exam.py").run()
    start = next(b for b in at.button if b.label == "Start the mock exam")
    start.click().run()
    assert not at.exception, at.exception
    assert "mock_exam" in at.session_state and not at.session_state["mock_exam"].is_submitted
