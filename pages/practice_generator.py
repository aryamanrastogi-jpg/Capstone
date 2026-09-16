"""Practice Generator - follow-up practice aimed at real weaknesses (prototype).

By default the questions are chosen from graded results: the weakest topics,
the error categories that keep coming up there, at a difficulty that fits.
Each question says why it was chosen. A manual mode is kept for picking a
topic and error category by hand.

Pointers, not answers: the method pointer names the approach, never the
worked solution or the final value.
"""

from __future__ import annotations

import streamlit as st

from components.layout import hint_note, page_header, privacy_notice
from models import ErrorType
from services import analytics_service as analytics
from services import assessment_service as service
from services import practice_service
from services import state as store
from services import targeted_practice_service as targeted

FROM_RESULTS = "From results"
BY_HAND = "Choose it yourself"

page_header(
    "Practice Generator",
    "Practice aimed at where the marks are actually being lost.",
    "Questions are picked from graded work: the weakest topics first, the error "
    "types that keep coming up, at a level that fits. Each one says why it was "
    "chosen.",
)

st.warning(practice_service.GENERATOR_LABEL, icon=":material/construction:")

_viewer = store.get_current_user()
_is_student = _viewer is not None and _viewer.is_student

st.info(
    "**Pointers, not answers.** Each question comes with a method pointer that "
    "names the approach - never a worked solution.",
    icon=":material/lightbulb:",
)

# ---------------------------------------------------------------------------
# Whose results to target
#
# Scoped by role: a student only ever sees their own history, and topic names
# drawn from their own question sets, never another student's.
# ---------------------------------------------------------------------------
if _viewer is None:
    _visible = []
    frame = analytics.results_dataframe([], [], [])
    whose = "your"
elif _is_student:
    _visible = service.list_assessments_for_student(_viewer.id)
    frame = analytics.student_dataframe(
        _viewer.id,
        service.list_grading_results(student_id=_viewer.id),
        _visible,
        service.list_submissions(student_id=_viewer.id),
    )
    whose = "your"
else:
    _visible = service.list_assessments_for_teacher()
    roster = service.list_students_for_teacher(_viewer.id)
    choices = {"Whole class": None, **{u.display_name: u.id for u in roster}}
    who = st.selectbox(
        "Whose results should the practice target?",
        list(choices.keys()),
        help="Only results you have reviewed count - unreviewed AI suggestions are left out.",
    )
    frame = analytics.results_dataframe(
        service.list_grading_results(), _visible, service.list_submissions()
    )
    if choices[who] is not None:
        frame = frame[frame["student_id"] == choices[who]]
        whose = f"{who}'s"
    else:
        whose = "the class's"

mode = st.radio(
    "How should the questions be chosen?",
    [FROM_RESULTS, BY_HAND],
    index=0 if not frame.empty else 1,
    horizontal=True,
)


def _render_question(question, reason: str = "") -> None:
    with st.container(border=True):
        st.markdown(f"**Question {question.number}.** {question.question_text}")
        st.caption(
            f"{question.topic} · {question.difficulty} · focus: {question.error_focus}"
        )
        if reason:
            st.markdown(f":material/target: **Why this question:** {reason}")
        with st.expander("Method pointer"):
            hint_note("How to go at it")
            st.markdown(question.method_hint)
            st.markdown(f"**Focus:** {question.skill_focus}")


def _download(questions, reasons, file_name: str) -> None:
    blocks = []
    for question, reason in zip(questions, reasons):
        block = f"Q{question.number}. {question.question_text}\nPointer: {question.method_hint}"
        if reason:
            block += f"\nWhy: {reason}"
        blocks.append(block)
    st.download_button(
        "Download as text",
        data="\n\n".join(blocks),
        file_name=file_name,
        mime="text/plain",
    )


# ---------------------------------------------------------------------------
# From results
# ---------------------------------------------------------------------------
if mode == FROM_RESULTS:
    if frame.empty:
        st.info(
            "There are no graded results to work from yet. "
            + (
                "Add a piece of work on My Work and come back, or choose a topic yourself."
                if _is_student
                else "Review some grading suggestions first, or choose a topic yourself."
            ),
            icon=":material/info:",
        )
    else:
        count = st.number_input(
            "Number of questions",
            min_value=1,
            max_value=targeted.MAX_TOTAL,
            value=targeted.DEFAULT_TOTAL,
            step=1,
        )
        plan = targeted.generate_targeted_practice(frame, total=int(count), whose=whose)

        with st.expander("What the results show"):
            st.dataframe(
                [
                    {
                        "Topic": e.topic,
                        "Average %": e.avg_percentage,
                        "Answers graded": e.responses,
                        "Most common errors": ", ".join(
                            f"{error.label} ({n})" for error, n in e.error_counts[:3]
                        )
                        or "None recorded",
                    }
                    for e in plan.evidence
                ],
                hide_index=True,
                width="stretch",
            )
            if plan.unsupported_topics:
                st.caption(
                    "No practice templates exist yet for "
                    + ", ".join(plan.unsupported_topics)
                    + ", so those topics were left out."
                )

        if plan.is_empty:
            st.info(
                "None of the graded topics have practice templates yet. Choose a "
                "topic yourself instead.",
                icon=":material/info:",
            )
        else:
            topics = list(dict.fromkeys(t.topic for t in plan.targets))
            st.subheader(f"{len(plan.items)} practice question(s) · {', '.join(topics)}")
            st.caption(
                "The same results always produce the same questions. New graded "
                "work changes the mix."
            )
            for item in plan.items:
                _render_question(item.question, item.reason)
            _download(
                [i.question for i in plan.items],
                [i.reason for i in plan.items],
                "practice_targeted.txt",
            )

# ---------------------------------------------------------------------------
# By hand
# ---------------------------------------------------------------------------
else:
    topics = practice_service.available_topics([a.topic for a in _visible])

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        topic = st.selectbox("Topic", topics, index=0)
    with col_b:
        error_label_map = {error.label: error for error in ErrorType}
        error_label = st.selectbox(
            "Error category to target",
            list(error_label_map.keys()),
            index=0,
            help="The generated questions carry a study tip aimed at this error type.",
        )
    with col_c:
        difficulty = st.selectbox("Difficulty", practice_service.DIFFICULTIES, index=1)
    with col_d:
        count = st.number_input(
            "Number of questions", min_value=1, max_value=10, value=3, step=1
        )

    st.caption(
        "The same selections always produce the same questions - the generator is "
        "deterministic, not random."
    )

    if st.button("Generate practice questions", type="primary"):
        st.session_state["practice_request"] = {
            "topic": topic,
            "error_type": error_label_map[error_label].value,
            "difficulty": difficulty,
            "count": int(count),
        }

    request = st.session_state.get("practice_request")

    if request:
        st.divider()
        try:
            questions = practice_service.generate_practice_questions(
                topic=request["topic"],
                error_type=ErrorType(request["error_type"]),
                difficulty=request["difficulty"],
                count=request["count"],
            )
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
        else:
            st.subheader(
                f"{len(questions)} practice question(s) · {request['topic']} · "
                f"{request['difficulty']}"
            )
            for question in questions:
                _render_question(question)
            _download(
                questions,
                [""] * len(questions),
                f"practice_{request['topic'].lower().replace(' ', '_')}_"
                f"{request['difficulty'].lower()}.txt",
            )
    else:
        st.info(
            "Choose a topic, an error category and a difficulty, then generate.",
            icon=":material/info:",
        )

privacy_notice()
