"""Regression tests for BUG-010, 011, 012, 013, 014 and 027.

  010  a topic with no marked work has no baseline - never a 0% one
  011  leaving a class removes the teacher's sets and the teacher's view of you
  012  one user's upload text and drafts never reach the next user
  013  user-supplied text in the HTML helpers is escaped
  014  CSV cells that a spreadsheet would run as a formula are neutralised
  027  resetting demo data keeps who you are and drops per-user leftovers
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from models import Assessment, GradingResult, Question, ReviewStatus, StudyCamp
from services import mappers
from services import report_service as reports
from services import study_camp_service as camps
from services.practice_service import available_topics

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _app_as(role: str = "student", user_id: str | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    users = at.session_state["users"]
    wanted = next(u for u in users if (u.id == user_id if user_id else u.role.value == role))
    at.session_state["current_user_id"] = wanted.id
    at.session_state["entered_demo"] = True
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.fixture()
def session(monkeypatch: pytest.MonkeyPatch) -> Dict[str, Any]:
    """A plain dict standing in for st.session_state (services.state, auth)."""
    import streamlit as st

    fake: Dict[str, Any] = {}
    monkeypatch.setattr(st, "session_state", fake)
    return fake


# --------------------------------------------------------------------------
# BUG-010  Study camp baseline
# --------------------------------------------------------------------------
def _frame(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["topic", "percentage", "error_types"])


def test_a_topic_with_no_data_has_no_baseline_and_no_fake_improvement():
    known, unseen = available_topics()[0], available_topics()[1]
    frame = _frame([{"topic": known, "percentage": 40.0, "error_types": []}])

    assert camps.baseline_for(frame, [unseen]) is None
    assert camps.baseline_for(_frame([]), [unseen]) is None

    camp = camps.build_camp("s1", frame, topics=[unseen], duration_days=3)
    assert camp.baseline_percentage is None
    # Missing data is not evidence of weakness: start at the standard level.
    assert camps.difficulty_for(camp.baseline_percentage) == "Core"

    camps.record_session_result(camp, 1, 1)
    assert camp.latest_percentage == 25.0
    assert camp.improvement is None, "1/4 right must not read as +25 points"
    assert camps.progress_summary(camp)["baseline"] is None


def test_topics_without_data_are_left_out_of_a_mixed_baseline():
    known, unseen = available_topics()[0], available_topics()[1]
    frame = _frame([{"topic": known, "percentage": 40.0, "error_types": []}])

    assert camps.baseline_for(frame, [known, unseen]) == 40.0
    assert camps.topics_without_baseline(frame, [known, unseen]) == [unseen]
    assert camps.difficulty_for(40.0) == "Foundation"


def test_a_camp_without_a_baseline_survives_the_database_mapping():
    camp = StudyCamp(student_id="s1", topics=["Percentages"], duration_days=3)
    row, _ = mappers.study_camp_to_rows(camp)
    # Migration 007 makes the column nullable: "no baseline" round-trips as None.
    assert row["baseline_percentage"] is None
    restored = mappers.study_camp_from_rows(row, [])
    assert restored.baseline_percentage is None


def test_the_study_camp_page_says_no_baseline_yet():
    at = _app_as("student")
    student_id = at.session_state["current_user_id"]
    camp = camps.build_camp(student_id, _frame([]), topics=[available_topics()[0]], duration_days=3)
    camps.record_session_result(camp, 1, 1)
    at.session_state["study_camps"] = [camp]
    at.switch_page("pages/study_camp.py")
    at.run()

    assert not at.exception, at.exception
    values = {m.label: m.value for m in at.metric}
    assert values["Starting point"] == "No baseline yet"
    assert values["Change"] == "—"


# --------------------------------------------------------------------------
# BUG-011  Leaving a class
# --------------------------------------------------------------------------
def test_leaving_a_class_hides_the_teachers_sets_and_the_students_work():
    at = _app_as("student")
    student_id = at.session_state["current_user_id"]
    student = next(u for u in at.session_state["users"] if u.id == student_id)
    teacher_titles = {a.title for a in at.session_state["assessments"] if not a.student_created}
    assert student.teacher_id

    at.switch_page("pages/my_class.py")
    at.run()
    next(b for b in at.button if b.label == "Leave class").click().run()
    student = next(u for u in at.session_state["users"] if u.id == student_id)
    assert student.teacher_id is None

    at.switch_page("pages/student_home.py")
    at.run()
    assert not at.exception, at.exception
    offered = [
        option
        for box in at.selectbox
        if box.label.startswith("Which piece")
        for option in box.options
    ]
    assert not any(title in option for option in offered for title in teacher_titles)

    teacher = next(u for u in at.session_state["users"] if u.role.value == "teacher")
    at.session_state["current_user_id"] = teacher.id
    at.run()
    at.switch_page("pages/review_grading.py")
    at.run()
    assert not at.exception, at.exception
    at.toggle[0].set_value(False).run()
    queue = next(s for s in at.selectbox if s.label == "Submission")
    assert queue.options, "the rest of the class is still there"
    assert not any(student.display_name in option for option in queue.options)


# --------------------------------------------------------------------------
# BUG-012  Upload text leaking between users
# --------------------------------------------------------------------------
def test_one_students_upload_text_is_not_shown_to_the_next():
    at = _app_as("student")
    first = at.session_state["current_user_id"]
    at.session_state[f"student_upload_extracted:{first}"] = {
        "text": "STUDENT-A PRIVATE ANSWERS",
        "filename": "a.txt",
    }
    other = next(
        u for u in at.session_state["users"] if u.is_student and u.id != first
    )
    at.session_state["current_user_id"] = other.id
    at.run()
    at.switch_page("pages/student_home.py")
    at.run()
    assert not at.exception, at.exception
    for index, _ in enumerate(
        next(s for s in at.selectbox if s.label.startswith("Which piece")).options
    ):
        next(s for s in at.selectbox if s.label.startswith("Which piece")).select_index(index).run()
        if at.radio:
            at.radio[0].set_value("Upload a file").run()
            break
    shown = " ".join(t.value or "" for t in at.text_area)
    assert "STUDENT-A PRIVATE" not in shown


def test_switching_identity_and_signing_out_clear_per_user_keys(session):
    from services import auth_service
    from services import state

    session.update(
        {
            "current_user_id": "usr_s01",
            "student_upload_extracted:usr_s01": {"text": "x"},
            "upload_extracted": {"text": "y"},
            "mock_exam": object(),
            "mock_answer_ex1_q1": "4",
            "users": ["kept"],
        }
    )
    state.set_current_user("usr_s02")
    assert session["current_user_id"] == "usr_s02"
    assert set(session) == {"current_user_id", "users"}

    session["mock_exam"] = object()
    session["my_questions_rows"] = []
    state.set_current_user("usr_s02")  # same person: nothing to clear
    assert "mock_exam" in session

    auth_service.sign_out()
    assert "mock_exam" not in session and "my_questions_rows" not in session
    assert session["users"] == ["kept"]

    session["practice_request"] = {}
    state.leave_demo()
    assert "practice_request" not in session


# --------------------------------------------------------------------------
# BUG-027  Reset demo data
# --------------------------------------------------------------------------
def test_reset_keeps_the_teacher_and_drops_leftovers(session):
    from data.sample_data import TEACHER_ID
    from services import state

    state.init_session_state()
    session["current_user_id"] = TEACHER_ID
    session["mock_exam"] = object()
    session["student_upload_extracted:usr_s02"] = {"text": "x"}
    session["upload_extracted"] = {"text": "y"}
    session["assessments"] = []

    state.reset_to_samples()

    assert session["current_user_id"] == TEACHER_ID
    assert session["assessments"], "the sample data is back"
    for key in ("mock_exam", "student_upload_extracted:usr_s02", "upload_extracted"):
        assert key not in session


def test_reset_falls_back_to_the_demo_student_for_an_unknown_user(session):
    from data.sample_data import DEMO_STUDENT_ID
    from services import state

    state.init_session_state()
    session["current_user_id"] = "usr_not_in_seed"
    state.reset_to_samples()
    assert session["current_user_id"] == DEMO_STUDENT_ID


# --------------------------------------------------------------------------
# BUG-013  HTML injection
# --------------------------------------------------------------------------
PAYLOAD = '<img src=x onerror="alert(1)">'


@pytest.fixture()
def rendered(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    from components import layout

    out: List[str] = []
    fake = SimpleNamespace(
        markdown=lambda body, **_: out.append(body),
        html=lambda body, **_: out.append(body),
        caption=lambda body, **_: out.append(body),
    )
    monkeypatch.setattr(layout, "st", fake)
    return out


def test_page_header_escapes_and_renders_a_real_h1(rendered):
    from components.layout import page_header

    page_header("My Work", f"Signed in as {PAYLOAD}", eyebrow=PAYLOAD)
    header = rendered[-1]
    assert "<img" not in header
    assert "&lt;img" in header
    assert '<h1 class="campprep-title">My Work</h1>' in header


def test_cards_hints_and_badges_escape_their_text(rendered):
    from components.layout import hint_note, info_card
    from components.status_badges import error_chip

    info_card(PAYLOAD, PAYLOAD, icon=PAYLOAD)
    hint_note(PAYLOAD)
    chip = error_chip(PAYLOAD, render=False)
    for html in [*rendered, chip]:
        assert "<img" not in html


# --------------------------------------------------------------------------
# BUG-014  CSV formula injection
# --------------------------------------------------------------------------
@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_csv_cells_that_look_like_formulas_are_neutralised(prefix):
    question = Question(question_text=f"{prefix}HYPERLINK(\"http://x\")", model_answer="1", max_marks=2)
    assessment = Assessment(title=f"{prefix}cmd", grade_level=10, topic="T", questions=[question])
    from services import assessment_service

    submission = assessment_service.build_submission(assessment.id, "S-1", submission_text="1")
    result = GradingResult(
        submission_id=submission.id, question_id=question.id, max_marks=2,
        suggested_score=2, confidence=0.9, student_feedback=f"{prefix}SUM(A1)",
    )
    from services.grading_service import apply_teacher_decision

    apply_teacher_decision(result, ReviewStatus.APPROVED)
    text = reports.to_csv(reports.build_report([result], [assessment], [submission]))
    rows = list(csv.reader(io.StringIO(text.decode("utf-8-sig"))))
    header = rows.index(reports.REPORT_COLUMNS)
    row = dict(zip(reports.REPORT_COLUMNS, rows[header + 1]))

    assert row["assessment"] == f"'{prefix}cmd"
    assert row["question"].startswith(f"'{prefix}")
    assert row["score"] == "2.0", "numbers are left alone"


def test_negative_numbers_stay_numbers():
    assert reports._csv_safe(-3.5) == -3.5
    assert reports._csv_safe("plain") == "plain"
    assert reports._csv_safe("-1") == "'-1"
    # Models strip surrounding whitespace, but the export guards these anyway.
    assert reports._csv_safe("\tcmd") == "'\tcmd"
    assert reports._csv_safe("\r=1") == "'\r=1"
