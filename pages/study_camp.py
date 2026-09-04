"""Study Camp - a short, targeted revision programme.

WHAT THIS FILE DOES
  Turns the weakness analysis into a day-by-day plan, then tracks whether the
  student actually improved against the baseline captured when the camp began.

WHERE THE LOGIC LIVES
  `study_camp_service.build_camp` picks the topics, difficulty and questions.
  This file only collects the choices and draws the result.

TRY CHANGING THIS
  `QUESTIONS_PER_SESSION` in services/study_camp_service.py changes how much
  work each day is.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from components.layout import empty_state, metric_row, page_header, privacy_notice
from components.navigation import goto
from services import analytics_service as analytics
from services import assessment_service as service
from services import state as store
from services import study_camp_service as camps

TEAL = "#0F766E"
NAVY = "#0F2D52"

student = store.get_current_user()
if student is None or not student.is_student:
    st.error("Sign in as a student to use this page.", icon=":material/error:")
    st.stop()

page_header(
    "Study Camp",
    "A short, focused programme built from your own weak spots.",
    "Pick the topics you want to drill, work through one session a day, and record "
    "how you did. The camp shows whether you actually improved.",
)

st.caption(
    ":material/construction: Practice questions come from a template generator for "
    "now. A real AI question writer replaces it in a later phase."
)

assessments = service.list_assessments()
my_submissions = service.list_submissions(student_id=student.id)
my_results = service.list_grading_results(student_id=student.id)
frame = analytics.student_dataframe(student.id, my_results, assessments, my_submissions)

camp = service.active_camp_for(student.id)

# ---------------------------------------------------------------------------
# No camp yet: build one
# ---------------------------------------------------------------------------
if camp is None:
    if frame.empty:
        empty_state(
            "There is not enough work yet to know what you should revise.",
            "Add a few pieces of past work first, then come back.",
            icon=":material/inventory_2:",
        )
        if st.button("Go to My Work", type="primary"):
            goto("My Work")
        privacy_notice()
        st.stop()

    suggested = camps.suggest_topics(frame, limit=3)
    strength = analytics.topic_strength(frame)

    st.subheader("Build your camp")

    if not suggested:
        st.success(
            "Nothing is currently below the revision threshold - you are in good "
            "shape across every topic with practice available.",
            icon=":material/task_alt:",
        )
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
        privacy_notice()
        st.stop()

    st.info(
        "Suggested from your results: **" + "**, **".join(suggested) + "**.",
        icon=":material/target:",
    )

    options = camps.available_topics_for(frame)
    chosen = st.multiselect(
        "Topics to drill",
        options=options,
        default=suggested,
        help="Weakest topics are pre-selected. You can override them.",
    )
    duration = st.slider(
        "How many days?",
        min_value=camps.MIN_DURATION_DAYS,
        max_value=camps.MAX_DURATION_DAYS,
        value=camps.DEFAULT_DURATION_DAYS,
        help="One session per day, rotating through your chosen topics.",
    )

    if chosen:
        baseline = camps.baseline_for(frame, chosen)
        st.caption(
            f"Your current average across those topics is **{baseline}%**. "
            f"That becomes the baseline the camp measures against, and it will "
            f"start you at **{camps.difficulty_for(baseline)}** difficulty."
        )

    if st.button("Start my study camp", type="primary", disabled=not chosen):
        try:
            new_camp = camps.build_camp(
                student_id=student.id,
                frame=frame,
                topics=chosen,
                duration_days=duration,
            )
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
        else:
            service.save_study_camp(new_camp)
            st.rerun()

    privacy_notice()
    st.stop()

# ---------------------------------------------------------------------------
# Active camp
# ---------------------------------------------------------------------------
summary = camps.progress_summary(camp)

head_a, head_b = st.columns([3, 1])
with head_a:
    st.subheader("Your current camp")
    st.caption(
        f"{camp.duration_days} days · {', '.join(camp.topics)} · "
        f"started {camp.started_on.strftime('%d %b %Y')}"
    )
with head_b:
    if st.button("Start over", width="stretch", help="Delete this camp and build a new one."):
        service.delete_study_camp(camp.id)
        st.rerun()

latest = summary["latest"]
improvement = summary["improvement"]

metric_row(
    [
        ("Starting point", f"{summary['baseline']}%", "Your average when the camp began."),
        (
            "Where you are now",
            f"{latest}%" if latest is not None else "—",
            "Average across the sessions you have completed.",
        ),
        (
            "Change",
            f"{improvement:+g} pts" if improvement is not None else "—",
            "Percentage points gained since starting.",
        ),
        (
            "Sessions done",
            f"{summary['completed']}/{summary['total']}",
            "Work through one a day.",
        ),
    ]
)

st.progress(summary["progress"], text=f"{summary['progress']:.0%} complete")

if summary["is_complete"]:
    if improvement is not None and improvement > 0:
        st.success(
            f"Camp complete - you went from {summary['baseline']}% to {latest}%, "
            f"a gain of {improvement:+g} points.",
            icon=":material/celebration:",
        )
    else:
        st.info(
            "Camp complete. The scores have not moved much yet - it may be worth "
            "running another camp on the same topics.",
            icon=":material/replay:",
        )

# --- Before / after ---------------------------------------------------------
if latest is not None:
    figure = go.Figure()
    figure.add_bar(
        x=["Starting point", "Now"],
        y=[summary["baseline"], latest],
        marker_color=[NAVY, TEAL],
        text=[f"{summary['baseline']}%", f"{latest}%"],
        textposition="outside",
    )
    figure.update_layout(
        margin=dict(l=10, r=10, t=20, b=10),
        height=280,
        yaxis=dict(range=[0, 105], title="Average score (%)"),
        showlegend=False,
    )
    st.plotly_chart(figure, width="stretch")

st.divider()

# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
st.subheader("Your sessions")

for session in camp.sessions:
    status = "✓" if session.completed else "○"
    label = f"{status}  Day {session.day} · {session.topic}"
    if session.completed and session.percentage is not None:
        label += f" · {session.score}/{session.question_count} ({session.percentage:g}%)"

    with st.expander(label, expanded=not session.completed and not summary["is_complete"]):
        st.caption(session.skill_focus)

        for number, question in enumerate(session.questions, start=1):
            st.markdown(f"**{number}.** {question}")

        with st.expander("Stuck? Show the method hints"):
            st.caption(
                "These are method reminders, not worked answers - try the question first."
            )
            for number, hint in enumerate(session.method_hints, start=1):
                st.markdown(f"**{number}.** {hint}")

        st.markdown("---")
        if session.completed:
            st.success(
                f"Recorded: {session.score} out of {session.question_count} correct.",
                icon=":material/check_circle:",
            )
            if st.button("Change my answer", key=f"reopen_{camp.id}_{session.day}"):
                camps.reopen_session(camp, session.day)
                service.save_study_camp(camp)
                st.rerun()
        else:
            score = st.number_input(
                "How many did you get right?",
                min_value=0,
                max_value=session.question_count,
                value=0,
                step=1,
                key=f"score_{camp.id}_{session.day}",
            )
            if st.button(
                "Mark this session done",
                type="primary",
                key=f"done_{camp.id}_{session.day}",
            ):
                try:
                    camps.record_session_result(camp, session.day, int(score))
                except ValueError as exc:
                    st.error(str(exc), icon=":material/error:")
                else:
                    service.save_study_camp(camp)
                    st.rerun()

privacy_notice()
