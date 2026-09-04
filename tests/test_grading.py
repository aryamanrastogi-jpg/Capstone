"""Tests for the mock grading service, document extraction and analytics."""

from __future__ import annotations

import pytest

from data.sample_data import build_sample_data
from models import ErrorType, GradingResult, Question, ReviewStatus
from services import analytics_service as analytics
from services import document_service
from services.grading_service import (
    apply_teacher_decision,
    grade_answer,
    grade_submission,
)
from services.practice_service import DIFFICULTIES, TOPICS, generate_practice_questions

STRONG_ANSWER = (
    "Subtract 7 from both sides so 3x = 15. Divide both sides by 3, so x = 5."
)
WEAK_ANSWER = "I think the answer is probably around twenty something."


@pytest.fixture
def question() -> Question:
    return Question(
        id="q_test_1",
        question_text="Solve for x: 3x + 7 = 22. Show your working.",
        model_answer="Subtract 7 from both sides to get 3x = 15, then divide by 3 to get x = 5.",
        marking_criteria="1 mark per correct step, 1 mark for x = 5.",
        max_marks=3,
    )


# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------
def test_mock_grader_returns_a_valid_structured_result(question):
    result = grade_answer(question, STRONG_ANSWER, "sub_test")

    assert isinstance(result, GradingResult)
    assert result.submission_id == "sub_test"
    assert result.question_id == question.id
    assert result.max_marks == question.max_marks
    assert 0 <= result.suggested_score <= question.max_marks
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.correct_elements, list)
    assert all(isinstance(item, str) for item in result.correct_elements)
    assert all(isinstance(e.error_type, ErrorType) for e in result.errors)
    assert result.student_feedback.strip()
    assert result.teacher_note.strip()


def test_ai_output_is_never_auto_approved(question):
    result = grade_answer(question, STRONG_ANSWER, "sub_test")
    assert result.review_status is ReviewStatus.AWAITING_REVIEW
    assert result.teacher_approved_score is None
    assert result.teacher_approved_feedback is None
    assert result.final_score is None
    assert not result.is_reviewed


def test_grading_is_deterministic(question):
    first = grade_answer(question, STRONG_ANSWER, "sub_test")
    second = grade_answer(question, STRONG_ANSWER, "sub_test")
    assert first.suggested_score == second.suggested_score
    assert first.confidence == second.confidence
    assert [e.error_type for e in first.errors] == [e.error_type for e in second.errors]


def test_suggested_score_never_exceeds_max_marks(question):
    for answer in [STRONG_ANSWER, WEAK_ANSWER, question.model_answer, "x=5", "?" * 500]:
        result = grade_answer(question, answer, "sub_test")
        assert 0 <= result.suggested_score <= question.max_marks


def test_a_close_answer_scores_higher_than_a_poor_one(question):
    strong = grade_answer(question, STRONG_ANSWER, "sub_a")
    weak = grade_answer(question, WEAK_ANSWER, "sub_b")
    assert strong.suggested_score > weak.suggested_score


def test_blank_answer_scores_zero_and_reports_an_incomplete_answer(question):
    result = grade_answer(question, "   ", "sub_blank")
    assert result.suggested_score == 0
    assert any(e.error_type is ErrorType.INCOMPLETE_ANSWER for e in result.errors)
    assert result.review_status is ReviewStatus.AWAITING_REVIEW


def test_missing_units_are_detected():
    unit_question = Question(
        question_text="A rectangle is 12 cm by 5 cm. Find its area.",
        model_answer="Area = 12 x 5 = 60 cm2.",
        marking_criteria="1 mark for the value, 1 mark for the unit.",
        max_marks=2,
    )
    result = grade_answer(unit_question, "60", "sub_units")
    assert any(e.error_type is ErrorType.UNIT_ERROR for e in result.errors)


def test_grade_submission_returns_one_result_per_question(question):
    second = Question(
        question_text="Solve 2y = 10.",
        model_answer="Divide both sides by 2 to get y = 5.",
        max_marks=2,
    )
    results = grade_submission([question, second], STRONG_ANSWER, "sub_multi")
    assert len(results) == 2
    assert {r.question_id for r in results} == {question.id, second.id}
    assert all(r.review_status is ReviewStatus.AWAITING_REVIEW for r in results)


# ---------------------------------------------------------------------------
# Document extraction
# ---------------------------------------------------------------------------
def test_txt_extraction_returns_the_text():
    payload = "Q1: x = 5 because 3x = 15.".encode("utf-8")
    result = document_service.extract_text("answer.txt", payload)
    assert result.success
    assert "3x = 15" in result.text


def test_unsupported_upload_format_is_rejected_by_extraction():
    result = document_service.extract_text("notes.docx", b"some bytes here")
    assert not result.success
    assert "Unsupported file type" in result.message


def test_pdf_without_a_text_layer_reports_a_clear_message():
    """An image-only PDF must be reported, never silently accepted as empty."""
    pymupdf = pytest.importorskip("pymupdf")
    document = pymupdf.open()
    document.new_page()  # a blank page carries no text layer
    payload = document.tobytes()
    document.close()

    result = document_service.extract_text("scan.pdf", payload)
    assert not result.success
    assert "handwritten or image-only" in result.message.lower()


def test_digital_pdf_text_is_extracted():
    pymupdf = pytest.importorskip("pymupdf")
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 100), "Q1: Subtract 7, divide by 3, so x = 5.")
    payload = document.tobytes()
    document.close()

    result = document_service.extract_text("typed.pdf", payload)
    assert result.success
    assert "x = 5" in result.text
    assert result.page_count == 1


# ---------------------------------------------------------------------------
# Sample data and analytics
# ---------------------------------------------------------------------------
def test_sample_data_is_consistent():
    assessments, submissions, results = build_sample_data()
    assert assessments and submissions and results

    assessment_ids = {a.id: a for a in assessments}
    for submission in submissions:
        assert submission.assessment_id in assessment_ids

    question_ids = {q.id for a in assessments for q in a.questions}
    submission_ids = {s.id for s in submissions}
    for result in results:
        assert result.question_id in question_ids
        assert result.submission_id in submission_ids
        assert 0 <= result.suggested_score <= result.max_marks
        if result.teacher_approved_score is not None:
            assert 0 <= result.teacher_approved_score <= result.max_marks


def test_sample_data_uses_anonymous_identifiers():
    _, submissions, _ = build_sample_data()
    for submission in submissions:
        assert submission.student_identifier.startswith("S-")


def test_sample_data_leaves_some_results_awaiting_review():
    _, _, results = build_sample_data()
    assert any(r.review_status is ReviewStatus.AWAITING_REVIEW for r in results)
    assert any(r.review_status is ReviewStatus.APPROVED for r in results)


def test_analytics_only_counts_reviewed_results():
    assessments, submissions, results = build_sample_data()
    frame = analytics.results_dataframe(results, assessments, submissions)
    assert not frame.empty
    assert set(frame["review_status"]).issubset({"approved", "edited"})


def test_analytics_handles_an_empty_dataset():
    frame = analytics.results_dataframe([], [], [])
    assert frame.empty
    assert analytics.average_percentage([]) is None
    assert analytics.acceptance_rate([]) is None
    assert analytics.error_frequency([]).empty
    assert analytics.question_difficulty(frame).empty
    assert analytics.topic_performance(frame).empty
    assert analytics.score_distribution(frame)["count"].sum() == 0


def test_acceptance_rate_is_a_percentage():
    _, _, results = build_sample_data()
    rate = analytics.acceptance_rate(results)
    assert rate is not None
    assert 0 <= rate <= 100


# ---------------------------------------------------------------------------
# Practice generator
# ---------------------------------------------------------------------------
def test_practice_generator_is_deterministic():
    first = generate_practice_questions(TOPICS[0], ErrorType.ARITHMETIC_ERROR, "Core", 3)
    second = generate_practice_questions(TOPICS[0], ErrorType.ARITHMETIC_ERROR, "Core", 3)
    assert [q.question_text for q in first] == [q.question_text for q in second]


@pytest.mark.parametrize("difficulty", DIFFICULTIES)
def test_practice_generator_returns_the_requested_count(difficulty):
    questions = generate_practice_questions(
        TOPICS[0], ErrorType.MISSING_WORKING, difficulty, 4
    )
    assert len(questions) == 4
    assert all(q.question_text.strip() for q in questions)
    assert all(q.method_hint.strip() for q in questions)


def test_practice_generator_rejects_an_unknown_topic():
    with pytest.raises(ValueError):
        generate_practice_questions("Astrophysics", ErrorType.UNIT_ERROR, "Core", 2)


# ---------------------------------------------------------------------------
# Teacher review decisions
# ---------------------------------------------------------------------------
def test_accepting_the_suggestion_marks_it_approved(question):
    result = grade_answer(question, STRONG_ANSWER, "sub_r1")
    apply_teacher_decision(result, ReviewStatus.APPROVED)

    assert result.review_status is ReviewStatus.APPROVED
    assert result.teacher_approved_score == result.suggested_score
    assert result.final_score == result.suggested_score
    assert result.is_reviewed


def test_changing_the_score_marks_it_edited(question):
    result = grade_answer(question, STRONG_ANSWER, "sub_r2")
    target = max(0.0, result.suggested_score - 1)
    apply_teacher_decision(result, ReviewStatus.EDITED, score=target)

    assert result.review_status is ReviewStatus.EDITED
    assert result.final_score == target


def test_an_edit_identical_to_the_suggestion_counts_as_approved(question):
    """Acceptance rate must not be skewed by a no-op 'edit'."""
    result = grade_answer(question, STRONG_ANSWER, "sub_r3")
    apply_teacher_decision(
        result,
        ReviewStatus.EDITED,
        score=result.suggested_score,
        feedback=result.student_feedback,
    )
    assert result.review_status is ReviewStatus.APPROVED


@pytest.mark.parametrize("attempted", [-5, 99])
def test_teacher_scores_are_clamped_into_the_mark_range(question, attempted):
    result = grade_answer(question, STRONG_ANSWER, "sub_r4")
    apply_teacher_decision(result, ReviewStatus.EDITED, score=attempted)
    assert 0 <= result.teacher_approved_score <= question.max_marks


def test_flagging_clears_any_approved_score(question):
    result = grade_answer(question, STRONG_ANSWER, "sub_r5")
    apply_teacher_decision(result, ReviewStatus.APPROVED)
    apply_teacher_decision(result, ReviewStatus.FLAGGED)

    assert result.review_status is ReviewStatus.FLAGGED
    assert result.teacher_approved_score is None
    assert result.final_score is None


def test_flagged_results_are_excluded_from_analytics(question):
    result = grade_answer(question, STRONG_ANSWER, "sub_r6")
    apply_teacher_decision(result, ReviewStatus.FLAGGED)
    assert analytics.approved_results([result]) == []
    assert analytics.average_percentage([result]) is None


# ---------------------------------------------------------------------------
# Scoring signal
# ---------------------------------------------------------------------------
def test_a_correct_symbolic_answer_scores_well_without_the_model_wording():
    """Maths answers are often pure symbols; numeric agreement must count."""
    percentage_question = Question(
        question_text="Find 20% of 350. Show your working.",
        model_answer="Divide 350 by 100 to get 3.5, then multiply by 20 to get 70.",
        marking_criteria="1 mark for the method, 1 mark for 70.",
        max_marks=2,
    )
    result = grade_answer(percentage_question, "350 / 100 = 3.5, then 3.5 x 20 = 70.", "sub_sym")

    assert result.suggested_score >= 1.5
    assert not any(e.error_type is ErrorType.CONCEPTUAL_ERROR for e in result.errors)


# ---------------------------------------------------------------------------
# Practice question quality
# ---------------------------------------------------------------------------
def test_generated_linear_equations_have_whole_number_solutions():
    """A generator that emits '36x + 36 = 21' is useless to a Grade 7 class."""
    import re

    for difficulty in DIFFICULTIES:
        questions = generate_practice_questions(
            "Linear Equations", ErrorType.ARITHMETIC_ERROR, difficulty, 10
        )
        for q in questions:
            match = re.search(r"(\d+)x \+ (\d+) = (\d+)", q.question_text)
            if not match:
                continue
            a, b, c = (int(g) for g in match.groups())
            assert (c - b) % a == 0, f"{q.question_text} has no integer solution"
            assert (c - b) // a > 0, f"{q.question_text} solves to a non-positive x"


def test_generated_ratio_questions_divide_exactly():
    import re

    for difficulty in DIFFICULTIES:
        for q in generate_practice_questions(
            "Ratio and Proportion", ErrorType.INCORRECT_METHOD, difficulty, 10
        ):
            match = re.search(r"Share (\d+) counters in the ratio (\d+) : (\d+)", q.question_text)
            if match:
                total, a, b = (int(g) for g in match.groups())
                assert total % (a + b) == 0, f"{q.question_text} does not divide exactly"

            match = re.search(r"If (\d+) pens cost (\d+) rupees", q.question_text)
            if match:
                count, cost = (int(g) for g in match.groups())
                assert cost % count == 0, f"{q.question_text} has a fractional unit cost"


def test_generated_percentage_questions_have_whole_answers():
    import re

    for difficulty in DIFFICULTIES:
        for q in generate_practice_questions(
            "Percentages", ErrorType.CONCEPTUAL_ERROR, difficulty, 10
        ):
            match = re.search(r"Find (\d+)% of (\d+)", q.question_text)
            if match:
                percent, amount = (int(g) for g in match.groups())
                assert (amount * percent) % 100 == 0, q.question_text


def test_generated_mean_questions_have_a_whole_mean():
    import re

    for difficulty in DIFFICULTIES:
        for q in generate_practice_questions(
            "Data Handling", ErrorType.ARITHMETIC_ERROR, difficulty, 10
        ):
            match = re.search(r"mean of these values: ([\d, ]+)\.", q.question_text)
            if match:
                values = [int(v) for v in match.group(1).split(",")]
                assert sum(values) % len(values) == 0, q.question_text


@pytest.mark.parametrize("topic", TOPICS)
def test_every_topic_generates_questions(topic):
    questions = generate_practice_questions(topic, ErrorType.MISSING_WORKING, "Core", 4)
    assert len(questions) == 4
    for q in questions:
        assert q.question_text.strip() and q.method_hint.strip()
        assert "{" not in q.question_text  # no unformatted placeholders
