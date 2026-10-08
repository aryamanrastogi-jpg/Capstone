"""Page-level state bugs that only show up when the Streamlit script runs.

Each test drives the real page with AppTest in demo mode:
  * "Clear form" must reset the draft without a StreamlitAPIException.
  * Mock exam answers must survive the student visiting another page.
  * Students' self-study work stays out of the teacher's review queue.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _app_as(role: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    users = at.session_state["users"]
    wanted = next(u for u in users if u.role.value == role)
    at.session_state["current_user_id"] = wanted.id
    at.session_state["entered_demo"] = True
    at.run()
    assert not at.exception, at.exception
    return at


def _button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


@pytest.mark.parametrize(
    "role, page, title_key",
    [
        ("teacher", "pages/create_assessment.py", "ca_title"),
        ("student", "pages/my_questions.py", "mq_title"),
    ],
)
def test_clear_form_resets_the_draft_without_an_exception(role, page, title_key):
    at = _app_as(role)
    at.switch_page(page)
    at.run()
    at.text_input(key=title_key).set_value("QA draft").run()
    assert at.text_input(key=title_key).value == "QA draft"

    _button(at, "Clear form").click().run()

    assert not at.exception, at.exception
    assert at.text_input(key=title_key).value == ""


def test_mock_exam_answers_survive_leaving_the_page():
    at = _app_as("student")
    at.switch_page("pages/mock_exam.py")
    at.run()
    _button(at, "Start the mock exam").click().run()
    assert not at.exception, at.exception

    at.text_area[0].input("2 + 3 = 5 parts, so 18 and 27").run()

    at.switch_page("pages/study_camp.py")
    at.run()
    at.switch_page("pages/mock_exam.py")
    at.run()
    assert not at.exception, at.exception
    assert at.text_area[0].value == "2 + 3 = 5 parts, so 18 and 27"

    _button(at, "Submit my answers").click().run()
    exam = at.session_state["mock_exam"]
    first_id = exam.items[0].question.id
    assert exam.answers[first_id] == "2 + 3 = 5 parts, so 18 and 27"


def test_active_exam_navigation_registers_only_the_hidden_exam_page(monkeypatch):
    from components import navigation

    pages = []
    options = {}

    class Page:
        def __init__(self, path, **kwargs):
            self.path = path
            self.kwargs = kwargs

    class Nav:
        def run(self):
            pass

    def fake_navigation(registered, **kwargs):
        pages.extend(registered)
        options.update(kwargs)
        return Nav()

    monkeypatch.setattr(navigation.st, "Page", Page)
    monkeypatch.setattr(navigation.st, "navigation", fake_navigation)

    navigation.build_exam_navigation()

    assert [page.path for page in pages] == ["pages/mock_exam.py"]
    assert options == {"position": "hidden"}


def _awaiting_review(at: AppTest) -> int:
    return int(next(m for m in at.metric if m.label == "Submissions awaiting review").value)


def _queue_size(at: AppTest) -> int:
    at.switch_page("pages/review_grading.py")
    at.run()
    assert not at.exception, at.exception
    return len(next(s for s in at.selectbox if s.label == "Submission").options)


def test_self_study_work_stays_out_of_the_teacher_review_queue():
    at = _app_as("teacher")
    before = _awaiting_review(at)
    queue_before = _queue_size(at)
    at.switch_page("pages/dashboard.py")
    at.run()

    # Turn one pending, teacher-collected submission into a student's self-study.
    submissions = at.session_state["submissions"]
    results = at.session_state["grading_results"]
    pending = {r.submission_id for r in results if not r.is_reviewed}
    index = next(i for i, s in enumerate(submissions) if s.id in pending)
    submissions[index] = submissions[index].model_copy(update={"is_self_study": True})
    at.session_state["submissions"] = submissions
    at.run()

    assert not at.exception, at.exception
    assert _awaiting_review(at) == before - 1
    assert _queue_size(at) == queue_before - 1
