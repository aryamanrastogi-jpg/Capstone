"""My Questions - a student types up their own set of questions.

WHY THIS PAGE EXISTS
  Until now a student could do nothing until a teacher had authored an
  assessment. That is backwards: the whole point of the app is that you bring
  the questions you have actually been set - a worksheet, a past paper, the
  problems at the end of the chapter - and work through them here.

MODEL ANSWERS ARE OPTIONAL HERE
  A student usually has the questions and nothing else. A set without model
  answers is saved and reusable, but it cannot be marked yet: the grader has
  nothing to compare a response against, and a score it invented would be
  worse than no score. The page says so plainly rather than quietly guessing.

TRY CHANGING THIS
  Add a "Duplicate" button next to Delete, so a student can base a new set on
  an old one.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from pydantic import ValidationError as PydanticValidationError

from components.layout import empty_state, page_header, privacy_notice
from components.navigation import goto
from models.assessment import CURRICULA, GRADE_LEVELS, AssessmentType, Subject
from services import assessment_service as service
from services import document_service
from services import state as store
from utils.config import ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_BYTES
from utils.validation import total_marks, validate_assessment_draft

EDITOR_KEY = "my_questions_rows"
EDITOR_WIDGET_KEY = "mq_editor"
EDITOR_GENERATION_KEY = "mq_editor_generation"
EXTRACTED_KEY = "my_questions_extracted"
FLASH_KEY = "my_questions_flash"
RESET_AFTER_SAVE_KEY = "my_questions_reset_after_save"
CONFIRM_DELETE_KEY = "my_questions_confirm_delete"

BLANK_ROWS = pd.DataFrame(
    [
        {"question_text": "", "model_answer": "", "max_marks": 1.0}
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

student = store.get_current_user()
if student is None or not student.is_student:
    st.error("Sign in as a student to use this page.", icon=":material/error:")
    st.stop()

page_header(
    "My Questions",
    f"Signed in as {student.display_name}",
    "Type up the questions you have been set - a worksheet, a past paper, the "
    "problems at the end of a chapter - and they become something you can work "
    "through and track.",
)

if st.session_state.pop(RESET_AFTER_SAVE_KEY, False):
    _reset_editor()
    st.session_state["mq_title"] = ""
    st.session_state["mq_topic"] = ""

st.info(
    "You do **not** need the answers. Add them only if you already have a mark "
    "scheme; without them a set is still saved, it just cannot be scored yet.",
    icon=":material/lightbulb:",
)

if EDITOR_KEY not in st.session_state:
    st.session_state[EDITOR_KEY] = BLANK_ROWS.copy()
st.session_state.setdefault(EDITOR_GENERATION_KEY, 0)

# A confirmation set just before an st.rerun() would never be seen, so it is
# carried across the rerun in session state and shown here.
_flash = st.session_state.pop(FLASH_KEY, None)
if _flash:
    st.success(_flash, icon=":material/check_circle:")


def _clear_form() -> None:
    """Runs as an on_click callback, i.e. before the widgets are created again,
    which is the only point where their session-state keys may be changed."""
    _reset_editor()
    st.session_state.pop(EXTRACTED_KEY, None)
    for key in ("mq_title", "mq_topic"):
        st.session_state[key] = ""

# ---------------------------------------------------------------------------
# Optional: start from a file
# ---------------------------------------------------------------------------
with st.expander("Start from a file instead of typing"):
    allowed = ", ".join(sorted(ext.lstrip(".") for ext in ALLOWED_UPLOAD_EXTENSIONS))
    st.caption(
        f"Allowed: {allowed}. Max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
        "Photos of handwriting are not readable yet. The text is pulled out for "
        "you to split into questions - it is not split automatically."
    )
    uploaded = st.file_uploader("Your question paper", type=["txt", "pdf"])
    if uploaded is not None:
        extraction = document_service.read_uploaded_file(uploaded)
        if extraction.success:
            st.session_state[EXTRACTED_KEY] = extraction.text
            st.success(extraction.message, icon=":material/check_circle:")
        else:
            st.session_state.pop(EXTRACTED_KEY, None)
            st.error(extraction.message, icon=":material/error:")

    if st.session_state.get(EXTRACTED_KEY):
        st.markdown("**What we read** — copy each question into the table below.")
        st.text_area(
            "Extracted text",
            value=st.session_state[EXTRACTED_KEY],
            height=200,
            disabled=True,
        )

st.divider()

# ---------------------------------------------------------------------------
# Set details
# ---------------------------------------------------------------------------
st.subheader("About this set")

col_a, col_b = st.columns(2)
with col_a:
    title = st.text_input(
        "Give it a name *",
        placeholder="e.g. Algebra worksheet 4",
        key="mq_title",
    )
    subject = st.selectbox("Subject *", Subject.values(), index=0, key="mq_subject")
with col_b:
    topic = st.text_input(
        "Topic *",
        placeholder="e.g. Linear Equations",
        key="mq_topic",
        help="This is what groups your progress, so keep it consistent.",
    )
    assessment_type_label = st.selectbox(
        "Type of work *", AssessmentType.labels(), index=0, key="mq_type"
    )

st.divider()

# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------
st.subheader("The questions")
st.caption(
    "One row per question. Use the + at the bottom of the table to add more, and "
    "leave unused rows blank - they are ignored."
)

edited = st.data_editor(
    st.session_state[EDITOR_KEY],
    key=_editor_widget_key(),
    num_rows="dynamic",
    width="stretch",
    column_config={
        "question_text": st.column_config.TextColumn(
            "Question *", width="large", help="The question as it was set."
        ),
        "model_answer": st.column_config.TextColumn(
            "Answer (optional)",
            width="large",
            help="Only if you have the mark scheme. Leave blank otherwise.",
        ),
        "max_marks": st.column_config.NumberColumn(
            "Marks *", min_value=0.5, max_value=100.0, step=0.5, format="%.1f"
        ),
    },
)

rows = edited.fillna("").to_dict("records")
entered = [r for r in rows if str(r.get("question_text", "")).strip()]
with_answers = [r for r in entered if str(r.get("model_answer", "")).strip()]

summary_a, summary_b, summary_c = st.columns(3)
summary_a.metric("Questions", len(entered))
summary_b.metric("Total marks", total_marks(rows))
summary_c.metric(
    "With answers",
    f"{len(with_answers)}/{len(entered)}" if entered else "—",
    help="A set can only be scored once every question has an answer to mark against.",
)

save_col, clear_col, _ = st.columns([1, 1, 3])
save_clicked = save_col.button("Save this set", type="primary", width="stretch")
clear_col.button("Clear form", width="stretch", on_click=_clear_form)

if save_clicked:
    result = validate_assessment_draft(
        title=title,
        topic=topic,
        curriculum=CURRICULA[0],
        questions=rows,
        # The point of this page: a student has the questions, not the answers.
        require_model_answers=False,
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
                curriculum=CURRICULA[0],
                grade_level=student.year_group or GRADE_LEVELS[0],
                topic=topic,
                rows=rows,
                assessment_type=AssessmentType.from_label(assessment_type_label),
                owner_id=student.id,
                student_created=True,
            )
            service.save_assessment(assessment)
        except PydanticValidationError as exc:
            st.error("This set could not be saved:", icon=":material/error:")
            for issue in exc.errors():
                field = " → ".join(str(part) for part in issue["loc"]) or "set"
                st.markdown(f"- **{field}**: {issue['msg']}")
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
        else:
            st.session_state[RESET_AFTER_SAVE_KEY] = True
            st.session_state.pop(EXTRACTED_KEY, None)
            st.success(
                f"Saved **{assessment.title}** — {assessment.question_count} "
                f"question{'s' if assessment.question_count != 1 else ''}, {assessment.max_marks:g} marks.",
                icon=":material/check_circle:",
            )
            if assessment.is_gradable:
                st.info(
                    "Every question has an answer, so you can work through this "
                    "set on **My Work** and get an estimate.",
                    icon=":material/check:",
                )
            else:
                st.warning(
                    "No answers on this set yet, so it cannot be scored. Add them "
                    "when you have the mark scheme.",
                    icon=":material/info:",
                )

st.divider()

# ---------------------------------------------------------------------------
# Sets this student has already saved
# ---------------------------------------------------------------------------
st.subheader("Your saved sets")

mine = service.list_assessments_owned_by(student.id)
if not mine:
    # No early stop: the shared library below is exactly what a student with
    # nothing of their own should be looking at.
    empty_state(
        "You have not saved any question sets yet.",
        "Add one above, or take a copy of someone else's from the library below.",
        icon=":material/inbox:",
    )

for assessment in sorted(mine, key=lambda a: a.created_at, reverse=True):
    with st.container(border=True):
        detail_col, action_col = st.columns([4, 1])
        with detail_col:
            st.markdown(f"**{assessment.title}**")
            st.caption(
                f"{assessment.topic} · {assessment.assessment_type.label} · "
                f"{assessment.question_count} question{'s' if assessment.question_count != 1 else ''} · "
                f"{assessment.max_marks:g} marks · "
                f"saved {assessment.created_at.strftime('%d %b %Y')}"
            )
            if assessment.is_gradable:
                st.caption(":material/check_circle: Ready to score.")
            else:
                missing = len(assessment.questions_missing_model_answers)
                st.caption(
                    f":material/info: {missing} question{'s have' if missing != 1 else ' has'} no answer, so "
                    "this set cannot be scored yet."
                )
            if assessment.is_copy:
                st.caption(":material/content_copy: Copied from the shared library.")

            # Sharing is always a deliberate act, and always reversible.
            shared = st.toggle(
                "Share with other students",
                value=assessment.is_shared,
                key=f"share_{assessment.id}",
                help="Puts the questions in the shared library so anyone can take "
                "a copy. Your answers and your scores are never shared.",
            )
            if shared != assessment.is_shared:
                service.set_shared(assessment.id, shared)
                st.rerun()
        with action_col:
            # Destructive, so it takes two clicks: Delete, then confirm.
            if st.session_state.get(CONFIRM_DELETE_KEY) == assessment.id:
                st.caption("Delete this set? This cannot be undone.")
                if st.button(
                    "Yes, delete",
                    key=f"confirm_delete_{assessment.id}",
                    type="primary",
                    width="stretch",
                ):
                    service.delete_assessment(assessment.id)
                    st.session_state.pop(CONFIRM_DELETE_KEY, None)
                    st.session_state[FLASH_KEY] = f"Deleted **{assessment.title}**."
                    st.rerun()
                if st.button(
                    "Cancel", key=f"cancel_delete_{assessment.id}", width="stretch"
                ):
                    st.session_state.pop(CONFIRM_DELETE_KEY, None)
                    st.rerun()
            elif st.button("Delete", key=f"delete_{assessment.id}", width="stretch"):
                st.session_state[CONFIRM_DELETE_KEY] = assessment.id
                st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# The shared library
# ---------------------------------------------------------------------------
st.subheader("Shared library")
st.caption(
    "Question sets other students have shared. Take a copy and it becomes yours "
    "— your own attempts, your own progress, and nothing you do touches theirs."
)

library = service.list_shared_library(exclude_owner_id=student.id)
if not library:
    empty_state(
        "Nobody has shared a question set yet.",
        "Share one of yours above and it will show up here for everyone else.",
        icon=":material/library_books:",
    )
else:
    for assessment in library:
        with st.container(border=True):
            detail_col, action_col = st.columns([4, 1])
            with detail_col:
                st.markdown(f"**{assessment.title}**")
                st.caption(
                    f"{assessment.topic} · {assessment.assessment_type.label} · "
                    f"{assessment.question_count} question{'s' if assessment.question_count != 1 else ''} · "
                    f"{assessment.max_marks:g} marks"
                )
                st.caption(
                    ":material/info: Answers are never copied, so a copy gives "
                    "you guidance rather than a score until you add your own."
                )
                with st.expander("See the questions"):
                    for index, question in enumerate(assessment.questions, start=1):
                        st.markdown(
                            f"**Q{index}. ({question.max_marks:g} marks)** "
                            f"{question.question_text}"
                        )
            with action_col:
                if st.button(
                    "Take a copy", key=f"copy_{assessment.id}", width="stretch"
                ):
                    copy = service.copy_assessment_to(assessment, student.id)
                    st.session_state[FLASH_KEY] = f"Copied **{copy.title}** into your sets."
                    st.rerun()

if st.button("Go to My Work", type="primary"):
    goto("My Work")

privacy_notice()
