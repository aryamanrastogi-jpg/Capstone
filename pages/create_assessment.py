"""Create Assessment - teacher authors questions, model answers and criteria."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from pydantic import ValidationError as PydanticValidationError

from components.layout import page_header, privacy_notice
from components.navigation import goto
from models.assessment import CURRICULA, GRADE_LEVELS, AssessmentType, Subject
from services import assessment_service as service
from services import state as store
from utils.validation import total_marks, validate_assessment_draft

EDITOR_KEY = "create_assessment_rows"
EDITOR_WIDGET_KEY = "ca_editor"
EDITOR_GENERATION_KEY = "ca_editor_generation"
JUST_SAVED_KEY = "create_assessment_just_saved"
RESET_AFTER_SAVE_KEY = "create_assessment_reset_after_save"

BLANK_ROWS = pd.DataFrame(
    [
        {"question_text": "", "model_answer": "", "marking_criteria": "", "max_marks": 1.0}
        for _ in range(3)
    ]
)


def _editor_widget_key() -> str:
    return f"{EDITOR_WIDGET_KEY}_{st.session_state.get(EDITOR_GENERATION_KEY, 0)}"


def _reset_editor() -> None:
    """Discard both the draft and Streamlit's cached value for its widget."""
    st.session_state[EDITOR_KEY] = BLANK_ROWS.copy()
    st.session_state.pop(_editor_widget_key(), None)
    st.session_state[EDITOR_GENERATION_KEY] = (
        st.session_state.get(EDITOR_GENERATION_KEY, 0) + 1
    )

# Teacher-only page. Navigation already keeps students out; this is the second
# line of defence if the page is reached directly.
_viewer = store.get_current_user()
if _viewer is None or not _viewer.is_teacher:
    st.error("Sign in as a teacher to use this page.", icon=":material/error:")
    st.stop()

page_header(
    "Create Assessment",
    "Define the questions, the model answers and how each mark is awarded.",
    "The marking criteria are what the grader compares each response against, so the more "
    "specific they are, the more useful the suggestions will be.",
)

# Widget values may only be changed before those widgets are instantiated.
# Successful saves schedule their reset for this next run.
if st.session_state.pop(RESET_AFTER_SAVE_KEY, False):
    _reset_editor()
    st.session_state["ca_title"] = ""
    st.session_state["ca_topic"] = ""

if EDITOR_KEY not in st.session_state:
    st.session_state[EDITOR_KEY] = BLANK_ROWS.copy()
st.session_state.setdefault(EDITOR_GENERATION_KEY, 0)


def _clear_form() -> None:
    """Runs as an on_click callback, i.e. before the widgets are created again,
    which is the only point where their session-state keys may be changed."""
    _reset_editor()
    st.session_state.pop(JUST_SAVED_KEY, None)
    for key in ("ca_title", "ca_topic"):
        st.session_state[key] = ""


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
    grade_level = st.selectbox("Grade level *", GRADE_LEVELS, index=3, key="ca_grade")
    assessment_type_label = st.selectbox(
        "Type of work *",
        AssessmentType.labels(),
        index=0,
        key="ca_type",
        help="Used to separate homework from exam performance in the analytics.",
    )

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
    key=_editor_widget_key(),
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
clear_col.button("Clear form", width="stretch", on_click=_clear_form)

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
                assessment_type=AssessmentType.from_label(assessment_type_label),
                # BUG-003: assessments_insert_own requires owner_id to be the
                # signed-in profile; an unowned set would also be visible to
                # every student.
                owner_id=_viewer.id,
            )
            service.save_assessment(assessment)
        except PydanticValidationError as exc:
            st.error("This assessment could not be saved:", icon=":material/error:")
            for issue in exc.errors():
                field = " → ".join(str(part) for part in issue["loc"]) or "assessment"
                st.markdown(f"- **{field}**: {issue['msg']}")
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
        except Exception:  # noqa: BLE001 - a database refusal, shown plainly
            st.error(
                "This assessment could not be saved. Check that you are still "
                "signed in as a teacher, then try again.",
                icon=":material/error:",
            )
        else:
            st.success(
                f"Saved **{assessment.title}** with {assessment.question_count} question{'s' if assessment.question_count != 1 else ''} "
                f"worth {assessment.max_marks} marks in total.",
                icon=":material/check_circle:",
            )
            st.session_state[RESET_AFTER_SAVE_KEY] = True
            st.session_state[JUST_SAVED_KEY] = True

# Outside `if save_clicked:` - the click on this button is a fresh run in which
# save_clicked is False, so the button has to survive that run to act on it.
if st.session_state.get(JUST_SAVED_KEY):
    if st.button("Go to Upload Responses"):
        st.session_state.pop(JUST_SAVED_KEY, None)
        goto("Upload Responses")

# ---------------------------------------------------------------------------
# Existing assessments
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Your assessments")

existing = service.list_assessments_for_teacher()
if not existing:
    st.info("No assessments saved yet.", icon=":material/info:")
else:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Title": a.title,
                    "Subject": a.subject.value,
                    "Type": a.assessment_type.label,
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
