"""Class Overview - the teacher's landing page.

WHAT THIS FILE DOES
  Shows the teacher their roster: who is uploading work, how each student is
  tracking, what is waiting to be reviewed, and where the AI's read of a piece
  of work disagrees with the mark that was actually given.

THE MISMATCH PANEL
  When a student records the mark their teacher gave them, `mark_mismatches`
  compares it against the AI estimate. A large gap is a prompt to look again -
  never a claim that the teacher was wrong.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.layout import empty_state, metric_row, page_header, privacy_notice
from components.navigation import goto
from components.status_badges import submission_status_label
from services import analytics_service as analytics
from services import assessment_service as service
from services import state as store

teacher = store.get_current_user()
if teacher is None or not teacher.is_teacher:
    st.error("Sign in as a teacher to use this page.", icon=":material/error:")
    st.stop()

page_header(
    "Class Overview",
    f"{teacher.display_name} · your students and where they stand.",
    "Class scores count only results you have reviewed. Student self-study "
    "estimates are excluded.",
)

assessments = service.list_assessments()
submissions = service.list_submissions()
results = service.list_grading_results()
roster = service.list_students_for_teacher(teacher.id)

metrics = analytics.dashboard_metrics(assessments, submissions, results)
average = metrics["average_score_pct"]
mismatches = analytics.mark_mismatches(submissions, results, assessments)

metric_row(
    [
        ("Students", len(roster), "Students on your roster."),
        (
            "Awaiting review",
            metrics["awaiting_review"],
            "Submissions with AI suggestions that still need your sign-off.",
        ),
        (
            "Class average",
            f"{average}%" if average is not None else "—",
            "Across reviewed results only.",
        ),
        (
            "Possible mismatches",
            len(mismatches),
            "Where the AI reads a piece of work very differently to the mark given.",
        ),
    ]
)

st.write("")

cta_a, cta_b, cta_c = st.columns([2, 1, 1])
with cta_a:
    if metrics["awaiting_review"]:
        st.info(
            f"{metrics['awaiting_review']} submission(s) are waiting for your review.",
            icon=":material/pending_actions:",
        )
    else:
        st.success("Everything submitted has been reviewed.", icon=":material/task_alt:")
with cta_b:
    if st.button("Review grading", type="primary", width="stretch"):
        goto("Review Grading")
with cta_c:
    if st.button("Create assessment", width="stretch"):
        goto("Create Assessment")

st.divider()

# ---------------------------------------------------------------------------
# Possible marking mismatches
# ---------------------------------------------------------------------------
st.subheader("Possible marking mismatches")
st.caption(
    "Shown when a student recorded the mark you gave and the AI reads the work "
    "more than 15 percentage points differently. A prompt to look again, nothing more."
)

if mismatches.empty:
    empty_state(
        "No mismatches to look at.",
        "These appear when a student adds the mark they were given alongside their work.",
        icon=":material/check_circle:",
    )
else:
    for _, row in mismatches.iterrows():
        tone = st.warning if abs(row["gap"]) < 30 else st.error
        tone(
            f"**{row['student_identifier']}** · {row['assessment_title']} — "
            f"marked **{row['teacher_score']:g}/{row['max_marks']:g}** "
            f"({row['teacher_pct']}%), AI reads it as **{row['ai_score']:g}/"
            f"{row['max_marks']:g}** ({row['ai_pct']}%). "
            f"{row['direction']} by {abs(row['gap'])} points.",
            icon=":material/compare_arrows:",
        )

st.divider()

# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------
st.subheader("Your students")

if not roster:
    empty_state("No students are linked to you yet.")
else:
    rows = []
    for student in roster:
        student_subs = service.list_submissions(student_id=student.id)
        student_results = service.list_grading_results(student_id=student.id)
        student_frame = analytics.student_dataframe(
            student.id, student_results, assessments, student_subs
        )
        weakest = analytics.weakest_topics(student_frame, limit=1)
        last_seen = (
            max(s.submitted_at for s in student_subs).strftime("%d %b")
            if student_subs
            else "—"
        )
        rows.append(
            {
                "Student": student.display_name,
                "Pieces of work": len(student_subs),
                "Average (%)": (
                    round(float(student_frame["percentage"].mean()), 1)
                    if not student_frame.empty
                    else None
                ),
                "Weakest topic": weakest[0] if weakest else "—",
                "Last activity": last_seen,
            }
        )

    st.dataframe(
        pd.DataFrame(rows).sort_values("Average (%)", na_position="first"),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Averages include the students' own AI estimates, so treat them as a "
        "direction of travel rather than a report-card grade."
    )

st.divider()

# ---------------------------------------------------------------------------
# Recent activity and error patterns
# ---------------------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Recent submissions")
    if not submissions:
        empty_state("No submissions yet.")
    else:
        titles = {a.id: a.title for a in assessments}
        recent = sorted(submissions, key=lambda s: s.submitted_at, reverse=True)[:8]
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Student": s.student_identifier,
                        "Work": titles.get(s.assessment_id, "Unknown"),
                        "Status": submission_status_label(s.status),
                        "Added": s.submitted_at.strftime("%d %b"),
                    }
                    for s in recent
                ]
            ),
            hide_index=True,
            width="stretch",
        )

with right:
    st.subheader("Common error categories")
    st.caption("Across all grading results, including those awaiting review.")
    errors = analytics.error_frequency(results)
    if errors.empty:
        empty_state("No graded responses yet.")
    else:
        st.bar_chart(errors.set_index("label")["count"], height=300, color="#0F766E")

privacy_notice()
