"""Review Grading - the teacher approves, edits, or flags every AI suggestion.

Nothing on this page is final until a teacher acts on it. AI output is only ever
presented as a recommendation, and the approved score is stored separately from
the suggested score so the two can always be compared.
"""

from __future__ import annotations

import streamlit as st

from components.layout import ai_disclaimer, empty_state, page_header, privacy_notice
from components.navigation import goto
from components.status_badges import (
    confidence_badge,
    review_status_badge,
    review_status_label,
)
from models import GradingResult, ReviewStatus
from services import assessment_service as service
from services.grading_service import (
    MOCK_ENGINE_NAME,
    apply_teacher_decision,
    grade_submission,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _submission_label(submission_id: str, titles: dict) -> str:
    submission = service.get_submission(submission_id)
    if submission is None:
        return submission_id
    results = service.list_grading_results(submission_id)
    reviewed = sum(1 for r in results if r.is_reviewed)
    progress = f"{reviewed}/{len(results)} reviewed" if results else "not graded"
    title = titles.get(submission.assessment_id, "Unknown assessment")
    return f"{submission.student_identifier} · {title} · {progress}"


def _save_decision(
    result: GradingResult,
    score: float | None,
    feedback: str | None,
    status: ReviewStatus,
) -> None:
    """Record a teacher decision, then persist it."""
    apply_teacher_decision(result, status=status, score=score, feedback=feedback)
    service.save_grading_result(result)


page_header(
    "Review Grading",
    "Check every AI recommendation before it counts towards a student's result.",
    "Approve accepts the suggestion unchanged. Edit records your own score or wording. "
    "Flag parks the result for a second look without approving it.",
)

ai_disclaimer(f"Grading engine: {MOCK_ENGINE_NAME}.")

assessments = service.list_assessments()
submissions = service.list_submissions()

if not assessments:
    empty_state(
        "There are no assessments yet, so there is nothing to review.",
        "Create an assessment, then add some responses.",
        icon=":material/assignment_late:",
    )
    if st.button("Create an assessment", type="primary"):
        goto("Create Assessment")
    st.stop()

if not submissions:
    empty_state(
        "No responses have been submitted yet.",
        "Add a response on the Upload Responses page and it will appear here.",
        icon=":material/inbox:",
    )
    if st.button("Upload a response", type="primary"):
        goto("Upload Responses")
    st.stop()

# ---------------------------------------------------------------------------
# Pick a submission
# ---------------------------------------------------------------------------
titles = {a.id: a.title for a in assessments}

filter_col, sub_col = st.columns([1, 2])
with filter_col:
    only_pending = st.toggle(
        "Show only items awaiting review",
        value=True,
        help="Turn this off to revisit results you have already approved, edited or flagged.",
    )


def _has_pending(submission_id: str) -> bool:
    results = service.list_grading_results(submission_id)
    return (not results) or any(not r.is_reviewed for r in results)


candidates = [s for s in submissions if (not only_pending) or _has_pending(s.id)]

if not candidates:
    st.success(
        "Every submission has been reviewed. Turn off the filter above to look back "
        "over your decisions.",
        icon=":material/task_alt:",
    )
    st.stop()

with sub_col:
    selected_id = st.selectbox(
        "Submission",
        options=[s.id for s in candidates],
        format_func=lambda sid: _submission_label(sid, titles),
    )

submission = service.get_submission(selected_id)
if submission is None:
    st.error("That submission could not be found.", icon=":material/error:")
    st.stop()

assessment = service.get_assessment(submission.assessment_id)
if assessment is None:
    st.error(
        "The assessment for this submission no longer exists, so it cannot be reviewed.",
        icon=":material/error:",
    )
    st.stop()

# ---------------------------------------------------------------------------
# Ensure grading results exist
# ---------------------------------------------------------------------------
results = service.list_grading_results(submission.id)
if not results:
    st.info("This submission has not been graded yet.", icon=":material/info:")
    if st.button("Run mock grading", type="primary"):
        for result in grade_submission(
            assessment.questions, submission.submission_text, submission.id
        ):
            service.save_grading_result(result)
        st.rerun()
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# The student response
# ---------------------------------------------------------------------------
head_left, head_right = st.columns([3, 1])
with head_left:
    st.subheader(f"{submission.student_identifier} · {assessment.title}")
    st.caption(
        f"Submitted {submission.submitted_at.strftime('%d %b %Y, %H:%M')} · "
        f"Source: {submission.uploaded_filename or 'typed / pasted'}"
    )
with head_right:
    reviewed = sum(1 for r in results if r.is_reviewed)
    st.metric("Reviewed", f"{reviewed}/{len(results)}")

with st.expander("Full student response", expanded=False):
    st.text(submission.submission_text)

st.divider()

# ---------------------------------------------------------------------------
# Per-question review
# ---------------------------------------------------------------------------
for index, result in enumerate(results, start=1):
    question = assessment.get_question(result.question_id)
    if question is None:
        st.warning(
            f"Question {result.question_id} is no longer part of this assessment; "
            "its result is shown read-only.",
            icon=":material/warning:",
        )
        continue

    with st.container(border=True):
        title_col, badge_col = st.columns([3, 1])
        with title_col:
            st.markdown(f"#### Question {index} · {question.max_marks} marks")
        with badge_col:
            review_status_badge(result.review_status)

        st.markdown(f"**Question:** {question.question_text}")

        ref_left, ref_right = st.columns(2)
        with ref_left:
            st.markdown("**Model answer**")
            st.info(question.model_answer)
        with ref_right:
            st.markdown("**Marking criteria**")
            st.info(question.marking_criteria or "No marking criteria were provided.")

        # --- AI recommendation ---
        st.markdown("**AI recommendation** (not final)")
        rec_a, rec_b = st.columns([1, 2])
        with rec_a:
            st.metric(
                "Suggested score",
                f"{result.suggested_score} / {result.max_marks}",
            )
            confidence_badge(result.confidence)
        with rec_b:
            st.markdown("*What the response got right*")
            for item in result.correct_elements:
                st.markdown(f"- {item}")

            st.markdown("*Errors detected*")
            if not result.errors:
                st.markdown("- No errors were detected.")
            else:
                for error in result.errors:
                    st.markdown(
                        f"- **{error.error_type.label}** — {error.explanation}"
                    )

        st.markdown("**Suggested student feedback**")
        st.success(result.student_feedback)
        st.caption(f":material/psychology: Note for you: {result.teacher_note}")

        st.markdown("---")

        # --- Teacher decision ---
        st.markdown("**Your decision**")
        default_score = (
            result.teacher_approved_score
            if result.teacher_approved_score is not None
            else result.suggested_score
        )
        default_feedback = result.teacher_approved_feedback or result.student_feedback

        score_col, feedback_col = st.columns([1, 3])
        with score_col:
            teacher_score = st.number_input(
                "Score to award",
                min_value=0.0,
                max_value=float(result.max_marks),
                value=float(default_score),
                step=0.5,
                key=f"score_{result.submission_id}_{result.question_id}",
                help=f"Must be between 0 and {result.max_marks}.",
            )
        with feedback_col:
            teacher_feedback = st.text_area(
                "Feedback the student will see",
                value=default_feedback,
                height=120,
                key=f"feedback_{result.submission_id}_{result.question_id}",
            )

        accept_col, save_col, flag_col = st.columns(3)
        key_suffix = f"{result.submission_id}_{result.question_id}"

        if accept_col.button(
            "Accept as-is",
            key=f"accept_{key_suffix}",
            width="stretch",
            help="Approve the AI score and feedback without changes.",
        ):
            _save_decision(
                result,
                score=result.suggested_score,
                feedback=result.student_feedback,
                status=ReviewStatus.APPROVED,
            )
            st.rerun()

        if save_col.button(
            "Save my edits",
            key=f"edit_{key_suffix}",
            type="primary",
            width="stretch",
            help="Record the score and feedback exactly as you have written them above.",
        ):
            # The service decides whether this counts as APPROVED or EDITED.
            _save_decision(
                result,
                score=teacher_score,
                feedback=teacher_feedback,
                status=ReviewStatus.EDITED,
            )
            st.rerun()

        if flag_col.button(
            "Flag for review",
            key=f"flag_{key_suffix}",
            width="stretch",
            help="Park this result. It stays out of analytics until you approve it.",
        ):
            _save_decision(result, score=None, feedback=None, status=ReviewStatus.FLAGGED)
            st.rerun()

        if result.is_reviewed:
            final = result.final_score
            st.caption(
                f":material/history: Currently recorded as "
                f"**{review_status_label(result.review_status)}**"
                + (f" at **{final} / {result.max_marks}**." if final is not None else ".")
            )

privacy_notice()
