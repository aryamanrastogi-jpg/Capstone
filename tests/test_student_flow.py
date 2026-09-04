"""Tests for the student-facing half of the product.

Three things matter most here and each has a test:

  1. **An AI estimate is never an official mark.** A student self-uploading work
     gets useful feedback, but nothing that reads as a grade until a teacher
     signs it off.
  2. **Students cannot see each other's work.** Scoping happens in the service
     layer, not the page, so it holds no matter what a page does.
  3. **The app gives pointers, not answers.** It must not become a way of
     obtaining homework solutions.
"""

from __future__ import annotations

import pandas as pd
import pytest

from data.sample_data import build_sample_data
from models import (
    Assessment,
    AssessmentType,
    ErrorType,
    Question,
    ReviewStatus,
    Role,
    StudyCamp,
    Submission,
)
from services import analytics_service as analytics
from services import study_camp_service as camps
from services.grading_service import (
    apply_teacher_decision,
    grade_answer,
    grade_submission,
    student_safe_view,
)


@pytest.fixture
def seed():
    assessments, submissions, results, users = build_sample_data()
    return assessments, submissions, results, users


@pytest.fixture
def question() -> Question:
    return Question(
        id="q_units",
        question_text="A rectangle is 12 cm by 5 cm. Find the area.",
        model_answer="Area = 12 x 5 = 60 cm2.",
        marking_criteria="1 mark for the method, 1 mark for 60 cm2 with the unit.",
        max_marks=2,
    )


# ---------------------------------------------------------------------------
# 1. Estimates are not marks
# ---------------------------------------------------------------------------
def test_a_self_study_result_is_never_an_official_mark(question):
    result = grade_answer(question, "12 x 5 = 60 cm2", "sub_self")

    assert result.review_status is ReviewStatus.AWAITING_REVIEW
    assert result.final_score is None, "an AI estimate must not read as a real mark"
    assert not result.is_finalised


def test_a_teacher_decision_turns_an_estimate_into_a_mark(question):
    result = grade_answer(question, "12 x 5 = 60 cm2", "sub_self")
    apply_teacher_decision(result, ReviewStatus.APPROVED)

    assert result.is_finalised
    assert result.final_score == result.suggested_score


def test_student_frame_marks_estimates_as_unofficial(seed):
    assessments, submissions, results, _ = seed
    student_id = "usr_s01"
    frame = analytics.student_dataframe(student_id, results, assessments, submissions)

    assert not frame.empty
    assert "is_official" in frame
    # Everything the teacher has not finalised must be flagged as an estimate.
    unofficial = frame[~frame["is_official"]]
    assert (unofficial["final_score"].isna()).all()


def test_teacher_frame_still_excludes_estimates(seed):
    """The default view is unchanged: teachers only see finalised results."""
    assessments, submissions, results, _ = seed
    frame = analytics.results_dataframe(results, assessments, submissions)
    assert set(frame["review_status"]).issubset({"approved", "edited"})
    assert bool(frame["is_official"].all())


def test_flagged_results_are_excluded_from_the_student_view(seed):
    assessments, submissions, results, _ = seed
    frame = analytics.student_dataframe("usr_s03", results, assessments, submissions)
    assert "flagged" not in set(frame["review_status"])


# ---------------------------------------------------------------------------
# 2. One student cannot see another
# ---------------------------------------------------------------------------
def test_students_only_see_their_own_work(seed):
    assessments, submissions, results, users = seed
    students = [u for u in users if u.role is Role.STUDENT]
    assert len(students) >= 2

    first, second = students[0], students[1]
    frame_a = analytics.student_dataframe(first.id, results, assessments, submissions)
    frame_b = analytics.student_dataframe(second.id, results, assessments, submissions)

    assert not frame_a.empty and not frame_b.empty
    assert set(frame_a["student_id"]) == {first.id}
    assert set(frame_b["student_id"]) == {second.id}
    assert set(frame_a["submission_id"]).isdisjoint(set(frame_b["submission_id"]))


def test_an_unknown_student_sees_nothing(seed):
    assessments, submissions, results, _ = seed
    frame = analytics.student_dataframe("usr_nobody", results, assessments, submissions)
    assert frame.empty


# ---------------------------------------------------------------------------
# 3. Pointers, not answers
# ---------------------------------------------------------------------------
def test_student_view_never_reveals_the_model_answer(question):
    result = grade_answer(question, "I multiplied them and got 17", "sub_leak")
    view = student_safe_view(result, question)

    blob = " ".join(
        [*view["strengths"], *view["pointers"], *view["error_labels"]]
    ).lower()

    assert "60" not in blob, "the expected answer must not leak to the student"
    assert question.model_answer.lower() not in blob
    assert question.marking_criteria.lower() not in blob


def test_student_view_still_says_something_useful(question):
    result = grade_answer(question, "I multiplied them and got 17", "sub_leak")
    view = student_safe_view(result, question)

    assert view["strengths"], "a student should always get some encouragement"
    assert view["pointers"], "a student should always get a next step"
    assert view["question_text"] == question.question_text
    assert view["max_marks"] == question.max_marks


def test_student_view_reports_whether_the_score_is_an_estimate(question):
    result = grade_answer(question, "12 x 5 = 60 cm2", "sub_est")
    assert student_safe_view(result, question)["is_estimate"] is True

    apply_teacher_decision(result, ReviewStatus.APPROVED)
    assert student_safe_view(result, question)["is_estimate"] is False


def test_pointers_are_derived_from_the_detected_errors(question):
    result = grade_answer(question, "60", "sub_units")
    view = student_safe_view(result, question)
    assert any(e == ErrorType.UNIT_ERROR.label for e in view["error_labels"])
    assert any("unit" in p.lower() for p in view["pointers"])


# ---------------------------------------------------------------------------
# Longitudinal analysis
# ---------------------------------------------------------------------------
def test_topic_trend_has_a_row_per_topic_and_period(seed):
    assessments, submissions, results, _ = seed
    frame = analytics.student_dataframe("usr_s01", results, assessments, submissions)
    trend = analytics.topic_trend(frame)

    assert not trend.empty
    assert set(trend.columns) == {"period", "topic", "avg_percentage", "responses"}
    assert trend["avg_percentage"].between(0, 100).all()
    # The seed spans a term, so there must be more than one period.
    assert trend["period"].nunique() > 1


def test_overall_trend_collapses_topics(seed):
    assessments, submissions, results, _ = seed
    frame = analytics.student_dataframe("usr_s01", results, assessments, submissions)
    overall = analytics.overall_trend(frame)
    assert not overall.empty
    assert overall["period"].is_unique


def test_weakest_topics_are_ranked_worst_first(seed):
    assessments, submissions, results, _ = seed
    frame = analytics.student_dataframe("usr_s02", results, assessments, submissions)

    ranked = analytics.weakest_topics(frame, limit=3)
    performance = analytics.topic_performance(frame).set_index("topic")["avg_percentage"]

    assert ranked
    scores = [performance[t] for t in ranked]
    assert scores == sorted(scores), "weakest topics must come out worst first"


def test_weakest_topics_respects_the_ceiling(seed):
    assessments, submissions, results, _ = seed
    frame = analytics.student_dataframe("usr_s01", results, assessments, submissions)
    performance = analytics.topic_performance(frame).set_index("topic")["avg_percentage"]

    for topic in analytics.weakest_topics(frame, limit=5, ceiling=60.0):
        assert performance[topic] <= 60.0


def test_longitudinal_helpers_survive_an_empty_history():
    empty = analytics.student_dataframe("nobody", [], [], [])
    assert empty.empty
    assert analytics.topic_trend(empty).empty
    assert analytics.overall_trend(empty).empty
    assert analytics.weakest_topics(empty) == []
    assert analytics.topic_strength(empty).empty


def test_topic_strength_bands_every_topic(seed):
    assessments, submissions, results, _ = seed
    frame = analytics.student_dataframe("usr_s02", results, assessments, submissions)
    strength = analytics.topic_strength(frame)

    assert not strength.empty
    assert set(strength["band"]).issubset(
        {"Secure", "Developing", "Needs work", "Priority"}
    )


# ---------------------------------------------------------------------------
# Mark mismatches - the teacher's second pair of eyes
# ---------------------------------------------------------------------------
def test_mark_mismatch_is_flagged_when_the_ai_disagrees(seed):
    assessments, submissions, results, _ = seed
    mismatches = analytics.mark_mismatches(submissions, results, assessments)

    assert not mismatches.empty, "the seed includes deliberate mismatches"
    assert (mismatches["gap"].abs() >= 15.0).all()
    assert set(mismatches["direction"]).issubset({"AI scored higher", "AI scored lower"})


def test_agreement_is_not_reported_as_a_mismatch():
    question = Question(
        question_text="Solve 3x + 7 = 22.",
        model_answer="Subtract 7 to get 3x = 15, divide by 3 to get x = 5.",
        max_marks=3,
    )
    assessment = Assessment(
        id="as_m", title="T", curriculum="Cambridge IGCSE", grade_level=10,
        topic="Linear Equations", assessment_type=AssessmentType.HOMEWORK,
        questions=[question],
    )
    submission = Submission(
        id="sub_m", assessment_id="as_m", student_identifier="S-1", student_id="u1",
        submission_text="Subtract 7 so 3x = 15, divide by 3, x = 5.",
    )
    results = grade_submission(assessment.questions, submission.submission_text, submission.id)

    # Teacher agrees exactly with the AI - nothing to report.
    submission.teacher_awarded_score = results[0].suggested_score
    assert analytics.mark_mismatches([submission], results, [assessment]).empty


def test_submissions_without_a_teacher_mark_are_ignored(seed):
    assessments, submissions, results, _ = seed
    for submission in submissions:
        submission.teacher_awarded_score = None
    assert analytics.mark_mismatches(submissions, results, assessments).empty


# ---------------------------------------------------------------------------
# Study camps
# ---------------------------------------------------------------------------
@pytest.fixture
def student_frame(seed) -> pd.DataFrame:
    assessments, submissions, results, _ = seed
    return analytics.student_dataframe("usr_s02", results, assessments, submissions)


def test_camp_targets_the_weakest_topics(student_frame):
    camp = camps.build_camp("usr_s02", student_frame)
    suggested = camps.suggest_topics(student_frame)

    assert isinstance(camp, StudyCamp)
    assert camp.topics == suggested
    assert camp.sessions
    assert {s.topic for s in camp.sessions} == set(camp.topics)


def test_camp_baseline_is_fixed_at_creation(student_frame):
    camp = camps.build_camp("usr_s02", student_frame)
    original = camp.baseline_percentage

    camps.record_session_result(camp, 1, len(camp.sessions[0].questions))
    assert camp.baseline_percentage == original, "the starting point must not move"
    assert camp.latest_percentage == 100.0
    assert camp.improvement == round(100.0 - original, 1)


def test_camp_progress_tracks_completion(student_frame):
    camp = camps.build_camp("usr_s02", student_frame, duration_days=4)
    assert camp.progress == 0.0
    assert not camp.is_complete

    for day in range(1, 5):
        camps.record_session_result(camp, day, 2)
    assert camp.progress == 1.0
    assert camp.is_complete


def test_camp_sessions_carry_questions_and_hints(student_frame):
    camp = camps.build_camp("usr_s02", student_frame, duration_days=3)
    for session in camp.sessions:
        assert session.questions
        assert len(session.method_hints) == len(session.questions)
        assert all("{" not in q for q in session.questions)


def test_camp_duration_is_clamped(student_frame):
    short = camps.build_camp("usr_s02", student_frame, duration_days=1)
    long = camps.build_camp("usr_s02", student_frame, duration_days=99)
    assert len(short.sessions) == camps.MIN_DURATION_DAYS
    assert len(long.sessions) == camps.MAX_DURATION_DAYS


def test_camp_difficulty_follows_the_baseline():
    assert camps.difficulty_for(30) == "Foundation"
    assert camps.difficulty_for(60) == "Core"
    assert camps.difficulty_for(75) == "Core"
    assert camps.difficulty_for(90) == "Extension"


def test_camp_cannot_be_built_without_history():
    empty = analytics.student_dataframe("nobody", [], [], [])
    with pytest.raises(ValueError, match="not enough marked work"):
        camps.build_camp("nobody", empty)


def test_recording_an_impossible_score_is_rejected(student_frame):
    camp = camps.build_camp("usr_s02", student_frame, duration_days=3)
    with pytest.raises(ValueError):
        camps.record_session_result(camp, 1, 99)
    with pytest.raises(ValueError):
        camps.record_session_result(camp, 99, 1)


def test_a_session_can_be_reopened(student_frame):
    camp = camps.build_camp("usr_s02", student_frame, duration_days=3)
    camps.record_session_result(camp, 1, 3)
    assert camp.get_session(1).completed

    camps.reopen_session(camp, 1)
    assert not camp.get_session(1).completed
    assert camp.get_session(1).score is None
    assert camp.latest_percentage is None


def test_camps_only_offer_topics_that_have_practice_templates(student_frame):
    supported = set(camps.available_topics_for(student_frame))
    camp = camps.build_camp("usr_s02", student_frame)
    assert set(camp.topics).issubset(supported)


# ---------------------------------------------------------------------------
# Seed data shape
# ---------------------------------------------------------------------------
def test_seed_spans_a_term(seed):
    _, submissions, _, _ = seed
    dates = sorted(s.submitted_at for s in submissions)
    assert (dates[-1] - dates[0]).days > 60, "the seed must cover enough time to trend"


def test_seed_users_are_anonymous(seed):
    _, _, _, users = seed
    for user in users:
        if user.role is Role.STUDENT:
            assert user.display_name.startswith("S-")
    assert any(u.role is Role.TEACHER for u in users)


def test_every_student_submission_is_linked_to_an_account(seed):
    _, submissions, _, users = seed
    known = {u.id for u in users}
    for submission in submissions:
        assert submission.student_id in known


def test_seed_gives_every_student_some_history(seed):
    assessments, submissions, results, users = seed
    for student in [u for u in users if u.role is Role.STUDENT]:
        frame = analytics.student_dataframe(
            student.id, results, assessments, submissions
        )
        assert not frame.empty, f"{student.display_name} has no history to show"
