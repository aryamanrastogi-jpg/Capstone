"""Fixes from the 26 Nov 2026 bug hunt: BUG-009, BUG-015, BUG-017 to BUG-021.

(ARY-002, ARY-004/006/007 and BUG-008/011/012/014/016 have their own files:
test_password_change.py, test_welcome_page_styles.py, test_admin.py.)

Each section says which bug it guards. Layout and scroll problems that a unit
test cannot see (the chart on a phone, the tab title in a real browser, the
heading outline in the real DOM) were measured in a browser as well; these are
the guards that keep them from coming back.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

import pytest
from streamlit.testing.v1 import AppTest

from components import charts
from components.navigation import PAGE_SPECS

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")


def _demo(role: str, page: str | None = None) -> AppTest:
    """The app in the demo, as the sample student or teacher, optionally on a page."""
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    user = next(u for u in at.session_state["users"] if u.role.value == role)
    at.session_state["current_user_id"] = user.id
    at.session_state["entered_demo"] = True
    at.run()
    if page:
        at.switch_page(page).run()
    assert not at.exception, at.exception
    return at


def _walk(block):
    for _, child in sorted(block.children.items()):
        yield child
        if isinstance(getattr(child, "children", None), dict):
            yield from _walk(child)


def heading_levels(at: AppTest) -> List[int]:
    """The heading levels on the page, in reading order."""
    levels: List[int] = []
    for element in _walk(at.main):
        kind = getattr(element, "type", "")
        if kind == "title":
            levels.append(1)
        elif kind == "header":
            levels.append(2)
        elif kind == "subheader":
            levels.append(3)
        elif kind == "markdown":
            text = str(element.value)
            hashes = re.match(r"(#{1,6}) ", text)
            if hashes:
                levels.append(len(hashes.group(1)))
            levels.extend(int(n) for n in re.findall(r"<h([1-6])[ >]", text))
        elif kind == "html":
            levels.extend(int(n) for n in re.findall(r"<h([1-6])[ >]", element.proto.body))
    return levels


# --------------------------------------------------------------------------
# BUG-009: no `pages/` folder next to app.py
# --------------------------------------------------------------------------
def test_there_is_no_pages_folder_for_streamlit_to_find() -> None:
    """With a `pages/` folder beside app.py, Streamlit runs those files directly
    after every server start, until somebody opens "/": a raw menu of all 17 files
    (Admin included) and dead-end errors. The page scripts live in `views/`."""
    assert not (ROOT / "pages").exists()


def test_every_menu_entry_points_at_a_real_file() -> None:
    for spec in PAGE_SPECS:
        assert (ROOT / spec["path"]).is_file(), spec["path"]


def test_the_page_scripts_live_in_views() -> None:
    assert all(spec["path"].startswith("views/") for spec in PAGE_SPECS)


# --------------------------------------------------------------------------
# BUG-015: Class Analytics > Most difficult questions on a phone
# --------------------------------------------------------------------------
LONG_QUESTIONS = [
    "Solve the simultaneous equations 2x + y = 7 and x - y = 2",
    "Solve the simultaneous equations 2x + y = 7 and x - y = 5",
    "Find x",
    "  Find   x  ",
]


def test_short_labels_fit_a_phone_and_stay_distinct() -> None:
    labels = charts.short_labels(LONG_QUESTIONS)
    assert all(len(label) <= 26 + len(" (9)") for label in labels), labels
    assert len(set(labels)) == len(labels), "Plotly merges bars that share a label"
    assert labels[0].endswith("…") and "  " not in "".join(labels)
    assert labels[2] == "Find x"


def test_short_labels_cut_at_a_word() -> None:
    [label] = charts.short_labels(["Calculate the area of the shaded region"], limit=20)
    assert label == "Calculate the area…"


def test_the_hover_text_keeps_the_whole_question() -> None:
    text = "Solve the simultaneous equations 2x + y = 7 and x - y = 2 and say how you checked"
    wrapped = charts.wrap_for_hover(text)
    assert "<br>" in wrapped
    assert wrapped.replace("<br>", " ") == text


def test_the_hardest_questions_chart_has_short_labels_and_the_full_text_on_hover() -> None:
    at = _demo("teacher", "views/analytics.py")
    figures = [json.loads(chart.proto.spec) for chart in at.get("plotly_chart")]
    [hardest] = [
        f for f in figures if f["layout"].get("xaxis", {}).get("title", {}).get("text") == "Average score (%)"
    ]
    trace = hardest["data"][0]
    assert trace["y"] and all(len(label) <= 30 for label in trace["y"]), trace["y"]
    for label, hover in zip(trace["y"], trace["hovertext"]):
        assert hover.replace("<br>", " ").startswith(label.rstrip("…").rstrip())


# --------------------------------------------------------------------------
# BUG-017: /privacy opens before anyone has an account
# --------------------------------------------------------------------------
def test_privacy_opens_without_an_account() -> None:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    at.switch_page("views/privacy.py").run()
    assert not at.exception, at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "What we store" in text
    assert "Explore the demo" not in [b.label for b in at.button]


def test_the_welcome_footer_links_to_the_privacy_page() -> None:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    footer = [e.proto.body for e in at.get("html") if "cp-footer" in e.proto.body]
    assert footer and 'href="privacy"' in footer[0]


# --------------------------------------------------------------------------
# BUG-018: the mock exam names the marker that made the scores
# --------------------------------------------------------------------------
def _marked_exam(monkeypatch: pytest.MonkeyPatch, by_ai: bool, student_id: str = "s1"):
    import dataclasses
    from datetime import datetime

    import pandas as pd

    from models import Assessment, Question
    from services import ai_grading_service
    from services import mock_exam_service as exams

    question = Question(
        question_text="Find the area of a 3 by 4 rectangle",
        model_answer="12 square units.",
        max_marks=2,
    )
    paper = Assessment(title="Area", grade_level=9, topic="Area", questions=[question])
    frame = pd.DataFrame({"topic": ["Area"], "percentage": [50.0]})
    exam = exams.build_exam(student_id, [paper], ["Area"], frame, 1, now=datetime(2026, 9, 1, 10))
    if by_ai:
        real = ai_grading_service.grade_with_ai

        def fake_ai(q, answer, submission_id, *args, **kwargs):
            outcome = real(q, answer, submission_id, *args, **kwargs)
            return dataclasses.replace(
                outcome, path=ai_grading_service.PATH_AI, fallback_reason=None
            )

        monkeypatch.setattr(ai_grading_service, "grade_with_ai", fake_ai)
    answers = {exam.items[0].question.id: "12 square units."}
    return exams.submit_exam(exam, answers, now=datetime(2026, 9, 1, 10, 2))


def test_a_paper_marked_by_the_built_in_checker_is_not_called_an_ai_paper(monkeypatch) -> None:
    assert _marked_exam(monkeypatch, by_ai=False).ai_marked is False


def test_a_paper_the_ai_marked_is_recorded_as_such(monkeypatch) -> None:
    assert _marked_exam(monkeypatch, by_ai=True).ai_marked is True


@pytest.mark.parametrize("by_ai, said, not_said", [
    (False, "built-in checker", "AI estimate"),
    (True, "AI estimates", "built-in checker"),
])
def test_the_result_page_says_who_marked_it(monkeypatch, by_ai, said, not_said) -> None:
    at = _demo("student")
    exam = _marked_exam(monkeypatch, by_ai=by_ai, student_id=at.session_state["current_user_id"])
    at.session_state["mock_exam"] = exam
    at.switch_page("views/mock_exam.py").run()
    assert not at.exception, at.exception
    info = " ".join(i.value for i in at.info)
    assert said in info and not_said not in info
    helps = " ".join(str(getattr(m, "help", "")) for m in at.metric)
    assert ("AI estimate" in helps) == by_ai


# --------------------------------------------------------------------------
# BUG-019: stale or inconsistent copy
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", sorted((ROOT / "views").glob("*.py")))
def test_no_page_writes_a_plural_as_word_s(path: Path) -> None:
    assert not re.search(r"[a-z]\(s\)", path.read_text(encoding="utf-8")), path.name


def test_one_blank_question_is_grammatical() -> None:
    from datetime import datetime

    import pandas as pd

    from models import Assessment, Question
    from services import mock_exam_service as exams

    at = _demo("student")
    question = Question(question_text="Find the area", model_answer="12 square units.", max_marks=2)
    paper = Assessment(title="Area", grade_level=9, topic="Area", questions=[question])
    frame = pd.DataFrame({"topic": ["Area"], "percentage": [50.0]})
    exam = exams.build_exam(
        at.session_state["current_user_id"], [paper], ["Area"], frame, 1, now=datetime.now()
    )
    at.session_state["mock_exam"] = exam
    at.switch_page("views/mock_exam.py").run()
    next(b for b in at.button if b.label == "Submit my answers").click().run()
    warning = " ".join(w.value for w in at.warning)
    assert "1 of 1 question is blank" in warning


def test_the_dashboard_counts_flagged_results_in_grammar() -> None:
    at = _demo("teacher", "views/dashboard.py")
    text = " ".join(w.value for w in at.warning)
    match = re.search(r"(\d+) flagged (result still needs|results still need) a decision\.", text)
    assert match, text
    assert (match.group(2) == "result still needs") == (match.group(1) == "1")


def test_a_demo_page_does_not_say_somebody_is_signed_in() -> None:
    at = _demo("student", "views/student_home.py")
    banner = " ".join(m.value for m in at.markdown if "campprep-header" in str(m.value))
    assert "Viewing as" in banner and "Signed in as" not in banner


def test_a_real_account_is_told_it_is_signed_in(monkeypatch) -> None:
    from data.sample_data import build_sample_data
    from services import auth_service
    from services import state as store

    student = next(u for u in build_sample_data()[3] if u.is_student)
    monkeypatch.setattr(auth_service, "current_user", lambda: student)
    assert store.identity_line(student) == f"Signed in as {student.display_name}"
    monkeypatch.setattr(auth_service, "current_user", lambda: None)
    assert store.identity_line(student) == f"Viewing as {student.display_name}"


def test_the_welcome_teacher_card_mentions_that_an_admin_can_create_the_account() -> None:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    html = " ".join(e.proto.body for e in at.get("html"))
    assert "Your admin can create your teacher account" in html


def test_profile_help_says_teacher_access_comes_from_an_admin(monkeypatch) -> None:
    from models import Role, User
    from services import auth_service

    teacher = User(id="usr_t99", display_name="Ms Rao", role=Role.TEACHER)
    monkeypatch.setattr(auth_service, "current_user", lambda: teacher)
    monkeypatch.setattr(auth_service, "current_email", lambda: "rao@school.org")
    at = AppTest.from_file(str(ROOT / "views" / "profile.py"), default_timeout=60).run()
    role_help = next(t.help for t in at.text_input if t.label == "Role")
    assert "admin" in role_help and "from an invite code." not in role_help


# --------------------------------------------------------------------------
# BUG-020: headings never skip a level
# --------------------------------------------------------------------------
STUDENT_PAGES = [
    "views/student_home.py", "views/my_questions.py", "views/study_camp.py",
    "views/mock_exam.py", "views/practice_generator.py", "views/my_class.py",
    "views/privacy.py",
]
TEACHER_PAGES = [
    "views/dashboard.py", "views/create_assessment.py", "views/upload_responses.py",
    "views/review_grading.py", "views/analytics.py", "views/practice_generator.py",
    "views/my_class.py", "views/privacy.py",
]


def _assert_outline(levels: List[int]) -> None:
    assert levels and levels[0] == 1, levels
    assert levels.count(1) == 1, f"one h1 per page: {levels}"
    for before, after in zip(levels, levels[1:]):
        assert after <= before + 1, f"a heading jumps from h{before} to h{after}: {levels}"


@pytest.mark.parametrize("page", STUDENT_PAGES)
def test_student_page_headings_do_not_skip_a_level(page: str) -> None:
    _assert_outline(heading_levels(_demo("student", page)))


@pytest.mark.parametrize("page", TEACHER_PAGES)
def test_teacher_page_headings_do_not_skip_a_level(page: str) -> None:
    _assert_outline(heading_levels(_demo("teacher", page)))


def test_the_profile_headings_do_not_skip_a_level(monkeypatch) -> None:
    from models import Role, User
    from services import auth_service

    teacher = User(id="usr_t99", display_name="Ms Rao", role=Role.TEACHER)
    monkeypatch.setattr(auth_service, "current_user", lambda: teacher)
    monkeypatch.setattr(auth_service, "current_email", lambda: "rao@school.org")
    at = AppTest.from_file(str(ROOT / "views" / "profile.py"), default_timeout=60).run()
    _assert_outline(heading_levels(at))


def test_the_admin_headings_do_not_skip_a_level(monkeypatch) -> None:
    from services import admin_service

    monkeypatch.setenv("ADMIN_PASSKEY", "x" * 20)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setattr(admin_service, "is_unlocked", lambda: True)
    monkeypatch.setattr(admin_service, "list_teacher_invites", lambda: ([], None))
    monkeypatch.setattr(admin_service, "list_teachers", lambda: ([], None))
    at = AppTest.from_file(str(ROOT / "views" / "admin.py"), default_timeout=60).run()
    _assert_outline(heading_levels(at))


# --------------------------------------------------------------------------
# BUG-023: a new screen opens at the top
# --------------------------------------------------------------------------
def _scroll_scripts(at: AppTest) -> list:
    return [e for e in at.get("html") if "scrollTo(0, 0)" in e.proto.body]


def test_the_first_load_does_not_scroll_anything() -> None:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert _scroll_scripts(at) == []


def test_leaving_the_welcome_page_scrolls_to_the_top_once() -> None:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    next(b for b in at.button if b.label == "Explore the demo").click().run()
    assert not at.exception, at.exception
    assert len(_scroll_scripts(at)) == 1
    at.run()
    assert _scroll_scripts(at) == [], "only on the run that changes screen"


def test_going_back_to_the_welcome_page_scrolls_to_the_top_once(monkeypatch) -> None:
    from components import layout

    calls: list = []
    monkeypatch.setattr(layout, "scroll_to_top", lambda: calls.append(1))
    at = _demo("student")
    calls.clear()  # arriving in the app from the welcome page is the other test
    next(b for b in at.button if b.label == "Welcome page").click().run()
    assert not at.exception, at.exception
    assert "Explore the demo" in [b.label for b in at.button]
    assert calls == [1]
    at.run()
    assert calls == [1], "only on the run that changes screen"


def test_moving_between_pages_of_the_app_does_not_scroll_on_its_own() -> None:
    at = _demo("student", "views/student_home.py")
    at.switch_page("views/study_camp.py").run()
    assert _scroll_scripts(at) == []


# --------------------------------------------------------------------------
# BUG-021: the browser tab says Camp Prep AI
# --------------------------------------------------------------------------
def test_tab_titles_carry_the_app_name() -> None:
    from components.navigation import tab_title

    assert tab_title("Welcome") == "Camp Prep AI"
    assert tab_title("My Work") == "My Work · Camp Prep AI"
    assert tab_title("Admin") == "Admin · Camp Prep AI"


def test_every_page_is_run_through_the_function_that_names_the_tab() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    code = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
    assert not re.search(r"\.run\(\)", code), "a page is run without naming the tab"
    assert code.count("run_page(") >= 4
