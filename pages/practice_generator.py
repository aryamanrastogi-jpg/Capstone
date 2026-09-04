"""Practice Generator - template-based follow-up questions (prototype)."""

from __future__ import annotations

import streamlit as st

from components.layout import page_header, privacy_notice
from models import ErrorType
from services import assessment_service as service
from services import practice_service

page_header(
    "Practice Generator",
    "Build targeted follow-up practice for a topic and an error pattern.",
    "Pick the error category your class struggled with most on the Analytics page, "
    "then generate practice that drills exactly that.",
)

st.warning(practice_service.GENERATOR_LABEL, icon=":material/construction:")

# Offer template topics first, plus any assessment topic that has templates.
assessment_topics = [a.topic for a in service.list_assessments()]
topics = practice_service.available_topics(assessment_topics)

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
    count = st.number_input("Number of questions", min_value=1, max_value=10, value=3, step=1)

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
            with st.container(border=True):
                st.markdown(f"**Question {question.number}.** {question.question_text}")
                with st.expander("Method hint and skill focus"):
                    st.markdown(f"**Method:** {question.method_hint}")
                    st.markdown(f"**Focus:** {question.skill_focus}")

        export = "\n\n".join(
            f"Q{q.number}. {q.question_text}\nMethod: {q.method_hint}" for q in questions
        )
        st.download_button(
            "Download as text",
            data=export,
            file_name=(
                f"practice_{request['topic'].lower().replace(' ', '_')}_"
                f"{request['difficulty'].lower()}.txt"
            ),
            mime="text/plain",
        )
else:
    st.info(
        "Choose a topic, an error category and a difficulty, then generate.",
        icon=":material/info:",
    )

privacy_notice()
