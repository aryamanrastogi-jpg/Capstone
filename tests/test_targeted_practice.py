"""Targeted practice: chosen from real results, pointers never answers.

Three things are guaranteed here:

* the choice of topic, error category and difficulty follows the evidence -
  weakest topics first and weighted, the errors that actually happened, a
  lower level for method and concept errors - and each item says why;
* every topic in the seed data can be practised;
* a method pointer never contains the value its question resolves to.
"""

from __future__ import annotations

import random
import re
from math import gcd
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from data.sample_data import build_sample_data
from models import ErrorType
from services import analytics_service as analytics
from services import practice_service
from services import targeted_practice_service as targeted
from services.practice_service import (
    DIFFICULTIES,
    generate_practice_questions,
    template_topic_for,
)

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PRACTICE_PAGE = "pages/practice_generator.py"

ARITH = ErrorType.ARITHMETIC_ERROR.value
UNIT = ErrorType.UNIT_ERROR.value
CONCEPT = ErrorType.CONCEPTUAL_ERROR.value
METHOD = ErrorType.INCORRECT_METHOD.value


@pytest.fixture(scope="module")
def seed():
    return build_sample_data()


def _frame(rows):
    """rows: (topic, percentage, [error values])"""
    return pd.DataFrame(
        [{"topic": t, "percentage": p, "error_types": list(e)} for t, p, e in rows]
    )


# ---------------------------------------------------------------------------
# Template coverage
# ---------------------------------------------------------------------------
def test_every_topic_in_the_seed_data_has_templates(seed):
    assessments = seed[0]
    for topic in {a.topic for a in assessments}:
        assert template_topic_for(topic) is not None, topic
        assert generate_practice_questions(topic, ErrorType.UNIT_ERROR, "Core", 4)


@pytest.mark.parametrize("topic", practice_service.TOPICS)
def test_every_template_topic_has_at_least_three_templates(topic):
    assert len(practice_service._TEMPLATES[topic]) >= 3


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Linear Equations", "Linear Equations"),
        ("linear equations", "Linear Equations"),
        ("Simultaneous equations", "Linear Equations"),
        ("Percentage change", "Percentages"),
        ("Ratio", "Ratio and Proportion"),
        ("Area of compound shapes", "Area and Perimeter"),
        ("Mean, median and mode", "Data Handling"),
        ("Adding fractions", "Fractions and Decimals"),
        ("Photosynthesis", None),
        ("", None),
        ("Meaningful", None),
    ],
)
def test_free_text_topics_map_to_a_template_topic(name, expected):
    assert template_topic_for(name) == expected


def test_a_topic_alias_generates_under_the_template_topic():
    questions = generate_practice_questions("percentage change", ErrorType.UNIT_ERROR, "Core", 2)
    assert all(q.topic == "Percentages" for q in questions)


def test_start_continues_the_template_rotation():
    first = generate_practice_questions("Area and Perimeter", ErrorType.UNIT_ERROR, "Core", 4)
    later = generate_practice_questions(
        "Area and Perimeter", ErrorType.UNIT_ERROR, "Core", 2, start=2
    )
    assert [q.question_text for q in later] == [q.question_text for q in first[2:]]
    assert [q.number for q in later] == [1, 2]


# ---------------------------------------------------------------------------
# Pointers, not answers
# ---------------------------------------------------------------------------
def _contains_value(text: str, value: str) -> bool:
    """`value` appears as a number in `text` (not as part of a longer number)."""
    return re.search(rf"(?<![\d.]){re.escape(value)}(?![\d]|\.\d)", text) is not None


@pytest.mark.parametrize("topic", practice_service.TOPICS)
def test_a_method_pointer_never_contains_the_answer(topic):
    for builder in practice_service._TEMPLATES[topic]:
        for difficulty in DIFFICULTIES:
            low, high = practice_service._DIFFICULTY_RANGE[difficulty]
            for index in range(25):
                built = builder(random.Random(f"{topic}|{difficulty}|{index}"), low, high)
                for value in built.answers:
                    if _contains_value(built.question, value):
                        continue  # a number the question itself states is fair game
                    assert not _contains_value(built.pointer, value), (
                        f"{builder.__name__} pointer gives away {value!r}: {built.pointer}"
                    )


def test_practice_questions_carry_no_answer_field():
    question = generate_practice_questions("Percentages", ErrorType.UNIT_ERROR, "Core", 1)[0]
    assert not any("answer" in name for name in vars(question))


# ---------------------------------------------------------------------------
# New templates still resolve to clean values
# ---------------------------------------------------------------------------
def _all_questions(topic):
    for difficulty in DIFFICULTIES:
        for error in ErrorType:
            yield from generate_practice_questions(topic, error, difficulty, 10)


def test_bracket_and_division_equations_have_whole_positive_solutions():
    for q in _all_questions("Linear Equations"):
        match = re.search(r"Solve for x: (\d+)\(x \+ (\d+)\) = (\d+)", q.question_text)
        if match:
            a, b, c = (int(g) for g in match.groups())
            assert c % a == 0 and c // a - b > 0, q.question_text
        match = re.search(r"Solve for x: x/(\d+) \+ (\d+) = (\d+)", q.question_text)
        if match:
            d, b, c = (int(g) for g in match.groups())
            assert c - b > 0, q.question_text


def test_ratio_to_simplify_is_not_already_simple():
    seen = 0
    for q in _all_questions("Ratio and Proportion"):
        match = re.search(r"Write the ratio (\d+) : (\d+)", q.question_text)
        if match:
            seen += 1
            assert gcd(*(int(g) for g in match.groups())) > 1, q.question_text
    assert seen


def test_missing_side_divides_exactly():
    for q in _all_questions("Area and Perimeter"):
        match = re.search(r"area of (\d+) cm\^2 and a width of (\d+) cm", q.question_text)
        if match:
            area, width = (int(g) for g in match.groups())
            assert area % width == 0, q.question_text


def test_missing_score_questions_have_a_whole_positive_answer():
    seen = 0
    for q in _all_questions("Data Handling"):
        match = re.search(
            r"mean of five test scores is (\d+)\. Four of the scores are ([\d, ]+)\.",
            q.question_text,
        )
        if match:
            seen += 1
            mean = int(match.group(1))
            known = [int(v) for v in match.group(2).split(",")]
            assert mean * 5 - sum(known) > 0, q.question_text
    assert seen


def test_recipe_and_survey_percentages_are_whole():
    for q in _all_questions("Ratio and Proportion"):
        match = re.search(r"recipe for (\d+) people uses (\d+) g", q.question_text)
        if match:
            people, grams = (int(g) for g in match.groups())
            assert grams % people == 0, q.question_text
    for q in _all_questions("Percentages"):
        match = re.search(r"(\d+) out of (\d+) students", q.question_text)
        if match:
            part, total = (int(g) for g in match.groups())
            assert (part * 100) % total == 0, q.question_text


# ---------------------------------------------------------------------------
# Choosing from the evidence
# ---------------------------------------------------------------------------
def test_the_weakest_topic_comes_first_and_gets_the_most_questions():
    frame = _frame(
        [
            ("Percentages", 20, [ARITH]),
            ("Percentages", 30, [ARITH]),
            ("Linear Equations", 70, [UNIT]),
            ("Area and Perimeter", 60, [UNIT]),
        ]
    )
    targets, evidence, _ = targeted.build_targets(frame, total=10)

    assert [e.topic for e in evidence] == ["Percentages", "Area and Perimeter", "Linear Equations"]
    per_topic = {}
    for t in targets:
        per_topic[t.topic] = per_topic.get(t.topic, 0) + t.count
    assert sum(per_topic.values()) == 10
    assert targets[0].topic == "Percentages"
    assert per_topic["Percentages"] > per_topic["Area and Perimeter"] > per_topic["Linear Equations"]


def test_error_categories_come_from_that_topic_in_proportion():
    frame = _frame(
        [
            ("Area and Perimeter", 40, [UNIT, UNIT, ARITH]),
            ("Area and Perimeter", 40, [UNIT, ARITH]),
            ("Area and Perimeter", 40, [UNIT, METHOD]),  # third-most, left out
        ]
    )
    targets, _, _ = targeted.build_targets(frame, total=5)

    by_error = {t.error_type: t.count for t in targets}
    assert set(by_error) == {ErrorType.UNIT_ERROR, ErrorType.ARITHMETIC_ERROR}
    assert by_error[ErrorType.UNIT_ERROR] > by_error[ErrorType.ARITHMETIC_ERROR]


def test_method_and_concept_errors_are_drilled_a_level_lower():
    frame = _frame(
        [
            ("Linear Equations", 70, [CONCEPT, CONCEPT]),
            ("Linear Equations", 70, [ARITH, ARITH]),
        ]
    )
    targets, _, _ = targeted.build_targets(frame, total=4)

    level = {t.error_type: t.difficulty for t in targets}
    assert level[ErrorType.ARITHMETIC_ERROR] == "Core"
    assert level[ErrorType.CONCEPTUAL_ERROR] == "Foundation"
    concept = next(t for t in targets if t.error_type is ErrorType.CONCEPTUAL_ERROR)
    assert "rather than Core" in concept.reason


@pytest.mark.parametrize(
    "average, expected", [(10, "Foundation"), (54.9, "Foundation"), (55, "Core"), (80, "Extension")]
)
def test_difficulty_follows_the_topic_average(average, expected):
    assert targeted.difficulty_for(average, ErrorType.ARITHMETIC_ERROR) == expected


def test_foundation_does_not_step_below_foundation():
    assert targeted.difficulty_for(10, ErrorType.INCORRECT_METHOD) == "Foundation"


def test_a_topic_with_no_errors_borrows_the_most_common_error_elsewhere():
    frame = _frame([("Percentages", 30, []), ("Ratio and Proportion", 80, [UNIT, UNIT])])
    targets, _, _ = targeted.build_targets(frame, total=4, max_topics=1)

    assert {t.error_type for t in targets} == {ErrorType.UNIT_ERROR}
    assert "most common error elsewhere" in targets[0].reason


def test_no_errors_anywhere_falls_back_to_showing_working():
    targets, _, _ = targeted.build_targets(_frame([("Percentages", 50, [])]), total=2)
    assert [t.error_type for t in targets] == [targeted.DEFAULT_FOCUS]
    assert "showing full working" in targets[0].reason


def test_secure_topics_are_skipped_while_anything_is_weaker():
    frame = _frame([("Percentages", 95, [ARITH]), ("Linear Equations", 60, [ARITH])])
    targets, _, _ = targeted.build_targets(frame, total=4)
    assert {t.topic for t in targets} == {"Linear Equations"}


def test_when_everything_is_secure_the_weakest_is_stretched():
    frame = _frame([("Percentages", 95, []), ("Linear Equations", 90, [])])
    targets, _, _ = targeted.build_targets(frame, total=3)
    assert {t.topic for t in targets} == {"Linear Equations"}
    assert {t.difficulty for t in targets} == {"Extension"}


def test_topics_without_templates_are_reported_not_invented():
    frame = _frame([("Photosynthesis", 10, [CONCEPT]), ("Percentage change", 40, [ARITH])])
    plan = targeted.generate_targeted_practice(frame, total=3)

    assert plan.unsupported_topics == ["Photosynthesis"]
    assert {i.question.topic for i in plan.items} == {"Percentages"}
    assert plan.evidence[0].source_topics == ["Percentage change"]


def test_no_results_means_no_practice():
    plan = targeted.generate_targeted_practice(_frame([]))
    assert plan.is_empty and not plan.targets


@pytest.mark.parametrize("total", [1, 2, 3, 6, 10])
def test_the_requested_total_is_delivered_and_numbered(total):
    frame = _frame(
        [
            ("Percentages", 20, [ARITH, UNIT]),
            ("Linear Equations", 50, [METHOD]),
            ("Area and Perimeter", 60, [UNIT]),
            ("Ratio and Proportion", 70, [ARITH]),
        ]
    )
    plan = targeted.generate_targeted_practice(frame, total=total)
    assert len(plan.items) == total
    assert [i.question.number for i in plan.items] == list(range(1, total + 1))
    assert len({i.question.question_text for i in plan.items}) == total, "no repeats"


def test_every_item_explains_why_it_was_chosen():
    frame = _frame([("Percentages", 25, [UNIT]), ("Percentages", 35, [UNIT])])
    plan = targeted.generate_targeted_practice(frame, total=3, whose="S-1102's")

    for item in plan.items:
        assert "Percentages is S-1102's weakest topic (30% across 2 graded answers)" in item.reason
        assert "Unit Error came up 2 times" in item.reason


def test_targeted_practice_is_deterministic():
    frame = _frame([("Percentages", 25, [UNIT]), ("Linear Equations", 45, [ARITH])])
    first = targeted.generate_targeted_practice(frame, total=6)
    second = targeted.generate_targeted_practice(frame, total=6)
    assert [i.question.question_text for i in first.items] == [
        i.question.question_text for i in second.items
    ]


def test_seeded_student_is_targeted_on_their_own_weakest_topic(seed):
    assessments, submissions, results, _ = seed
    frame = analytics.student_dataframe("usr_s03", results, assessments, submissions)
    plan = targeted.generate_targeted_practice(frame)

    weakest = analytics.weakest_topics(frame, limit=1)[0]
    assert plan.items[0].question.topic == weakest
    assert len(plan.items) == targeted.DEFAULT_TOTAL


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def _page_as(user_id: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.session_state["current_user_id"] = user_id
    at.session_state["entered_demo"] = True
    at.run()
    at.switch_page(PRACTICE_PAGE)
    at.run()
    assert not at.exception, at.exception
    return at


def _markdown(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def test_a_student_gets_practice_from_their_own_results():
    at = _page_as("usr_s03")

    mode = [r for r in at.radio if r.label == "How should the questions be chosen?"][0]
    assert mode.value == targeted_mode()
    text = _markdown(at)
    assert text.count("Why this question:") == targeted.DEFAULT_TOTAL
    assert "is your weakest topic" in text
    assert "S-11" not in text, "a student must not see other students' codes"


def test_changing_the_count_changes_the_practice():
    at = _page_as("usr_s03")
    [n for n in at.number_input if n.label == "Number of questions"][0].set_value(3)
    at.run()
    assert not at.exception
    assert _markdown(at).count("Why this question:") == 3


def test_a_teacher_can_target_one_student():
    at = _page_as("usr_teacher01")
    assert "the class's weakest topic" in _markdown(at)

    picker = [s for s in at.selectbox if s.label.startswith("Whose results")][0]
    picker.set_value("S-1103")
    at.run()
    assert not at.exception
    assert "S-1103's weakest topic" in _markdown(at)


def test_manual_mode_still_works():
    at = _page_as("usr_s03")
    [r for r in at.radio if r.label == "How should the questions be chosen?"][0].set_value(
        "Choose it yourself"
    )
    at.run()
    [b for b in at.button if b.label == "Generate practice questions"][0].click()
    at.run()
    assert not at.exception
    assert "Question 1." in _markdown(at)
    assert "Why this question:" not in _markdown(at)


def targeted_mode() -> str:
    return "From results"
