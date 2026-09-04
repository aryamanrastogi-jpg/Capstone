"""Anonymised sample data seeded on first launch.

Everything here is synthetic. Students are referred to only by anonymous codes
(S-7101, S-8204, ...) - no real names, no identifying information.

The dataset spans a term rather than a single week, because the point of the
product is the trend: which topics a student is improving at and which are
stuck. A handful of submissions from one day would make the progress charts
look broken.

Shape of the seed:
  * 4 students on one teacher's roster, with different profiles
  * 6 assessments across 4 topics and 3 assessment types
  * ~12 weeks of submissions, oldest to newest
  * a mix of reviewed, awaiting-review and flagged results
  * two submissions where the teacher's recorded mark disagrees with the AI,
    so the mismatch panel has something to show
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from models import (
    Assessment,
    AssessmentType,
    GradingResult,
    Question,
    ReviewStatus,
    Role,
    Subject,
    Submission,
    SubmissionStatus,
    User,
)
from services.grading_service import grade_submission

_NOW = datetime(2026, 9, 1, 9, 0)
TEACHER_ID = "usr_teacher01"

# Whose account the demo opens on. S-1102 starts weak and improves over the
# term, so every student page has something substantive to show on launch.
DEMO_STUDENT_ID = "usr_s02"


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------
def _build_users() -> List[User]:
    teacher = User(
        id=TEACHER_ID,
        display_name="Ms. R. Kapoor",
        role=Role.TEACHER,
    )
    students = [
        User(id="usr_s01", display_name="S-1101", role=Role.STUDENT,
             teacher_id=TEACHER_ID, year_group=10),
        User(id="usr_s02", display_name="S-1102", role=Role.STUDENT,
             teacher_id=TEACHER_ID, year_group=10),
        User(id="usr_s03", display_name="S-1103", role=Role.STUDENT,
             teacher_id=TEACHER_ID, year_group=10),
        User(id="usr_s04", display_name="S-1104", role=Role.STUDENT,
             teacher_id=TEACHER_ID, year_group=10),
    ]
    return [teacher, *students]


# --------------------------------------------------------------------------
# Assessments
# --------------------------------------------------------------------------
def _build_assessments() -> List[Assessment]:
    return [
        Assessment(
            id="as_linear01",
            title="Linear Equations - Homework 3",
            subject=Subject.MATHEMATICS,
            curriculum="Cambridge IGCSE",
            grade_level=10,
            topic="Linear Equations",
            assessment_type=AssessmentType.HOMEWORK,
            created_at=_NOW - timedelta(weeks=11),
            questions=[
                Question(
                    id="q_lin_1",
                    question_text="Solve for x: 3x + 7 = 22. Show each step of your working.",
                    model_answer=(
                        "Subtract 7 from both sides to get 3x = 15. "
                        "Divide both sides by 3 to get x = 5."
                    ),
                    marking_criteria=(
                        "1 mark for subtracting 7 from both sides. "
                        "1 mark for dividing by 3. 1 mark for the correct value x = 5."
                    ),
                    max_marks=3,
                ),
                Question(
                    id="q_lin_2",
                    question_text=(
                        "A number is multiplied by 4 and then 6 is subtracted. "
                        "The result is 26. Form an equation and solve it."
                    ),
                    model_answer=(
                        "Let the number be n. The equation is 4n - 6 = 26. "
                        "Add 6 to both sides to get 4n = 32, then divide by 4 to get n = 8."
                    ),
                    marking_criteria=(
                        "1 mark for forming the correct equation. "
                        "2 marks for solving it correctly with working. "
                        "1 mark for stating n = 8."
                    ),
                    max_marks=4,
                ),
            ],
        ),
        Assessment(
            id="as_area01",
            title="Area and Perimeter - Class Exercise",
            subject=Subject.MATHEMATICS,
            curriculum="Cambridge IGCSE",
            grade_level=10,
            topic="Area and Perimeter",
            assessment_type=AssessmentType.EXERCISE,
            created_at=_NOW - timedelta(weeks=9),
            questions=[
                Question(
                    id="q_area_1",
                    question_text=(
                        "A rectangle measures 12 cm by 5 cm. "
                        "Calculate its area and its perimeter. Include units."
                    ),
                    model_answer=(
                        "Area = length x breadth = 12 x 5 = 60 cm2. "
                        "Perimeter = 2 x (12 + 5) = 34 cm."
                    ),
                    marking_criteria=(
                        "1 mark for the area formula, 1 mark for 60 cm2, "
                        "1 mark for the perimeter formula, 1 mark for 34 cm. "
                        "Units are required for full marks."
                    ),
                    max_marks=4,
                ),
                Question(
                    id="q_area_2",
                    question_text=(
                        "A triangle has base 9 cm and height 6 cm. "
                        "Find its area and name the formula you used."
                    ),
                    model_answer=(
                        "Area of a triangle = 1/2 x base x height. "
                        "So area = 1/2 x 9 x 6 = 27 cm2."
                    ),
                    marking_criteria=(
                        "1 mark for naming the formula, 1 mark for substituting correctly, "
                        "1 mark for 27 cm2 with the unit."
                    ),
                    max_marks=3,
                ),
            ],
        ),
        Assessment(
            id="as_ratio01",
            title="Ratio and Proportion - Homework 5",
            subject=Subject.MATHEMATICS,
            curriculum="Cambridge IGCSE",
            grade_level=10,
            topic="Ratio and Proportion",
            assessment_type=AssessmentType.HOMEWORK,
            created_at=_NOW - timedelta(weeks=7),
            questions=[
                Question(
                    id="q_ratio_1",
                    question_text="Share 45 counters in the ratio 2 : 3. Show your working.",
                    model_answer=(
                        "The total number of parts is 2 + 3 = 5. "
                        "One part is 45 divided by 5 = 9. "
                        "So the shares are 2 x 9 = 18 and 3 x 9 = 27."
                    ),
                    marking_criteria=(
                        "1 mark for the total parts, 1 mark for the value of one part, "
                        "1 mark for both shares."
                    ),
                    max_marks=3,
                ),
            ],
        ),
        Assessment(
            id="as_pct01",
            title="Percentages - Class Exercise",
            subject=Subject.MATHEMATICS,
            curriculum="Cambridge IGCSE",
            grade_level=10,
            topic="Percentages",
            assessment_type=AssessmentType.EXERCISE,
            created_at=_NOW - timedelta(weeks=5),
            questions=[
                Question(
                    id="q_pct_1",
                    question_text="Find 20% of 350. Show your working.",
                    model_answer=(
                        "Divide 350 by 100 to get 3.5, then multiply by 20 to get 70."
                    ),
                    marking_criteria="1 mark for the method, 1 mark for 70.",
                    max_marks=2,
                ),
                Question(
                    id="q_pct_2",
                    question_text=(
                        "An item costing 240 rupees is reduced by 25%. "
                        "Work out the new price, with units."
                    ),
                    model_answer=(
                        "25% of 240 is 60 rupees, so the new price is 180 rupees."
                    ),
                    marking_criteria=(
                        "1 mark for finding the reduction, 1 mark for 180 rupees "
                        "with the unit."
                    ),
                    max_marks=2,
                ),
            ],
        ),
        Assessment(
            id="as_linear02",
            title="Linear Equations - Retest",
            subject=Subject.MATHEMATICS,
            curriculum="Cambridge IGCSE",
            grade_level=10,
            topic="Linear Equations",
            assessment_type=AssessmentType.EXERCISE,
            created_at=_NOW - timedelta(weeks=3),
            questions=[
                Question(
                    id="q_lin2_1",
                    question_text="Solve for x: 5x + 8 = 43. Show every step.",
                    model_answer=(
                        "Subtract 8 from both sides to get 5x = 35, "
                        "then divide by 5 to get x = 7."
                    ),
                    marking_criteria=(
                        "1 mark for subtracting 8, 1 mark for dividing by 5, "
                        "1 mark for x = 7."
                    ),
                    max_marks=3,
                ),
            ],
        ),
        Assessment(
            id="as_mock01",
            title="Mathematics - Mid-term Mock Exam",
            subject=Subject.MATHEMATICS,
            curriculum="Cambridge IGCSE",
            grade_level=10,
            topic="Area and Perimeter",
            assessment_type=AssessmentType.MOCK_EXAM,
            created_at=_NOW - timedelta(weeks=1),
            questions=[
                Question(
                    id="q_mock_1",
                    question_text=(
                        "A rectangular garden measures 15 m by 8 m. "
                        "Find the area and the perimeter, with units."
                    ),
                    model_answer=(
                        "Area = 15 x 8 = 120 m2. Perimeter = 2 x (15 + 8) = 46 m."
                    ),
                    marking_criteria=(
                        "1 mark for each formula, 1 mark for each value with its unit."
                    ),
                    max_marks=4,
                ),
            ],
        ),
    ]


# --------------------------------------------------------------------------
# Responses
#
# (assessment_id, user_id, code, response, weeks ago, review plan,
#  teacher mark or None)
# review plan: "approve" | "edit" | "flag" | "pending"
# --------------------------------------------------------------------------
_SAMPLE_RESPONSES: List[Tuple[str, str, str, str, int, str, float | None]] = [
    # --- Week 11: Linear equations homework -------------------------------
    (
        "as_linear01", "usr_s01", "S-1101",
        "Q1: 3x + 7 = 22. Subtract 7 from both sides so 3x = 15. Divide both "
        "sides by 3, x = 5.\n"
        "Q2: Let the number be n. 4n - 6 = 26. Add 6 to both sides, 4n = 32. "
        "Divide by 4, n = 8.",
        11, "approve", None,
    ),
    (
        "as_linear01", "usr_s02", "S-1102",
        "Q1: 3x + 7 = 22 so 3x = 29 and x = 9.67.\n"
        "Q2: I multiplied 26 by 4 and got 104 then subtracted 6 to get 98.",
        11, "edit", None,
    ),
    (
        "as_linear01", "usr_s03", "S-1103",
        "Q1: x = 5\nQ2: n = 8",
        11, "edit", None,
    ),
    (
        "as_linear01", "usr_s04", "S-1104",
        "Q1: Subtract 7 from both sides, 3x = 15, then divide by 3 so x = 5.\n"
        "Q2: Let the number be n. 4n - 6 = 26, so 4n = 32 and n = 9.",
        11, "approve", None,
    ),
    # --- Week 9: Area and perimeter exercise ------------------------------
    (
        "as_area01", "usr_s01", "S-1101",
        "Area = length x breadth = 12 x 5 = 60 cm2. Perimeter = 2 x (12 + 5) = 34 cm.\n"
        "Triangle: area = 1/2 x base x height = 1/2 x 9 x 6 = 27 cm2.",
        9, "approve", None,
    ),
    (
        "as_area01", "usr_s02", "S-1102",
        "Area = 12 x 5 = 60. Perimeter = 12 + 5 = 17.\n"
        "Triangle area = 9 x 6 = 54.",
        9, "edit", None,
    ),
    (
        "as_area01", "usr_s03", "S-1103",
        "I think you multiply the sides together but I was not sure which formula "
        "to use so I added them instead.",
        9, "flag", None,
    ),
    (
        "as_area01", "usr_s04", "S-1104",
        "Rectangle: area = 12 x 5 = 60 cm2, perimeter = 2 x (12 + 5) = 34 cm.\n"
        "Triangle: I used the formula 1/2 x base x height = 1/2 x 9 x 6 = 27 cm2.",
        9, "approve", None,
    ),
    # --- Week 7: Ratio homework -------------------------------------------
    (
        "as_ratio01", "usr_s01", "S-1101",
        "Total parts = 2 + 3 = 5. One part = 45 / 5 = 9. So the shares are "
        "2 x 9 = 18 and 3 x 9 = 27.",
        7, "approve", None,
    ),
    (
        "as_ratio01", "usr_s02", "S-1102",
        "45 divided by 2 is 22.5 and 45 divided by 3 is 15.",
        7, "edit", None,
    ),
    (
        "as_ratio01", "usr_s03", "S-1103",
        "Total parts = 2 + 3 = 5, one part = 9, shares are 18 and 27.",
        7, "approve", None,
    ),
    (
        # Teacher recorded 1/3 but the work looks stronger than that - this is
        # the mismatch the teacher panel should surface.
        "as_ratio01", "usr_s04", "S-1104",
        "The total number of parts is 2 + 3 = 5. One part is 45 divided by 5 = 9. "
        "So the shares are 2 x 9 = 18 and 3 x 9 = 27.",
        7, "pending", 1.0,
    ),
    # --- Week 5: Percentages exercise -------------------------------------
    (
        "as_pct01", "usr_s01", "S-1101",
        "350 / 100 = 3.5, then 3.5 x 20 = 70.\n"
        "25% of 240 = 60 rupees, so the new price is 240 - 60 = 180 rupees.",
        5, "approve", None,
    ),
    (
        "as_pct01", "usr_s02", "S-1102",
        "20% of 350 is 70.\n25% off 240 is 180.",
        5, "edit", None,
    ),
    (
        "as_pct01", "usr_s03", "S-1103",
        "I divided 350 by 20 and got 17.5.\nFor the second one I got 215.",
        5, "pending", None,
    ),
    (
        "as_pct01", "usr_s04", "S-1104",
        "Divide 350 by 100 to get 3.5, multiply by 20 to get 70.\n"
        "25% of 240 is 60 rupees so the new price is 180 rupees.",
        5, "approve", None,
    ),
    # --- Week 3: Linear equations retest (S-1102 improving) ---------------
    (
        "as_linear02", "usr_s01", "S-1101",
        "Subtract 8 from both sides to get 5x = 35, then divide by 5 so x = 7.",
        3, "approve", None,
    ),
    (
        "as_linear02", "usr_s02", "S-1102",
        "Subtract 8 from both sides, 5x = 35. Divide both sides by 5, x = 7.",
        3, "approve", None,
    ),
    (
        "as_linear02", "usr_s03", "S-1103",
        "5x = 43 - 8 = 35 so x = 7.",
        3, "pending", None,
    ),
    (
        "as_linear02", "usr_s04", "S-1104",
        "5x + 8 = 43, so 5x = 35 and x = 7.",
        3, "approve", None,
    ),
    # --- Week 1: Mock exam ------------------------------------------------
    (
        "as_mock01", "usr_s01", "S-1101",
        "Area = 15 x 8 = 120 m2. Perimeter = 2 x (15 + 8) = 46 m.",
        1, "approve", None,
    ),
    (
        # Correct area, perimeter missing. The teacher gave credit for the part
        # that was right; the rule-based grader reads it lower. The other
        # direction of mismatch, so the panel shows both - and a fair reminder
        # that the AI is the one more likely to be wrong here.
        "as_mock01", "usr_s02", "S-1102",
        "Area = 15 x 8 = 120 m2.",
        1, "pending", 3.0,
    ),
    (
        # Method is wrong throughout (added instead of multiplied), but the
        # recorded mark is generous. The AI reads it much lower - the other
        # direction of mismatch. The panel does not say who is right; it says
        # the two readings disagree enough to be worth a second look.
        "as_mock01", "usr_s03", "S-1103",
        "Area = 15 + 8 = 23. Perimeter = 15 x 8 = 120.",
        1, "pending", 3.0,
    ),
    (
        "as_mock01", "usr_s04", "S-1104",
        "Area = 15 x 8 = 120 m2 and perimeter = 2 x (15 + 8) = 46 m.",
        1, "pending", None,
    ),
]


def build_sample_data() -> Tuple[
    List[Assessment], List[Submission], List[GradingResult], List[User]
]:
    """Build the seeded demo dataset.

    Grading results are produced by the same mock grader the app uses, then a
    teacher review decision is applied on top - so the demo data is consistent
    with what a teacher would see live.
    """
    users = _build_users()
    assessments = _build_assessments()
    by_id: Dict[str, Assessment] = {a.id: a for a in assessments}

    submissions: List[Submission] = []
    results: List[GradingResult] = []

    for index, entry in enumerate(_SAMPLE_RESPONSES):
        assessment_id, user_id, code, text, weeks_ago, plan, teacher_mark = entry
        assessment = by_id[assessment_id]

        submission = Submission(
            id=f"sub_demo{index:02d}",
            assessment_id=assessment_id,
            student_identifier=code,
            student_id=user_id,
            submission_text=text,
            uploaded_filename=None,
            submitted_at=_NOW - timedelta(weeks=weeks_ago, hours=index),
            status=SubmissionStatus.PENDING,
            is_self_study=False,
            teacher_awarded_score=teacher_mark,
        )

        graded = grade_submission(assessment.questions, text, submission.id)
        for result in graded:
            _apply_review_plan(result, plan)

        if all(result.is_finalised for result in graded):
            submission.status = SubmissionStatus.REVIEWED
        else:
            # Awaiting review, or holding a flagged result the teacher parked.
            submission.status = SubmissionStatus.GRADED

        submissions.append(submission)
        results.extend(graded)

    return assessments, submissions, results, users


def _apply_review_plan(result: GradingResult, plan: str) -> None:
    """Simulate the teacher decision that would have been made on this result."""
    if plan == "approve":
        result.review_status = ReviewStatus.APPROVED
        result.teacher_approved_score = result.suggested_score
        result.teacher_approved_feedback = result.student_feedback
    elif plan == "edit":
        # Teachers typically nudge the AI score up by half a mark and soften
        # the wording; both stay within the mark bounds.
        adjusted = min(result.max_marks, result.suggested_score + 0.5)
        result.review_status = ReviewStatus.EDITED
        result.teacher_approved_score = adjusted
        result.teacher_approved_feedback = (
            result.student_feedback + " Come and see me if any of this is unclear."
        )
    elif plan == "flag":
        result.review_status = ReviewStatus.FLAGGED
        result.teacher_note = (
            (result.teacher_note or "")
            + " Flagged: the response may be off-topic; re-read before scoring."
        ).strip()
    # "pending" leaves the result untouched (awaiting_review).
