"""Create Assessment - teacher authors questions, model answers and criteria."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from pydantic import ValidationError as PydanticValidationError

from components.layout import page_header, privacy_notice
from components.navigation import goto
from models.assessment import CURRICULA, GRADE_LEVELS, Subject
from services import assessment_service as service
from utils.validation import total_marks, validate_assessment_draft

EDITOR_KEY = "create_assessment_rows"

BLANK_ROWS = pd.DataFrame(
    [
        {"question_text": "", "model_answer": "", "marking_criteria": "", "max_marks": 1.0}
        for _ in range(3)
    ]
)

page_header(
    "Create Assessment",
    "Define the questions, the model answers and how each mark is awarded.",
    "The marking criteria are what the grader compares each response against, so the more "
    "specific they are, the more useful the suggestions will be.",
)

if EDITOR_KEY not in st.session_state:
    st.session_state[EDITOR_KEY] = BLANK_ROWS.copy()

# ---------------------------------------------------------------------------
# Assessment details
# ---------------------------------------------------------------------------
st.subheader("Assessment details")

col_a, col_b = st.columns(2)
with col_a:
    title = st.text_input(
        "Assessment title *",
        placeholder="e.g. Linear Equations - Class Test 1",
        key="ca_title",
    )
    subject = st.selectbox(
        "Subject *",
        Subject.values(),
        index=0,
        key="ca_subject",
        help="Mathematics is the supported subject in this phase; others are placeholders.",
    )
    topic = st.text_input(
        "Topic *",
        placeholder="e.g. Linear Equations",
        key="ca_topic",
        help="Used to group analytics and to target practice questions.",
    )
with col_b:
    curriculum = st.selectbox("Curriculum *", CURRICULA, index=0, key="ca_curriculum")
    grade_level = st.selectbox("Grade level *", GRADE_LEVELS, index=1, key="ca_grade")

st.divider()

# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------
st.subheader("Questions")
st.caption(
    "Add one row per question. Use the + row at the bottom of the table to add more, "
    "and leave unused rows blank - they are ignored."
)

edited = st.data_editor(
    st.session_state[EDITOR_KEY],
    key="ca_editor",
    num_rows="dynamic",
    width="stretch",
    column_config={
        "question_text": st.column_config.TextColumn(
            "Question *", width="large", help="The question exactly as the students see it."
        ),
        "model_answer": st.column_config.TextColumn(
            "Model answer *",
            width="large",
            help="The full worked answer, including the method and the units.",
        ),
        "marking_criteria": st.column_config.TextColumn(
            "Marking criteria",
            width="large",
            help="How the marks are split, e.g. '1 mark for the formula, 1 for the value'.",
        ),
        "max_marks": st.column_config.NumberColumn(
            "Marks *", min_value=0.5, max_value=100.0, step=0.5, format="%.1f"
        ),
    },
)

rows = edited.fillna("").to_dict("records")
computed_total = total_marks(rows)

summary_a, summary_b = st.columns(2)
summary_a.metric("Questions entered", len([r for r in rows if str(r.get("question_text", "")).strip()]))
summary_b.metric("Total marks", computed_total)

st.divider()

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
save_col, clear_col, _ = st.columns([1, 1, 3])
save_clicked = save_col.button("Save assessment", type="primary", width="stretch")
clear_clicked = clear_col.button("Clear form", width="stretch")

if clear_clicked:
    st.session_state[EDITOR_KEY] = BLANK_ROWS.copy()
    for key in ("ca_title", "ca_topic"):
        st.session_state[key] = ""
    st.rerun()

if save_clicked:
    result = validate_assessment_draft(
        title=title, topic=topic, curriculum=curriculum, questions=rows
    )
    if not result.ok:
        st.error("Please fix the following before saving:", icon=":material/error:")
        for message in result.errors:
            st.markdown(f"- {message}")
    else:
        try:
            assessment = service.build_assessment(
                title=title,
                subject=subject,
                curriculum=curriculum,
                grade_level=grade_level,
                topic=topic,
                rows=rows,
            )
            service.save_assessment(assessment)
        except PydanticValidationError as exc:
            st.error("This assessment could not be saved:", icon=":material/error:")
            for issue in exc.errors():
                field = " → ".join(str(part) for part in issue["loc"]) or "assessment"
                st.markdown(f"- **{field}**: {issue['msg']}")
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
        else:
            st.success(
                f"Saved **{assessment.title}** with {assessment.question_count} question(s) "
                f"worth {assessment.max_marks} marks in total.",
                icon=":material/check_circle:",
            )
            st.session_state[EDITOR_KEY] = BLANK_ROWS.copy()
            if st.button("Go to Upload Responses"):
                goto("Upload Responses")

# ---------------------------------------------------------------------------
# Existing assessments
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Your assessments")

existing = service.list_assessments()
if not existing:
    st.info("No assessments saved yet.", icon=":material/info:")
else:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Title": a.title,
                    "Subject": a.subject.value,
                    "Curriculum": a.curriculum,
                    "Grade": a.grade_level,
                    "Topic": a.topic,
                    "Questions": a.question_count,
                    "Total marks": a.max_marks,
                }
                for a in sorted(existing, key=lambda a: a.created_at, reverse=True)
            ]
        ),
        hide_index=True,
        width="stretch",
    )

privacy_notice()
