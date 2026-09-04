"""My Progress - the student's weakness dashboard.

WHAT THIS FILE DOES
  Answers "where am I actually weak?" by looking across everything the student
  has uploaded this term, rather than at one piece of work. This is the part
  that a one-off chatbot conversation cannot do.

WHERE THE NUMBERS COME FROM
  `analytics_service.student_dataframe` scopes to this student, then
  `topic_trend`, `topic_strength` and `error_frequency` do the maths. No
  calculations happen in this file - it only draws.

TRY CHANGING THIS
  Change `freq="W"` to `freq="M"` in the trend call to group by month.
"""

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
BAND_COLOURS = {
    "Secure": "#16A34A",
    "Developing": "#0F766E",
    "Needs work": "#D97706",
    "Priority": "#DC2626",
}

student = store.get_current_user()
if student is None or not student.is_student:
    st.error("Sign in as a student to use this page.", icon=":material/error:")
    st.stop()

page_header(
    "My Progress",
    "What your work over the term says about where you stand.",
    "Built from everything you have added. The more work you add, the more "
    "reliable this gets.",
)

assessments = service.list_assessments()
my_submissions = service.list_submissions(student_id=student.id)
my_results = service.list_grading_results(student_id=student.id)
frame = analytics.student_dataframe(student.id, my_results, assessments, my_submissions)

if frame.empty:
    empty_state(
        "There is nothing to chart yet.",
        "Add some past work on the My Work page and your progress will appear here.",
        icon=":material/query_stats:",
    )
    if st.button("Go to My Work", type="primary"):
        goto("My Work")
    privacy_notice()
    st.stop()

# ---------------------------------------------------------------------------
# Headline
# ---------------------------------------------------------------------------
average = round(float(frame["percentage"].mean()), 1)
strength = analytics.topic_strength(frame)
weakest = analytics.weakest_topics(frame, limit=1)
official_count = int(frame["is_official"].sum())

metric_row(
    [
        ("Overall average", f"{average}%", "Across every question you have added."),
        ("Topics covered", frame["topic"].nunique(), "Breadth of the picture."),
        ("Questions analysed", len(frame), "More questions means more confidence."),
        (
            "Teacher-confirmed",
            f"{official_count}/{len(frame)}",
            "How many of these are real marks rather than AI estimates.",
        ),
    ]
)

st.caption(
    ":material/smart_toy: Anything not teacher-confirmed is an AI estimate. Useful "
    "for spotting patterns, not a real grade."
)

st.divider()

# ---------------------------------------------------------------------------
# Trend over the term
# ---------------------------------------------------------------------------
st.subheader("How you are tracking")
st.caption("Average score per week. Flat or falling lines are where to focus.")

overall = analytics.overall_trend(frame, freq="W")
by_topic = analytics.topic_trend(frame, freq="W")

if len(overall) < 2:
    st.info(
        "Once you have work from more than one week, a trend line will appear here.",
        icon=":material/timeline:",
    )
else:
    show_topics = st.toggle("Split by topic", value=True)
    source = by_topic if show_topics else overall
    figure = px.line(
        source,
        x="period",
        y="avg_percentage",
        color="topic" if show_topics else None,
        markers=True,
        labels={
            "period": "Week beginning",
            "avg_percentage": "Average score (%)",
            "topic": "Topic",
        },
        color_discrete_sequence=SEQUENCE,
    )
    figure.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=360,
        yaxis=dict(range=[0, 100]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(figure, width="stretch")

st.divider()

# ---------------------------------------------------------------------------
# Topic strength
# ---------------------------------------------------------------------------
st.subheader("Topic by topic")

left, right = st.columns([2, 1])
with left:
    figure = px.bar(
        strength,
        x="avg_percentage",
        y="topic",
        orientation="h",
        color="band",
        color_discrete_map=BAND_COLOURS,
        labels={"avg_percentage": "Average score (%)", "topic": "", "band": ""},
        hover_data={"responses": True},
    )
    figure.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=max(280, 55 * len(strength)),
        xaxis=dict(range=[0, 100]),
        yaxis=dict(autorange="reversed"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(figure, width="stretch")

with right:
    st.dataframe(
        strength.rename(
            columns={
                "topic": "Topic",
                "avg_percentage": "Average (%)",
                "responses": "Questions",
                "band": "Standing",
            }
        ),
        hide_index=True,
        width="stretch",
    )

if weakest:
    cta_a, cta_b = st.columns([3, 1])
    with cta_a:
        st.warning(
            f"**{weakest[0]}** needs the most attention. A study camp will drill it.",
            icon=":material/priority_high:",
        )
    with cta_b:
        if st.button("Build a study camp", type="primary", width="stretch"):
            goto("Study Camp")

st.divider()

# ---------------------------------------------------------------------------
# Mistake patterns
# ---------------------------------------------------------------------------
st.subheader("The mistakes you repeat")
st.caption("Knowing the pattern is usually more useful than any single wrong answer.")

errors = analytics.error_frequency(my_results)
error_col, type_col = st.columns(2)

with error_col:
    if errors.empty:
        empty_state("No error patterns detected yet.")
    else:
        figure = px.bar(
            errors,
            x="count",
            y="label",
            orientation="h",
            labels={"count": "Times", "label": ""},
            color_discrete_sequence=[NAVY],
        )
        figure.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=300,
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(figure, width="stretch")

with type_col:
    st.markdown("**By type of work**")
    by_type = (
        frame.groupby("assessment_type", as_index=False)
        .agg(avg=("percentage", "mean"), questions=("percentage", "size"))
        .sort_values("avg", ascending=True, ignore_index=True)
    )
    by_type["avg"] = by_type["avg"].round(1)
    st.dataframe(
        by_type.rename(
            columns={"assessment_type": "Type", "avg": "Average (%)", "questions": "Questions"}
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Mock exams are usually the closest thing to how you will perform in the real one."
    )

with st.expander("Every question, in full"):
    st.dataframe(
        frame[
            [
                "submitted_at",
                "assessment_title",
                "topic",
                "question_text",
                "score",
                "max_marks",
                "percentage",
                "is_official",
            ]
        ]
        .sort_values("submitted_at", ascending=False)
        .rename(
            columns={
                "submitted_at": "Date",
                "assessment_title": "Work",
                "topic": "Topic",
                "question_text": "Question",
                "score": "Score",
                "max_marks": "Out of",
                "percentage": "%",
                "is_official": "Teacher confirmed",
            }
        ),
        hide_index=True,
        width="stretch",
    )

privacy_notice()
