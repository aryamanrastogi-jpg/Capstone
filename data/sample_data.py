"""Anonymised sample data seeded on first launch.

Everything here is synthetic. Students are referred to only by anonymous codes
(S-7101, S-8204, ...) - no real names, no identifying information.

The dataset is deliberately mixed: some submissions are already reviewed (so
Analytics has something to show), some are awaiting review (so Review Grading
has work to do), and one is flagged.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple

from models import (
    Assessment,
    GradingResult,
    Question,
    ReviewStatus,
    Submission,
    SubmissionStatus,
    Subject,
)
from services.grading_service import grade_submission

_NOW = datetime(2026, 9, 1, 9, 0)


def _build_assessments() -> List[Assessment]:
    linear = Assessment(
        id="as_linear01",
        title="Linear Equations - Class Test 1",
        subject=Subject.MATHEMATICS,
        curriculum="CBSE",
        grade_level=8,
        topic="Linear Equations",
        created_at=_NOW - timedelta(days=12),
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
    )

    area = Assessment(
        id="as_area01",
        title="Area and Perimeter - Practice Quiz",
        subject=Subject.MATHEMATICS,
        curriculum="CBSE",
        grade_level=7,
        topic="Area and Perimeter",
        created_at=_NOW - timedelta(days=6),
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
    )

    ratio = Assessment(
        id="as_ratio01",
        title="Ratio and Proportion - Homework Check",
        subject=Subject.MATHEMATICS,
        curriculum="Cambridge IGCSE",
        grade_level=9,
        topic="Ratio and Proportion",
        created_at=_NOW - timedelta(days=2),
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
    )

    return [linear, area, ratio]


# (assessment_id, student code, response text, days ago, review plan)
# review plan: "approve" | "edit" | "flag" | "pending"
_SAMPLE_RESPONSES: List[Tuple[str, str, str, int, str]] = [
    (
        "as_linear01",
        "S-8201",
        "Q1: 3x + 7 = 22. Subtract 7 from both sides so 3x = 15. Divide both sides "
        "by 3, x = 5.\n"
        "Q2: Let the number be n. 4n - 6 = 26. Add 6 to both sides, 4n = 32. "
        "Divide by 4, n = 8.",
        10,
        "approve",
    ),
    (
        "as_linear01",
        "S-8202",
        "Q1: 3x + 7 = 22 so 3x = 29 and x = 9.67.\n"
        "Q2: I multiplied 26 by 4 and got 104 then subtracted 6 to get 98.",
        10,
        "edit",
    ),
    (
        "as_linear01",
        "S-8203",
        "Q1: x = 5\nQ2: n = 8",
        10,
        "edit",
    ),
    (
        "as_linear01",
        "S-8204",
        "Q1: Subtract 7 from both sides, 3x = 15, then divide by 3 so x = 5.\n"
        "Q2: Let the number be n. 4n - 6 = 26, so 4n = 32 and n = 9.",
        9,
        "pending",
    ),
    (
        "as_area01",
        "S-7101",
        "Area = length x breadth = 12 x 5 = 60 cm2. Perimeter = 2 x (12 + 5) = 34 cm.\n"
        "Triangle: area = 1/2 x base x height = 1/2 x 9 x 6 = 27 cm2.",
        5,
        "approve",
    ),
    (
        "as_area01",
        "S-7102",
        "Area = 12 x 5 = 60. Perimeter = 12 + 5 = 17.\n"
        "Triangle area = 9 x 6 = 54.",
        5,
        "edit",
    ),
    (
        "as_area01",
        "S-7103",
        "I think you multiply the sides together but I was not sure which formula to "
        "use so I added them instead.",
        4,
        "flag",
    ),
    (
        "as_area01",
        "S-7104",
        "Rectangle: area = 12 x 5 = 60 cm2, perimeter = 2 x (12 + 5) = 34 cm.\n"
        "Triangle: I used the formula 1/2 x base x height = 1/2 x 9 x 6 = 27.",
        4,
        "pending",
    ),
    (
        "as_ratio01",
        "S-9301",
        "Total parts = 2 + 3 = 5. One part = 45 / 5 = 9. So the shares are "
        "2 x 9 = 18 and 3 x 9 = 27.",
        1,
        "pending",
    ),
    (
        "as_ratio01",
        "S-9302",
        "45 divided by 2 is 22.5 and 45 divided by 3 is 15.",
        1,
        "pending",
    ),
]


def build_sample_data() -> Tuple[List[Assessment], List[Submission], List[GradingResult]]:
    """Build the seeded demo dataset.

    Grading results are produced by the same mock grader the app uses, then a
    teacher review decision is applied on top - so the demo data is consistent
    with what a teacher would see live.
    """
    assessments = _build_assessments()
    by_id = {a.id: a for a in assessments}

    submissions: List[Submission] = []
    results: List[GradingResult] = []

    for index, (assessment_id, code, text, days_ago, plan) in enumerate(_SAMPLE_RESPONSES):
        assessment = by_id[assessment_id]
        submission = Submission(
            id=f"sub_demo{index:02d}",
            assessment_id=assessment_id,
            student_identifier=code,
            submission_text=text,
            uploaded_filename=None,
            submitted_at=_NOW - timedelta(days=days_ago, hours=index),
            status=SubmissionStatus.PENDING,
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

    return assessments, submissions, results


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
