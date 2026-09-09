"""Tests for question-only guidance.

The headline guarantee is the leak test: guidance is shown for a question the
student has not attempted, so if it could ever contain the answer the whole
"pointers, not answers" promise would be gone.
"""

from __future__ import annotations

import re

import pytest

from models import ErrorType, Question, Subject
from models.guidance import GENERIC_SHAPE
from services.hint_service import (
    MAX_HINT_LEVEL,
    escalating_pointers,
    guidance_for,
    guidance_for_questions,
    hint_level_for,
)


def _all_text(guidance) -> str:
    return " ".join(
        [guidance.shape] + guidance.approach + guidance.include + guidance.watch_out_for
    )


# ---------------------------------------------------------------------------
# 1. It cannot leak the answer
# ---------------------------------------------------------------------------
def test_guidance_never_contains_the_model_answer_values():
    """The guard that lets guidance be shown before any attempt."""
    question = Question(
        question_text="Solve for x: 3x + 7 = 22. Show your working.",
        model_answer="Subtract 7 from both sides to get 3x = 15, then divide by 3 "
        "to get x = 5.",
        marking_criteria="1 mark per step, 1 mark for x = 5.",
        max_marks=3,
    )
    text = _all_text(guidance_for(question))

    # Nothing from the model answer that is not already in the question.
    assert "x = 5" not in text
    assert "3x = 15" not in text
    assert "15" not in text


def test_guidance_contains_no_numbers_at_all():
    """A blunt rule, and the right one.

    Guidance describes method. The moment it starts quoting values it is doing
    the question. Numbering is added at render time, not here.
    """
    questions = [
        Question(question_text="Share 45 counters in the ratio 2 : 3.", max_marks=3),
        Question(
            question_text="A rectangular garden is 15 m by 8 m. Find its area.",
            max_marks=4,
        ),
        Question(question_text="Increase 80 by 15 percent.", max_marks=2),
        Question(question_text="Find the mean of 4, 9, 11 and 12.", max_marks=2),
        Question(question_text="Solve for x: 3x + 7 = 22.", max_marks=3),
    ]
    for guidance in guidance_for_questions(questions):
        body = " ".join(guidance.approach + guidance.include + guidance.watch_out_for)
        assert not re.search(r"\d", body), f"{guidance.shape} leaked a number: {body}"


def test_guidance_ignores_the_marking_criteria_too():
    question = Question(
        question_text="Find the area of a triangle with base 10 cm and height 6 cm.",
        model_answer="Area = 0.5 x 10 x 6 = 30 cm2.",
        marking_criteria="1 mark for the formula, 1 mark for 30 cm2.",
        max_marks=2,
    )
    text = _all_text(guidance_for(question))
    assert "30" not in text


# ---------------------------------------------------------------------------
# 2. It recognises the common shapes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected_shape",
    [
        ("Solve for x: 3x + 7 = 22.", "equation to solve"),
        ("Share 45 counters in the ratio 2 : 3.", "ratio and proportion"),
        ("A rectangular garden is 15 m by 8 m. Find the area.", "area, perimeter or volume"),
        ("Increase 80 by 15 percent.", "percentage"),
        ("Find the median of the following values.", "averages and spread"),
        ("What is the probability of rolling a six?", "probability"),
        (
            "A number is multiplied by 4 and then 6 is subtracted. Form an "
            "equation and solve it.",
            "word problem to turn into an equation",
        ),
        ("Explain why the reaction slows down over time.", "explain or describe"),
    ],
)
def test_common_question_shapes_are_recognised(text, expected_shape):
    guidance = guidance_for(Question(question_text=text, max_marks=2))
    assert guidance.shape == expected_shape
    assert guidance.is_specific


def test_an_unrecognised_question_still_gets_usable_guidance():
    guidance = guidance_for(Question(question_text="Have a go at this one.", max_marks=2))
    assert guidance.shape == GENERIC_SHAPE
    assert not guidance.is_specific
    assert guidance.approach, "generic guidance must still say something useful"
    assert guidance.include


def test_a_non_maths_question_falls_back_to_the_written_answer_frame():
    """Outside maths, an unrecognised question is almost always written."""
    guidance = guidance_for(
        Question(question_text="Account for the change in population.", max_marks=6),
        subject=Subject.ENGLISH,
    )
    assert guidance.shape == "explain or describe"


def test_written_answer_guidance_asks_for_the_students_own_thinking():
    """Straight from the brief: give points to include, and add your own."""
    guidance = guidance_for(Question(question_text="Explain photosynthesis.", max_marks=4))
    assert any("your own" in item.lower() for item in guidance.include)


# ---------------------------------------------------------------------------
# 3. It behaves predictably
# ---------------------------------------------------------------------------
def test_guidance_is_deterministic():
    question = Question(question_text="Solve for x: 2x = 8.", max_marks=2)
    assert guidance_for(question) == guidance_for(question)


def test_guidance_carries_the_question_it_belongs_to():
    question = Question(question_text="Solve for x: 2x = 8.", max_marks=2)
    guidance = guidance_for(question)
    assert guidance.question_id == question.id
    assert guidance.question_text == question.question_text


def test_guidance_works_for_a_question_with_no_model_answer():
    """The case this whole module exists for."""
    question = Question(question_text="Solve for x: 2x = 8.", max_marks=2)
    assert not question.has_model_answer
    assert guidance_for(question).approach


def test_guidance_for_questions_preserves_order():
    questions = [
        Question(question_text="Solve for x: 2x = 8.", max_marks=2),
        Question(question_text="Share 20 in the ratio 1 : 3.", max_marks=2),
    ]
    assert [g.question_id for g in guidance_for_questions(questions)] == [
        q.id for q in questions
    ]


# ---------------------------------------------------------------------------
# 4. The escalating hint ladder
#
# More goes at the same question earns a more pointed hint, never more of the
# answer. That distinction is the whole design.
# ---------------------------------------------------------------------------
RATIO_QUESTION = Question(
    question_text="Share 45 counters in the ratio 2 : 3.",
    model_answer="Total parts 5, one part is 9, so the shares are 18 and 27.",
    max_marks=3,
)


def test_hint_level_rises_with_attempts_and_then_stops():
    assert hint_level_for(0) == 1
    assert hint_level_for(1) == 1
    assert hint_level_for(2) == 2
    assert hint_level_for(3) == MAX_HINT_LEVEL
    assert hint_level_for(9) == MAX_HINT_LEVEL


def test_no_rung_of_the_ladder_contains_a_number():
    """The rule that separates a hint from the answer."""
    for level in range(1, MAX_HINT_LEVEL + 1):
        for pointer in escalating_pointers(
            RATIO_QUESTION, [ErrorType.INCORRECT_METHOD], Subject.MATHEMATICS, level
        ):
            assert not re.search(r"\d", pointer), f"level {level} leaked: {pointer}"


def test_no_rung_contains_a_value_from_the_model_answer():
    for level in range(1, MAX_HINT_LEVEL + 1):
        text = " ".join(escalating_pointers(RATIO_QUESTION, level=level))
        for value in ("18", "27", "9", "5"):
            assert value not in text


def test_each_rung_says_something_the_previous_one_did_not():
    rungs = [
        escalating_pointers(RATIO_QUESTION, level=level)
        for level in range(1, MAX_HINT_LEVEL + 1)
    ]
    assert rungs[0] != rungs[1] != rungs[2]
    # Later rungs move further along the method rather than repeating it.
    assert rungs[1][1] != rungs[0][1]


def test_the_maths_ladder_names_the_formula_before_the_substitution():
    """Aryaman's own framing: the formula is a hint, the numbers are the answer."""
    first = " ".join(escalating_pointers(RATIO_QUESTION, level=1)).lower()
    second = " ".join(escalating_pointers(RATIO_QUESTION, level=2)).lower()
    assert "formula" in first
    assert "place each value" in second


def test_a_written_question_gets_the_points_ladder_instead():
    question = Question(
        question_text="Explain why the reaction slows down over time.",
        max_marks=4,
    )
    first = " ".join(escalating_pointers(question, subject=Subject.SCIENCE, level=1))
    second = " ".join(escalating_pointers(question, subject=Subject.SCIENCE, level=2))
    third = " ".join(escalating_pointers(question, subject=Subject.SCIENCE, level=3))

    assert "points you would make" in first
    assert "reason" in second
    assert "your own" in third


def test_the_ladder_includes_what_the_grader_actually_spotted():
    pointers = escalating_pointers(RATIO_QUESTION, [ErrorType.UNIT_ERROR], level=1)
    assert any("unit" in p.lower() for p in pointers)


def test_the_level_is_clamped_to_the_ladder():
    assert escalating_pointers(RATIO_QUESTION, level=99) == escalating_pointers(
        RATIO_QUESTION, level=MAX_HINT_LEVEL
    )
    assert escalating_pointers(RATIO_QUESTION, level=0) == escalating_pointers(
        RATIO_QUESTION, level=1
    )


def test_the_shape_sentence_uses_the_right_article():
    equation = Question(question_text="Solve for x: 2x = 8.", max_marks=2)
    ratio = Question(question_text="Share 20 in the ratio 1 : 3.", max_marks=2)

    assert "an equation to solve question" in " ".join(escalating_pointers(equation))
    assert "a ratio and proportion question" in " ".join(escalating_pointers(ratio))
