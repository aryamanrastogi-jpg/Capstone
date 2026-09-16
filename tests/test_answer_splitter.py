"""Splitting one block of uploaded text into per-question answers.

The text here is written the way it actually arrives from a PDF or a phone
note: a name line at the top, inconsistent markers, working steps that are
themselves numbered, decimals at the start of a line, answers run together on
one line. The rule under test is simple to state - split only when the markers
are unambiguous, otherwise say so and fall back to the whole block.
"""

from __future__ import annotations

import pytest

from models import Question
from services.answer_splitter import FALLBACK_SUFFIX, split_answers
from services.grading_service import grade_submission


def _questions(count: int) -> list[Question]:
    return [
        Question(
            id=f"q{index}",
            question_text=f"Question number {index} about something.",
            model_answer="A model answer long enough to be valid.",
            marking_criteria="1 mark for the method.",
            max_marks=2,
        )
        for index in range(1, count + 1)
    ]


THREE = _questions(3)


def _answers(split) -> list[str]:
    return [split.answers[q.id] for q in THREE]


# ---------------------------------------------------------------------------
# Confident splits
# ---------------------------------------------------------------------------
def test_q_markers_with_a_header_line():
    text = (
        "S-1102   Homework 3   Linear equations\n"
        "\n"
        "Q1: 3x + 7 = 22\n"
        "3x = 15\n"
        "x = 5\n"
        "\n"
        "Q2) Let the number be n\n"
        "4n - 6 = 26 so n = 8\n"
        "Q3 - area = 1/2 x 9 x 6 = 27 cm2\n"
    )
    split = split_answers(text, THREE)

    assert split.confident, split.message
    assert _answers(split) == [
        "3x + 7 = 22\n3x = 15\nx = 5",
        "Let the number be n\n4n - 6 = 26 so n = 8",
        "area = 1/2 x 9 x 6 = 27 cm2",
    ]
    assert split.preamble.startswith("S-1102")
    assert "not given to any question" in split.message


@pytest.mark.parametrize(
    "markers",
    [
        ("1.", "2.", "3."),
        ("1)", "2)", "3)"),
        ("(1)", "(2)", "(3)"),
        ("Question 1", "Question 2", "Question 3"),
        ("Question 1:", "question 2:", "QUESTION 3:"),
        ("Q.1", "Q.2", "Q.3"),
        ("Answer 1:", "Answer 2:", "Answer 3:"),
        ("  1.", "\t2.", "   3."),
    ],
)
def test_common_marker_styles(markers):
    text = "\n".join(f"{marker} answer {n}" for n, marker in enumerate(markers, start=1))
    split = split_answers(text, THREE)

    assert split.confident, split.message
    assert _answers(split) == ["answer 1", "answer 2", "answer 3"]


def test_windows_line_endings():
    split = split_answers("1. first\r\n2. second\r\n3. third\r\n", THREE)
    assert split.confident
    assert _answers(split) == ["first", "second", "third"]


def test_answers_run_together_on_one_line_as_pdfs_often_do():
    text = "Q1: x = 5. Q2: n = 8. Q3: 27 cm2"
    split = split_answers(text, THREE)

    assert split.confident, split.message
    assert _answers(split) == ["x = 5.", "n = 8.", "27 cm2"]


def test_numbered_working_inside_q_markers_is_left_alone():
    """With explicit Q markers, numbered steps are part of the answer."""
    text = (
        "Q1\n"
        "1. subtract 7 from both sides\n"
        "2. divide by 3\n"
        "Q2\n"
        "1. add 6\n"
        "2. divide by 4\n"
        "Q3\n"
        "27 cm2\n"
    )
    split = split_answers(text, THREE)

    assert split.confident, split.message
    assert split.answers["q1"] == "1. subtract 7 from both sides\n2. divide by 3"
    assert split.answers["q2"] == "1. add 6\n2. divide by 4"


def test_a_decimal_at_the_start_of_a_line_is_not_a_marker():
    text = "1. 350 / 100\n3.5 x 20 = 70\n2. 25% of 240\n60 rupees off\n3. 180 rupees"
    split = split_answers(text, THREE)

    assert split.confident, split.message
    assert split.answers["q1"] == "350 / 100\n3.5 x 20 = 70"


def test_sub_parts_stay_inside_their_question():
    text = "1(a) area = 60 cm2\n1(b) perimeter = 34 cm\n2. 27 cm2\n3) 180 rupees"
    split = split_answers(text, THREE)

    assert split.confident, split.message
    assert split.answers["q1"] == "area = 60 cm2\n1(b) perimeter = 34 cm"
    assert split.answers["q2"] == "27 cm2"


def test_q_sub_parts_stay_inside_their_question():
    text = "Q1a) 60 cm2\nQ1b) 34 cm\nQ2 27 cm2\nQ3 180"
    split = split_answers(text, THREE)

    assert split.confident, split.message
    assert split.answers["q1"] == "60 cm2\nQ1b) 34 cm"
    assert split.answers["q3"] == "180"


def test_lettered_parts_map_to_questions_in_order_when_one_per_question():
    split = split_answers("(a) x = 5\n(b) n = 8\n(c) 27 cm2", THREE)

    assert split.confident, split.message
    assert _answers(split) == ["x = 5", "n = 8", "27 cm2"]
    assert "(a), (b)" in split.message


def test_a_skipped_question_is_blank_and_named():
    """Q2 left out on purpose: graded blank, and the message says so."""
    split = split_answers("Q1: x = 5\nQ3: 27 cm2", THREE)

    assert split.confident, split.message
    assert split.answers["q2"] == ""
    assert split.missing_count == 1
    assert "Q2" in split.message and "blank" in split.message


def test_a_single_question_assessment_takes_everything():
    one = _questions(1)
    split = split_answers("Q1: subtract 8 so 5x = 35\nx = 7", one)

    assert split.confident
    assert split.answers == {"q1": "subtract 8 so 5x = 35\nx = 7"}


# ---------------------------------------------------------------------------
# Not confident - fall back and say why
# ---------------------------------------------------------------------------
def _assert_fallback(split, fragment: str):
    assert not split.confident
    assert split.answers == {}
    assert fragment in split.message
    assert split.message.endswith(FALLBACK_SUFFIX)


def test_no_markers_at_all():
    split = split_answers(
        "I subtracted 7 and got 3x = 15 so x is 5. For the next one n = 8.", THREE
    )
    _assert_fallback(split, "No question markers")


def test_numbered_working_steps_that_restart_are_not_questions():
    text = "1. subtract 7\n2. divide by 3\n1. add 6\n2. divide by 4"
    _assert_fallback(split_answers(text, THREE), "out of order")


def test_a_question_number_the_assessment_does_not_have():
    text = "Q1: a\nQ2: b\nQ3: c\nQ4: d"
    _assert_fallback(split_answers(text, THREE), "question 4")


def test_too_few_markers_to_trust():
    """One marker in a two-question set says nothing about where Q2 starts."""
    split = split_answers("Q1: Subtract 7 from both sides so 3x = 15. x = 5.", _questions(2))
    _assert_fallback(split, "too few")


def test_lettered_parts_that_do_not_match_the_question_count():
    split = split_answers("(a) area 60 cm2\n(b) perimeter 34 cm", THREE)
    _assert_fallback(split, "cannot be matched")


def test_answer_followed_by_a_number_is_not_a_marker():
    """'Answer 12 rupees' is an answer, not a label for question 12."""
    split = split_answers("Answer 12 rupees\nAnswer 5 cm", THREE)
    _assert_fallback(split, "No question markers")


def test_empty_text_or_no_questions():
    assert not split_answers("", THREE).confident
    assert not split_answers("Q1: x = 5\nQ2: y", []).confident


# ---------------------------------------------------------------------------
# Grading uses the split
# ---------------------------------------------------------------------------
def test_each_question_is_graded_only_against_its_own_answer(seed):
    """The reason for splitting: Q1's working must not earn marks on Q2."""
    assessments, _, _, _ = seed
    area = next(a for a in assessments if a.id == "as_area01")
    text = (
        "S-1104  Class exercise\n"
        "Q1: Area = 12 x 5 = 60 cm2. Perimeter = 2 x (12 + 5) = 34 cm.\n"
        "Q2: skipped\n"
    )

    split = split_answers(text, area.questions)
    assert split.confident, split.message

    whole = {r.question_id: r for r in grade_submission(area.questions, text, "s1")}
    per_q = {
        r.question_id: r
        for r in grade_submission(area.questions, text, "s2", answers=split.answers)
    }
    q1, q2 = (q.id for q in area.questions)
    assert whole[q2].suggested_score > 0, "whole-block grading leaks Q1 into Q2"
    assert per_q[q2].suggested_score == 0
    assert per_q[q1].suggested_score == whole[q1].suggested_score


@pytest.fixture(scope="module")
def seed():
    from data.sample_data import build_sample_data

    return build_sample_data()
