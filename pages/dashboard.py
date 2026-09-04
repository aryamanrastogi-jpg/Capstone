"""Dashboard - the teacher's landing page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.layout import empty_state, metric_row, page_header, privacy_notice
from components.navigation import goto
from components.status_badges import submission_status_label
from services import analytics_service as analytics
from services import assessment_service as service

page_header(
    "Dashboard",
    "Your assessments, submissions and where the class currently stands.",
    "Scores shown here come only from grading results you have already reviewed.",
)

assessments = service.list_assessments()
submissions = service.list_submissions()
results = service.list_grading_results()

metrics = analytics.dashboard_metrics(assessments, submissions, results)
average = metrics["average_score_pct"]

metric_row(
    [
        ("Total assessments", metrics["total_assessments"], "Assessments you have created."),
        (
            "Awaiting review",
            metrics["awaiting_review"],
            "Submissions with AI suggestions that still need your sign-off.",
        ),
        (
            "Reviewed submissions",
            metrics["reviewed_submissions"],
            "Submissions where every question has been approved or edited.",
        ),
        (
            "Average class score",
            f"{average}%" if average is not None else "—",
            "Across approved results only.",
        ),
    ]
)

st.write("")

# ---------------------------------------------------------------------------
# Call to action
# ---------------------------------------------------------------------------
cta_left, cta_mid, cta_right = st.columns([2, 1, 1])
with cta_left:
    if not assessments:
        st.warning(
            "You have no assessments yet. Create one to start collecting responses.",
            icon=":material/rocket_launch:",
        )
    elif metrics["awaiting_review"]:
        st.info(
            f"{metrics['awaiting_review']} submission(s) are waiting for your review.",
            icon=":material/pending_actions:",
        )
    else:
        st.success("Everything submitted has been reviewed. Nice work.", icon=":material/task_alt:")

with cta_mid:
    if st.button("Create assessment", type="primary", width="stretch"):
        goto("Create Assessment")
with cta_right:
    if st.button("Review grading", width="stretch"):
        goto("Review Grading")

st.divider()

# ---------------------------------------------------------------------------
# Recent activity
# ---------------------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Recent assessments")
    if not assessments:
        empty_state(
            "No assessments yet.",
            "Use Create Assessment to add your questions, model answers and marking criteria.",
        )
    else:
        recent = sorted(assessments, key=lambda a: a.created_at, reverse=True)[:5]
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Title": a.title,
                        "Topic": a.topic,
                        "Grade": a.grade_level,
                        "Questions": a.question_count,
                        "Marks": a.max_marks,
                        "Created": a.created_at.strftime("%d %b %Y"),
                    }
                    for a in recent
                ]
            ),
            hide_index=True,
            width="stretch",
        )

with right:
    st.subheader("Recent submissions")
    if not submissions:
        empty_state(
            "No submissions yet.",
            "Use Upload Responses to paste or upload a student response.",
        )
    else:
        titles = {a.id: a.title for a in assessments}
        recent_subs = sorted(submissions, key=lambda s: s.submitted_at, reverse=True)[:6]
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Student": s.student_identifier,
                        "Assessment": titles.get(s.assessment_id, "Unknown"),
                        "Status": submission_status_label(s.status),
                        "Submitted": s.submitted_at.strftime("%d %b, %H:%M"),
                    }
                    for s in recent_subs
                ]
            ),
            hide_index=True,
            width="stretch",
        )

st.divider()

# ---------------------------------------------------------------------------
# Common error categories
# ---------------------------------------------------------------------------
st.subheader("Common error categories")
st.caption("Across all grading results, including those still awaiting review.")

errors = analytics.error_frequency(results)
if errors.empty:
    empty_state(
        "No graded responses yet, so there are no error patterns to show.",
        "Error categories appear once submissions have been graded.",
    )
else:
    chart_col, table_col = st.columns([2, 1])
    with chart_col:
        st.bar_chart(errors.set_index("label")["count"], height=280, color="#0F766E")
    with table_col:
        st.dataframe(
            errors.rename(columns={"label": "Error type", "count": "Occurrences"})[
                ["Error type", "Occurrences"]
            ],
            hide_index=True,
            width="stretch",
        )

privacy_notice()
