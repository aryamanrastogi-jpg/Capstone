"""Mock exam: building the paper, keeping time, marking and comparing."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from models import Assessment, Question
from services import mock_exam_service as exams

APP = str(Path(__file__).resolve().parent.parent / "app.py")
START = datetime(2026, 9, 1, 10, 0, 0)


def _assessment(topic, answered=2, unanswered=1):
    questions = [
        Question(
            question_text=f"{topic} question {i}",
            model_answer=f"Use the formula, substitute, answer {i + 3} cm.",
            max_marks=4,
        )
        for i in range(answered)
    ] + [
        Question(question_text=f"{topic} open {i}", max_marks=2) for i in range(unanswered)
    ]
    return Assessment(title=f"{topic} test", grade_level=9, topic=topic, questions=questions)


def _frame():
    return pd.DataFrame(
        {"topic": ["Algebra", "Algebra", "Geometry"], "percentage": [40.0, 60.0, 70.0]}
    )


def test_only_topics_with_model_answers_are_offered():
    empty = _assessment("Probability", answered=0)
    assert exams.available_topics([_assessment("Algebra"), empty]) == ["Algebra"]
    assert exams.default_topics(["Probability", "Algebra"], [_assessment("Algebra"), empty]) == [
        "Algebra"
    ]


def test_build_exam_uses_markable_questions_interleaved_across_topics():
    exam = exams.build_exam(
        "s1",
        [_assessment("Algebra"), _assessment("Geometry")],
        ["Algebra", "Geometry"],
        _frame(),
        question_count=3,
        now=START,
    )
    assert [i.topic for i in exam.items] == ["Algebra", "Geometry", "Algebra"]
    assert all(i.question.has_model_answer for i in exam.items)
    assert exam.time_limit_minutes == 3 * exams.MINUTES_PER_QUESTION
    assert exam.baseline_percentage == pytest.approx(56.7)


def test_build_exam_refuses_when_nothing_is_markable():
    with pytest.raises(ValueError):
        exams.build_exam("s1", [_assessment("Algebra", answered=0)], ["Algebra"], _frame())
    with pytest.raises(ValueError):
        exams.build_exam("s1", [_assessment("Algebra")], [], _frame())


def test_timer_is_computed_from_timestamps():
    exam = exams.build_exam("s1", [_assessment("Algebra")], ["Algebra"], _frame(), 1, now=START)
    assert exams.seconds_remaining(exam, START) == 240
    assert exams.seconds_remaining(exam, START + timedelta(minutes=10)) == 0
    assert exams.format_remaining(125) == "02:05"
    assert not exams.is_expired(exam, START + timedelta(minutes=4, seconds=10))
    assert exams.is_expired(exam, START + timedelta(minutes=5))


def test_submit_marks_every_question_and_flags_late_papers():
    exam = exams.build_exam("s1", [_assessment("Algebra")], ["Algebra"], _frame(), 2, now=START)
    first, second = exam.items
    exams.submit_exam(
        exam,
        {first.question.id: "Use the formula, substitute, answer 3 cm."},
        now=START + timedelta(minutes=30),
    )
    assert exam.is_submitted and exam.submitted_late
    assert len(exam.results) == 2
    assert exam.answers[second.question.id] == ""
    with pytest.raises(ValueError):
        exams.submit_exam(exam, {})


def test_on_time_submission_is_not_late_and_summary_compares_with_baseline():
    exam = exams.build_exam("s1", [_assessment("Algebra")], ["Algebra"], _frame(), 2, now=START)
    answers = {i.question.id: i.question.model_answer for i in exam.items}
    exams.submit_exam(exam, answers, now=START + timedelta(minutes=2))
    summary = exams.score_summary(exam, _frame())
    assert summary["late"] is False
    assert summary["baseline"] == 50.0
    assert summary["change"] == pytest.approx(summary["percentage"] - 50.0)
    (topic,) = summary["topics"]
    assert topic["before"] == 50.0 and topic["after"] == summary["percentage"]


def _student_app():
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    student = next(u for u in at.session_state["users"] if u.role.value == "student")
    at.session_state["current_user_id"] = student.id
    at.session_state["entered_demo"] = True
    at.run()
    at.switch_page("pages/mock_exam.py")
    at.run()
    assert not at.exception, at.exception
    return at


def test_a_student_can_sit_and_submit_a_mock_exam():
    at = _student_app()
    start = [b for b in at.button if b.label == "Start the mock exam"]
    if not start:
        pytest.skip("Seeded data has no markable questions for this student.")
    if not at.multiselect[0].value:
        at.multiselect[0].set_value([at.multiselect[0].options[0]])
        at.run()
        start = [b for b in at.button if b.label == "Start the mock exam"]
    start[0].click()
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["mock_exam"] is not None
    assert at.text_area

    at.text_area[0].input("Use the formula and substitute.")
    next(b for b in at.button if b.label == "Submit my answers").click()
    at.run()
    assert not at.exception, at.exception

    exam = at.session_state["mock_exam"]
    assert exam.is_submitted and exam.results
    text = " ".join(str(m.value) for m in at.markdown)
    assert all(i.question.model_answer not in text for i in exam.items)
    assert any("AI estimate" in i.value for i in at.info)
