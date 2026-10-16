"""Fixes from the student-workflow bug hunt (16 Oct 2026).

A long display name broke every estimate; a grading failure left a phantom
attempt behind; Study Camp could not suggest a topic it had no exact template
name for; results on sets a student can no longer see charted as "Unknown
topic"; the camp prompt showed for a topic at 96%; guidance on a re-attempt
numbered Q3 as Q1; and a second press of Save met an emptied form.
"""

from __future__ import annotations

import pandas as pd
import pytest

from models import Assessment, GradingResult, Question, ReviewStatus, Submission
from services import analytics_service as analytics
from services import assessment_service as service
from services import llm_service
from services import study_camp_service as camps
from services.repository import SessionRepository, SupabaseRepository
from tests.test_form_page_fixes import _app_as, _button
from tests.test_repository import FakeSupabase, _submission


# ---------------------------------------------------------------------------
# Long names
# ---------------------------------------------------------------------------
def test_a_long_display_name_still_fits_on_a_submission():
    name = "Alexandria Catherine Montgomery-Fitzwilliam the Third"  # 54 characters
    label = service.student_label(name)

    assert len(label) <= service.IDENTIFIER_MAX
    submission = service.build_submission(
        assessment_id="as_1",
        student_identifier=label,
        submission_text="x = 4",
        student_id="usr_s01",
        is_self_study=True,
    )
    assert submission.student_identifier == label


# ---------------------------------------------------------------------------
# Deleting a submission (used to take back work that could not be marked)
# ---------------------------------------------------------------------------
def test_deleting_a_submission_removes_its_results_in_both_backends(monkeypatch):
    from services import state

    submission = _submission()
    result = GradingResult(
        submission_id=submission.id, question_id="q_as_1_1", max_marks=2,
        suggested_score=1, confidence=0.5,
    )
    lists = {"s": [submission], "r": [result]}
    monkeypatch.setattr(state, "get_submissions", lambda: lists["s"])
    monkeypatch.setattr(state, "get_grading_results", lambda: lists["r"])
    demo = SessionRepository()
    assert demo.delete_submission(submission.id) is True
    assert lists == {"s": [], "r": []}
    assert demo.delete_submission(submission.id) is False

    db = FakeSupabase()
    live = SupabaseRepository(db)
    live.save_submission(submission)
    assert live.delete_submission(submission.id) is True
    assert db.tables["submissions"] == []


def test_my_work_takes_back_work_that_could_not_be_marked(monkeypatch):
    at = _app_as("student")
    me = at.session_state["current_user_id"]
    before = [s.id for s in at.session_state["submissions"] if s.student_id == me]

    from services import grading_service

    def unavailable(*args, **kwargs):
        raise RuntimeError("the marker is down")

    monkeypatch.setattr(grading_service, "grade_submission_outcomes", unavailable)
    # A set this demo student still has questions outstanding on.
    sets = at.selectbox[0]
    sets.set_value(next(o for o in sets.options if o.startswith("Percentages"))).run()
    at.text_area[0].input("x = 5").run()
    submit = next(b for b in at.button if b.label.startswith(("Submit attempt", "Get my estimate")))
    submit.click().run()

    assert not at.exception, at.exception
    assert any("could not be marked" in e.value for e in at.error)
    after = [s.id for s in at.session_state["submissions"] if s.student_id == me]
    assert after == before, "no phantom attempt is left behind"


# ---------------------------------------------------------------------------
# Study Camp topics
# ---------------------------------------------------------------------------
def _frame(rows):
    return pd.DataFrame(
        [{"topic": topic, "percentage": pct, "error_types": []} for topic, pct in rows]
    )


def test_a_topic_named_differently_from_the_templates_is_still_suggested(monkeypatch):
    monkeypatch.setattr(llm_service, "ai_enabled", lambda settings=None: False)
    frame = _frame([("linear equations", 30.0), ("Quadratics", 20.0), ("Fractions", 90.0)])

    # Quadratics has no templates and the AI is off, so it cannot be drilled;
    # "linear equations" is the Linear Equations template under another case.
    assert camps.suggest_topics(frame) == ["linear equations"]
    options = camps.available_topics_for(frame)
    assert "linear equations" in options and "Linear Equations" not in options


def test_with_the_ai_on_any_weak_topic_can_be_drilled(monkeypatch):
    monkeypatch.setattr(llm_service, "ai_enabled", lambda settings=None: True)
    frame = _frame([("Quadratics", 20.0), ("linear equations", 30.0)])

    assert camps.suggest_topics(frame) == ["Quadratics", "linear equations"]


# ---------------------------------------------------------------------------
# Results on sets the student can no longer see
# ---------------------------------------------------------------------------
def test_results_on_an_unseen_set_are_left_out_not_labelled_unknown():
    visible = Assessment(
        id="as_seen", title="Seen", grade_level=10, topic="Algebra",
        questions=[Question(id="q_seen", question_text="Q", max_marks=2)],
    )
    subs = [
        Submission(id="sub_seen", assessment_id="as_seen", student_identifier="S",
                   submission_text="a", student_id="usr_s01"),
        Submission(id="sub_gone", assessment_id="as_gone", student_identifier="S",
                   submission_text="a", student_id="usr_s01"),
    ]
    results = [
        GradingResult(submission_id="sub_seen", question_id="q_seen", max_marks=2,
                      suggested_score=1, confidence=0.5),
        GradingResult(submission_id="sub_gone", question_id="q_gone", max_marks=2,
                      suggested_score=0, confidence=0.5),
    ]

    frame = analytics.student_dataframe("usr_s01", results, [visible], subs)

    assert list(frame["topic"]) == ["Algebra"]


# ---------------------------------------------------------------------------
# Page behaviour
# ---------------------------------------------------------------------------
def test_the_camp_prompt_is_not_shown_for_a_strong_topic():
    at = _app_as("student")
    me = at.session_state["current_user_id"]
    for result in at.session_state["grading_results"]:
        owner = next(s for s in at.session_state["submissions"] if s.id == result.submission_id)
        if owner.student_id == me:
            result.suggested_score = result.max_marks
            result.teacher_approved_score = result.max_marks
            result.review_status = ReviewStatus.APPROVED
    at.run()

    assert not at.exception, at.exception
    assert "Build a study camp" not in [b.label for b in at.button]


def test_saving_a_set_clears_the_form_at_once():
    at = _app_as("student")
    at.switch_page("pages/my_questions.py")
    at.run()
    at.session_state["my_questions_rows"] = pd.DataFrame(
        [{"question_text": "What is 2+2?", "model_answer": "4", "max_marks": 1.0}]
    )
    at.run()
    at.text_input(key="mq_title").input("Quick set")
    at.text_input(key="mq_topic").input("Arithmetic")
    at.run()

    _button(at, "Save this set").click().run()

    assert not at.exception, at.exception
    assert at.text_input(key="mq_title").value == ""
    assert any("Saved" in s.value and "Quick set" in s.value for s in at.success)
    assert not at.error, "a second Save must not be needed to clear the form"


@pytest.mark.parametrize("numbers", [[3, 5]])
def test_guidance_keeps_the_real_question_numbers(numbers, monkeypatch):
    import streamlit as st

    from components import guidance as guidance_component

    drawn = []
    monkeypatch.setattr(
        guidance_component, "guidance_block", lambda g, number=None: drawn.append(number)
    )
    monkeypatch.setattr(st, "container", lambda **kwargs: _NullContext())
    guidance_component.guidance_list(["first", "second"], numbers=numbers)

    assert drawn == numbers


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------------------
# When the AI cannot mark (busy, over its free quota)
# ---------------------------------------------------------------------------
def test_only_a_failed_ai_call_counts_as_the_ai_being_unavailable():
    from services import ai_grading_service as ai

    question = Question(question_text="Solve 2x = 8.", model_answer="x = 4", max_marks=2)

    def outcome(reason):
        return ai._fallback(question, "x = 4", "sub_1", reason)

    assert not outcome(ai.NO_PROVIDER_REASON).ai_was_unavailable
    assert not outcome(ai.BLANK_ANSWER_REASON).ai_was_unavailable
    assert outcome("The AI provider call failed (ClientError).").ai_was_unavailable


def test_my_work_says_when_the_ai_was_too_busy_to_mark(monkeypatch):
    from services import ai_grading_service as ai
    from services import grading_service

    real = grading_service.grade_submission_outcomes

    def busy(*args, **kwargs):
        return [
            ai.AIGradingOutcome(
                result=o.result,
                path=ai.PATH_RULE_BASED,
                engine="rules",
                fallback_reason="The AI provider call failed (ClientError).",
            )
            for o in real(*args, **kwargs)
        ]

    at = _app_as("student")
    monkeypatch.setattr(grading_service, "grade_submission_outcomes", busy)
    sets = at.selectbox[0]
    sets.set_value(next(o for o in sets.options if o.startswith("Percentages"))).run()
    at.text_area[0].input("x = 5").run()
    submit = next(b for b in at.button if b.label.startswith(("Submit attempt", "Get my estimate")))
    submit.click().run()

    assert not at.exception, at.exception
    assert any("Your estimate is below" in s.value for s in at.success)
    assert any("AI marker was busy" in w.value for w in at.warning)
