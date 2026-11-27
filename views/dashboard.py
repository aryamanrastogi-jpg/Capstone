"""Class Overview - the teacher's landing page.

WHAT THIS FILE DOES
  Shows the teacher their roster: who is uploading work, who has not handed an
  assessment in yet, how each student is tracking, what is waiting to be
  reviewed, and where the AI's read of a piece of work disagrees with the mark
  that was actually given.

THE MISMATCH PANEL
  When a student records the mark their teacher gave them, `mark_mismatches`
  compares it against the AI estimate. A large gap is a prompt to look again -
  never a claim that the teacher was wrong.

NOT HANDED IN YET
  Every other number on this page is about work that exists, so a student who
  never handed anything in would not show up anywhere. `not_handed_in` lists
  them for each of the teacher's own assessments. It is given the roster rather
  than fetching it, so it can later be pointed at a single class.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.layout import empty_state, metric_row, page_header, privacy_notice
from components.navigation import goto
from components.status_badges import submission_status_label
from services import analytics_service as analytics
from services import assessment_service as service
from services import roster_service
from services import state as store
from utils import palette

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

assessments = service.list_assessments_for_teacher()
submissions = service.list_submissions()
results = service.list_grading_results()
roster = service.list_students_for_teacher(teacher.id)

# Headline numbers cover teacher-marked work only; self-study estimates are
# excluded, as the caption above says. Mismatches still read every submission.
review_submissions = service.list_submissions_for_review()
_review_ids = {s.id for s in review_submissions}
metrics = analytics.dashboard_metrics(
    assessments,
    review_submissions,
    [r for r in results if r.submission_id in _review_ids],
)
average = metrics["average_score_pct"]
mismatches = analytics.mark_mismatches(submissions, results, assessments)

metric_row(
    [
        ("Students", len(roster), "Students on your roster."),
        (
            "Submissions awaiting review",
            metrics["awaiting_review"],
            "Submissions with AI suggestions that still need your sign-off.",
        ),
        (
            "Flagged",
            metrics["flagged"],
            "Results you flagged for a second look. They count as unscored until "
            "you approve or edit them.",
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
    ],
    per_row=5,
)

st.write("")

cta_a, cta_b, cta_c = st.columns([2, 1, 1])
with cta_a:
    if metrics["awaiting_review"]:
        st.info(
            f"{metrics['awaiting_review']} submission{'s are' if metrics['awaiting_review'] != 1 else ' is'} waiting for your review.",
            icon=":material/pending_actions:",
        )
    elif not metrics["flagged"]:
        st.success("Everything submitted has been reviewed.", icon=":material/task_alt:")
    if metrics["flagged"]:
        st.warning(
            f"{metrics['flagged']} flagged "
            f"{'result still needs' if metrics['flagged'] == 1 else 'results still need'}"
            " a decision.",
            icon=":material/flag:",
        )
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
st.header("Possible marking mismatches")
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
        st.warning(
            f"**{row['student_identifier']}** · {row['assessment_title']} — "
            f"marked **{row['teacher_score']:g}/{row['max_marks']:g}** "
            f"({row['teacher_pct']}%), AI reads it as **{row['ai_score']:g}/"
            f"{row['ai_max_marks']:g}** ({row['ai_pct']}%). "
            f"{row['direction']} by {abs(row['gap'])} points.",
            icon=":material/compare_arrows:",
        )

st.divider()

# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------
st.header("Your students")

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
# Not handed in yet
# ---------------------------------------------------------------------------
st.markdown("## Not handed in yet")
st.caption(
    "Students on your roster with nothing handed in for the assessment you pick. "
    "Any attempt counts, marked or not. A practice mock exam that only borrowed "
    "its questions does not."
)

hand_ins = analytics.not_handed_in(assessments, roster, submissions, teacher_id=teacher.id)

if not hand_ins:
    empty_state(
        "You have no assessments of your own to check yet.",
        "Only assessments you created count here. Create one, and this shows who "
        "still needs to hand work in.",
        icon=":material/assignment:",
    )
elif not roster:
    empty_state(
        "No students are linked to you yet.",
        "Students join with your class code on My Class.",
    )
else:
    by_assessment = {entry["assessment"].id: entry for entry in hand_ins}

    def _assessment_label(assessment_id: str) -> str:
        assessment = by_assessment[assessment_id]["assessment"]
        return f"{assessment.title} · set {assessment.created_at:%d %b}"

    # The list comes newest first, so the default is the latest assessment:
    # the one most likely to need chasing.
    chosen = by_assessment[
        st.selectbox(
            "Assessment",
            options=list(by_assessment),
            format_func=_assessment_label,
        )
    ]
    st.markdown(f"**{chosen['handed_in']} of {chosen['total']}** handed in")

    if not chosen["missing"]:
        empty_state(
            "Everyone on your roster has handed in work for this one.",
            icon=":material/task_alt:",
        )
    else:
        # Name, class and year group: enough to follow up, nothing more. The
        # class column needs migration 013; without it the column is left out.
        try:
            class_names = {c.id: c.name for c in roster_service.list_classes(teacher.id)}
        except roster_service.ClassesNotSetUp:
            class_names = {}
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Student": student.display_name,
                        **(
                            {"Class": class_names.get(student.class_id or "", "No class")}
                            if class_names
                            else {}
                        ),
                        "Year": str(student.year_group) if student.year_group else "—",
                    }
                    for student in chosen["missing"]
                ]
            ),
            hide_index=True,
            width="stretch",
        )

st.divider()

# ---------------------------------------------------------------------------
# Recent activity and error patterns
# ---------------------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.header("Recent submissions")
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
                        "Work": ("Mock exam: " if s.is_mock_exam else "")
                        + titles.get(s.assessment_id, "Unknown"),
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
    st.header("Common error categories")
    st.caption("Across all grading results, including those awaiting review.")
    errors = analytics.error_frequency(results)
    if errors.empty:
        empty_state("No graded responses yet.")
    else:
        st.bar_chart(errors.set_index("label")["count"], height=300, color=palette.PRIMARY)

privacy_notice()
