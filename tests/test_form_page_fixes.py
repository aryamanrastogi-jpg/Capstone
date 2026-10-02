"""Regression tests for form and page fixes.

BUG-004 Clear form, BUG-015 copies drop the owner's answers, BUG-019 teacher
uploads take the next attempt number, BUG-021 delete needs confirming,
BUG-025 the "Go to ..." button survives the rerun after a save.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from models import Assessment, Question

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _app_as(role: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    wanted = next(u for u in at.session_state["users"] if u.role.value == role)
    at.session_state["current_user_id"] = wanted.id
    at.session_state["entered_demo"] = True
    at.run()
    assert not at.exception, at.exception
    return at


def _button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


def _labels(at: AppTest):
    return [b.label for b in at.button]


# --------------------------------------------------------------- BUG-004
def test_clear_form_on_my_questions_resets_without_error():
    at = _app_as("student")
    at.switch_page("pages/my_questions.py")
    at.run()
    at.text_input(key="mq_title").input("Algebra worksheet")
    at.text_input(key="mq_topic").input("Algebra")
    at.run()

    _button(at, "Clear form").click().run()

    assert not at.exception, at.exception
    assert at.text_input(key="mq_title").value == ""
    assert at.text_input(key="mq_topic").value == ""


def test_clear_form_on_create_assessment_resets_without_error():
    at = _app_as("teacher")
    at.switch_page("pages/create_assessment.py")
    at.run()
    at.text_input(key="ca_title").input("Class test")
    at.text_input(key="ca_topic").input("Algebra")
    at.run()

    _button(at, "Clear form").click().run()

    assert not at.exception, at.exception
    assert at.text_input(key="ca_title").value == ""
    assert at.text_input(key="ca_topic").value == ""


# --------------------------------------------------------------- BUG-025
def test_go_to_upload_responses_survives_the_rerun_after_saving():
    at = _app_as("teacher")
    at.switch_page("pages/create_assessment.py")
    at.run()
    at.session_state["create_assessment_rows"] = pd.DataFrame(
        [{"question_text": "What is 2+2?", "model_answer": "4",
          "marking_criteria": "", "max_marks": 1.0}]
    )
    at.run()
    at.text_input(key="ca_title").input("T1")
    at.text_input(key="ca_topic").input("Algebra")
    at.run()
    _button(at, "Save assessment").click().run()
    assert not at.exception, at.exception

    # Any other interaction reruns the script with save_clicked False.
    at.run()
    assert "Go to Upload Responses" in _labels(at)
    _button(at, "Go to Upload Responses").click().run()
    assert not at.exception, at.exception
    assert "Go to Upload Responses" not in _labels(at)


# --------------------------------------------------------------- BUG-015
def test_a_copy_does_not_carry_the_owners_answers(monkeypatch):
    from services import assessment_service as service

    monkeypatch.setattr(service, "save_assessment", lambda a: a)
    original = Assessment(
        title="Shared",
        grade_level=9,
        topic="Algebra",
        owner_id="usr_alice",
        student_created=True,
        is_shared=True,
        questions=[
            Question(
                question_text="Solve 2x = 10.",
                model_answer="x = 5",
                marking_criteria="1 mark method, 1 mark answer",
                max_marks=2,
            )
        ],
    )

    copy = service.copy_assessment_to(original, "usr_bob")

    assert all(q.model_answer == "" for q in copy.questions)
    assert all(q.marking_criteria == "" for q in copy.questions)
    # Behaves like any set with no answers saved: guidance, not a score.
    assert not copy.is_gradable
    assert len(copy.questions_missing_model_answers) == len(copy.questions)
    # The original is untouched.
    assert original.questions[0].model_answer == "x = 5"


# --------------------------------------------------------------- BUG-021
def _student_with_a_saved_set() -> AppTest:
    at = _app_as("student")
    at.switch_page("pages/my_questions.py")
    at.run()
    at.session_state["my_questions_rows"] = pd.DataFrame(
        [{"question_text": "Solve 2x = 8.", "model_answer": "", "max_marks": 2.0}]
    )
    at.run()
    at.text_input(key="mq_title").input("Delete me")
    at.text_input(key="mq_topic").input("Algebra")
    at.run()
    _button(at, "Save this set").click().run()
    assert not at.exception, at.exception
    return at


def _owned_titles(at: AppTest):
    me = at.session_state["current_user_id"]
    return [a.title for a in at.session_state["assessments"] if a.owner_id == me]


def test_delete_requires_confirmation():
    at = _student_with_a_saved_set()
    assert "Delete me" in _owned_titles(at)

    _button(at, "Delete").click().run()
    assert not at.exception, at.exception
    assert "Delete me" in _owned_titles(at), "one click must not delete"
    assert "Yes, delete" in _labels(at)

    _button(at, "Cancel").click().run()
    assert "Delete me" in _owned_titles(at)
    assert "Yes, delete" not in _labels(at)

    _button(at, "Delete").click().run()
    _button(at, "Yes, delete").click().run()
    assert not at.exception, at.exception
    assert "Delete me" not in _owned_titles(at)
    # BUG-028: the confirmation survives the rerun that follows it.
    assert any("Deleted" in s.value for s in at.success)


# --------------------------------------------------------------- BUG-019
def test_teacher_uploads_take_the_next_attempt_number():
    at = _app_as("teacher")
    at.switch_page("pages/upload_responses.py")
    at.run()
    assert not at.exception, at.exception

    assessment_id = at.selectbox[0].value
    student_box = next(s for s in at.selectbox if s.label == "Student *")
    student_id = student_box.value

    def attempt_numbers():
        return sorted(
            s.attempt_number
            for s in at.session_state["submissions"]
            if s.student_id == student_id and s.assessment_id == assessment_id
        )

    before = attempt_numbers()
    for _ in range(2):
        at.text_area[0].input("x = 4 because 2x = 8")
        at.checkbox[0].uncheck()
        at.run()
        _button(at, "Confirm submission").click().run()
        assert not at.exception, at.exception

    after = attempt_numbers()
    assert len(after) == len(before) + 2
    assert after[-2:] == [len(before) + 1, len(before) + 2]
    assert len(set(after)) == len(after), "no duplicate attempt numbers"


# --------------------------------------------------------------- BUG-018
def test_students_with_the_same_name_are_both_selectable():
    from models import Role, User

    at = _app_as("teacher")
    teacher_id = at.session_state["current_user_id"]
    users = at.session_state["users"]
    users.append(User(id="usr_twin1", display_name="Alex Tan", role=Role.STUDENT,
                      teacher_id=teacher_id))
    users.append(User(id="usr_twin2", display_name="Alex Tan", role=Role.STUDENT,
                      teacher_id=teacher_id))
    at.session_state["users"] = users

    for page, label in (
        ("pages/upload_responses.py", "Student *"),
        ("pages/practice_generator.py", "Whose results should the practice target?"),
    ):
        at.switch_page(page)
        at.run()
        assert not at.exception, at.exception
        box = next(s for s in at.selectbox if s.label == label)
        assert "Alex Tan (usr_twin1)" in box.options and "Alex Tan (usr_twin2)" in box.options
        box.set_value("usr_twin2").run()
        assert not at.exception, at.exception
        box = next(s for s in at.selectbox if s.label == label)
        assert box.value == "usr_twin2"
