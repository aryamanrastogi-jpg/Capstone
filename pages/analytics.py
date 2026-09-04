"""Analytics - class performance built from teacher-approved results only."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from components.layout import empty_state, metric_row, page_header, privacy_notice
from components.navigation import goto
from services import analytics_service as analytics
from services import assessment_service as service
from services import state as store

NAVY = "#0F2D52"
TEAL = "#0F766E"
SEQUENCE = ["#0F766E", "#0F2D52", "#2563EB", "#0891B2", "#7C3AED", "#B45309"]

# Teacher-only page. Navigation already keeps students out; this is the second
# line of defence if the page is reached directly.
_viewer = store.get_current_user()
if _viewer is None or not _viewer.is_teacher:
    st.error("Sign in as a teacher to use this page.", icon=":material/error:")
    st.stop()

page_header(
    "Analytics",
    "Where the class is strong, and what needs revisiting.",
    "Only results you have approved or edited are counted. Anything still awaiting "
    "review, or flagged, is excluded.",
)

assessments = service.list_assessments()
submissions = service.list_submissions()
results = service.list_grading_results()

frame = analytics.results_dataframe(results, assessments, submissions)
approved_count = len(analytics.approved_results(results))
acceptance = analytics.acceptance_rate(results)
average = analytics.average_percentage(results)

metric_row(
    [
        (
            "Average class score",
            f"{average}%" if average is not None else "—",
            "Total marks awarded divided by total marks available, across approved results.",
        ),
        ("Approved results", approved_count, "Question-level results you have signed off."),
        (
            "AI accepted unedited",
            f"{acceptance}%" if acceptance is not None else "—",
            "Share of your reviewed results where you kept the AI score and wording exactly.",
        ),
        (
            "Awaiting review",
            len(analytics.pending_results(results)),
            "Not counted in any chart on this page.",
        ),
    ]
)

if frame.empty:
    st.divider()
    empty_state(
        "No approved results yet, so there is nothing to chart.",
        "Approve or edit some grading recommendations and the analytics will fill in.",
        icon=":material/query_stats:",
    )
    if st.button("Go to Review Grading", type="primary"):
        goto("Review Grading")
    privacy_notice()
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# Score distribution and error categories
# ---------------------------------------------------------------------------
dist_col, error_col = st.columns(2)

with dist_col:
    st.subheader("Score distribution")
    st.caption("Approved question-level results, grouped into percentage bands.")
    distribution = analytics.score_distribution(frame)
    figure = px.bar(
        distribution,
        x="band",
        y="count",
        labels={"band": "Score band (%)", "count": "Results"},
        color_discrete_sequence=[TEAL],
    )
    figure.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=330,
        yaxis=dict(dtick=1) if distribution["count"].max() <= 8 else {},
    )
    st.plotly_chart(figure, width="stretch")

with error_col:
    st.subheader("Most frequent error categories")
    st.caption("Counted across approved results only.")
    errors = analytics.error_frequency(results, approved_only=True)
    if errors.empty:
        empty_state("No errors were detected in the approved results.")
    else:
        figure = px.bar(
            errors,
            x="count",
            y="label",
            orientation="h",
            labels={"count": "Occurrences", "label": ""},
            color_discrete_sequence=[NAVY],
        )
        figure.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=330,
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(figure, width="stretch")

st.divider()

# ---------------------------------------------------------------------------
# Hardest questions
# ---------------------------------------------------------------------------
st.subheader("Most difficult questions")
st.caption("Average percentage awarded per question, lowest first.")

difficulty = analytics.question_difficulty(frame)
if difficulty.empty:
    empty_state("Not enough approved results to rank questions yet.")
else:
    figure = px.bar(
        difficulty.head(8),
        x="avg_percentage",
        y="question_text",
        orientation="h",
        labels={"avg_percentage": "Average score (%)", "question_text": ""},
        hover_data={"responses": True},
        color_discrete_sequence=[TEAL],
    )
    figure.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=max(280, 60 * min(len(difficulty), 8)),
        xaxis=dict(range=[0, 100]),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(figure, width="stretch")

st.divider()

# ---------------------------------------------------------------------------
# Topics needing revision and per-student totals
# ---------------------------------------------------------------------------
topic_col, student_col = st.columns(2)

with topic_col:
    st.subheader("Topics requiring revision")
    topics = analytics.topic_performance(frame)
    if topics.empty:
        empty_state("No topic data yet.")
    else:
        weakest = topics.iloc[0]
        if weakest["avg_percentage"] < 60:
            st.warning(
                f"**{weakest['topic']}** is the weakest topic at "
                f"{weakest['avg_percentage']}%. Consider a revision session.",
                icon=":material/priority_high:",
            )
        st.dataframe(
            topics.rename(
                columns={
                    "topic": "Topic",
                    "avg_percentage": "Average (%)",
                    "responses": "Results",
                }
            ),
            hide_index=True,
            width="stretch",
        )

with student_col:
    st.subheader("Per-student totals")
    st.caption("Anonymous identifiers only.")
    students = analytics.submission_scores(frame)
    if students.empty:
        empty_state("No per-student totals yet.")
    else:
        st.dataframe(
            students.rename(
                columns={
                    "student_identifier": "Student",
                    "awarded": "Awarded",
                    "available": "Available",
                    "percentage": "Percentage",
                }
            ),
            hide_index=True,
            width="stretch",
        )

with st.expander("Approved results (raw table)"):
    st.dataframe(
        frame[
            [
                "student_identifier",
                "assessment_title",
                "question_text",
                "suggested_score",
                "final_score",
                "max_marks",
                "percentage",
                "confidence",
                "review_status",
            ]
        ].rename(
            columns={
                "student_identifier": "Student",
                "assessment_title": "Assessment",
                "question_text": "Question",
                "suggested_score": "AI suggested",
                "final_score": "Final",
                "max_marks": "Out of",
                "percentage": "%",
                "confidence": "Confidence",
                "review_status": "Status",
            }
        ),
        hide_index=True,
        width="stretch",
    )

privacy_notice()
