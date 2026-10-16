"""Read, edit and delete a saved question set.

Shared by My Questions (a student's own sets) and Create Assessment (a
teacher's). Creating stays on each page's own form; this is everything that
happens to a set after it exists.

WHY EDITING KEEPS IDS
  Work handed in on a set points at its question ids. The editor carries each
  question's id in a hidden column, so a question that is reworded or re-marked
  is updated in place and the answers and marks already given for it stay.
  Only a question that is removed takes its answers and marks with it, and the
  dialog says so before anything is saved.

WHY THE OPEN DIALOG LIVES IN SESSION STATE
  A dialog called only on the run where "Edit" was clicked disappears on the
  next full rerun. The page instead records which set is being edited and calls
  `render_open_editor` on every run until Save, Cancel or the close button
  clears it.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st
from pydantic import ValidationError as PydanticValidationError

from models import Assessment, User
from models.assessment import CURRICULA, GRADE_LEVELS, AssessmentType, Subject
from services import assessment_service as service
from utils.validation import total_marks, validate_assessment_draft

EDITING_KEY = "question_set_editing"
GENERATION_KEY = "question_set_editing_generation"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------
def question_list(
    assessment: Assessment, *, show_answers: bool, show_criteria: bool = False
) -> None:
    """The questions in order, with marks, and the answers for their owner."""
    for index, question in enumerate(assessment.questions, start=1):
        st.markdown(
            f"**Q{index}. ({question.max_marks:g} mark"
            f"{'s' if question.max_marks != 1 else ''})** {question.question_text}"
        )
        if show_answers:
            st.caption(
                f"Answer: {question.model_answer}"
                if question.has_model_answer
                else "No answer saved."
            )
        if show_criteria and question.marking_criteria:
            st.caption(f"Marking: {question.marking_criteria}")


def _work_count(assessment: Assessment, viewer: User) -> int:
    """How much handed-in work hangs off this set, as this viewer can see it."""
    return len(
        service.list_submissions(
            assessment_id=assessment.id,
            student_id=viewer.id if viewer.is_student else None,
        )
    )


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'s' if count != 1 else ''}"


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
def edit_button(assessment: Assessment, *, width: str = "stretch") -> None:
    """Open the edit dialog for this set on the next run."""

    def _open() -> None:
        st.session_state[EDITING_KEY] = assessment.id
        st.session_state[GENERATION_KEY] = st.session_state.get(GENERATION_KEY, 0) + 1

    st.button("Edit", key=f"edit_{assessment.id}", width=width, on_click=_open)


def _close() -> None:
    st.session_state.pop(EDITING_KEY, None)


def render_open_editor(
    assessments: list[Assessment], viewer: User, *, flash_key: str
) -> None:
    """Show the edit dialog if one of `assessments` is being edited."""
    editing = st.session_state.get(EDITING_KEY)
    if editing is None:
        return
    assessment = next((a for a in assessments if a.id == editing), None)
    if assessment is None or not service.can_edit(assessment, viewer):
        # Deleted, or not this viewer's to change: nothing to edit any more.
        _close()
        return
    if viewer.is_teacher:
        _edit_assessment_dialog(assessment, viewer, flash_key)
    else:
        _edit_question_set_dialog(assessment, viewer, flash_key)


@st.dialog("Edit assessment", width="large", on_dismiss=_close)
def _edit_assessment_dialog(assessment: Assessment, viewer: User, flash_key: str) -> None:
    _edit_form(assessment, viewer, flash_key, teacher=True)


@st.dialog("Edit question set", width="large", on_dismiss=_close)
def _edit_question_set_dialog(
    assessment: Assessment, viewer: User, flash_key: str
) -> None:
    _edit_form(assessment, viewer, flash_key, teacher=False)


def _index_of(options: list, value, fallback: int = 0) -> int:
    return options.index(value) if value in options else fallback


def _edit_form(
    assessment: Assessment, viewer: User, flash_key: str, *, teacher: bool
) -> None:
    prefix = f"qse_{assessment.id}_{st.session_state.get(GENERATION_KEY, 0)}"

    work = _work_count(assessment, viewer)
    if work:
        st.warning(
            f"{_plural(work, 'piece')} of work {'has' if work == 1 else 'have'} "
            "been handed in on this set. Edits apply to it too, and removing a "
            "question also removes the answers and marks given for it.",
            icon=":material/warning:",
        )

    col_a, col_b = st.columns(2)
    with col_a:
        title = st.text_input(
            "Assessment title *" if teacher else "Name *",
            value=assessment.title,
            key=f"{prefix}_title",
        )
        subject = st.selectbox(
            "Subject *",
            Subject.values(),
            index=_index_of(Subject.values(), assessment.subject.value),
            key=f"{prefix}_subject",
        )
        curriculum: Optional[str] = None
        if teacher:
            curriculum = st.selectbox(
                "Curriculum *",
                CURRICULA,
                index=_index_of(CURRICULA, assessment.curriculum),
                key=f"{prefix}_curriculum",
            )
    with col_b:
        topic = st.text_input("Topic *", value=assessment.topic, key=f"{prefix}_topic")
        type_label = st.selectbox(
            "Type of work *",
            AssessmentType.labels(),
            index=_index_of(AssessmentType.labels(), assessment.assessment_type.label),
            key=f"{prefix}_type",
        )
        grade_level: Optional[int] = None
        if teacher:
            grade_level = st.selectbox(
                "Grade level *",
                GRADE_LEVELS,
                index=_index_of(GRADE_LEVELS, assessment.grade_level),
                key=f"{prefix}_grade",
            )

    st.caption(
        "Change a cell to edit a question. Add one with the + row at the bottom; "
        "select a row and press the bin to remove it."
    )
    columns = ["id", "question_text", "model_answer"]
    if teacher:
        columns.append("marking_criteria")
    columns.append("max_marks")
    edited = st.data_editor(
        pd.DataFrame(service.question_rows(assessment), columns=columns),
        key=f"{prefix}_rows",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            # Hidden, but carried through: it is what keeps a question's
            # answers and marks attached to it when the question is edited.
            "id": None,
            "question_text": st.column_config.TextColumn(
                "Question *", width="large", default=""
            ),
            "model_answer": st.column_config.TextColumn(
                "Model answer *" if teacher else "Answer (optional)",
                width="large",
                default="",
            ),
            "marking_criteria": st.column_config.TextColumn(
                "Marking criteria", width="large", default=""
            ),
            "max_marks": st.column_config.NumberColumn(
                "Marks *",
                min_value=0.5,
                max_value=100.0,
                step=0.5,
                format="%.1f",
                default=1.0,
            ),
        },
    )
    rows = edited.fillna("").to_dict("records")
    st.caption(f"Total: {total_marks(rows):g} marks")

    save_col, cancel_col, _ = st.columns([1, 1, 2])
    save_clicked = save_col.button(
        "Save changes", key=f"{prefix}_save", type="primary", width="stretch"
    )
    if cancel_col.button("Cancel", key=f"{prefix}_cancel", width="stretch"):
        _close()
        st.rerun()

    if not save_clicked:
        return

    check = validate_assessment_draft(
        title=title,
        topic=topic,
        curriculum=curriculum or assessment.curriculum,
        questions=rows,
        require_model_answers=teacher,
        title_label="Assessment title" if teacher else "Name",
    )
    if not check.ok:
        st.error("Please fix the following before saving:", icon=":material/error:")
        for message in check.errors:
            st.markdown(f"- {message}")
        return

    try:
        saved = service.update_assessment(
            assessment,
            title=title,
            subject=subject,
            topic=topic,
            rows=rows,
            assessment_type=AssessmentType.from_label(type_label),
            curriculum=curriculum,
            grade_level=grade_level,
            # Only a student's own work freezes; a teacher may remove questions.
            protected_question_ids=(
                service.frozen_question_ids(assessment, viewer.id)
                if viewer.is_student
                else ()
            ),
        )
    except PydanticValidationError as exc:
        st.error("These changes could not be saved:", icon=":material/error:")
        for issue in exc.errors():
            field = " → ".join(str(part) for part in issue["loc"]) or "set"
            st.markdown(f"- **{field}**: {issue['msg']}")
    except ValueError as exc:
        st.error(str(exc), icon=":material/error:")
    except Exception:  # noqa: BLE001 - a database refusal, shown plainly
        st.error(
            "These changes could not be saved. "
            + (
                "Check that you are still signed in as a teacher, then try again."
                if teacher
                else "If your teacher has already reviewed work on this set, the "
                "questions they marked cannot be removed."
            ),
            icon=":material/error:",
        )
    else:
        _close()
        st.session_state[flash_key] = f"Saved changes to **{saved.title}**."
        st.rerun()


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
def delete_button(
    assessment: Assessment, viewer: User, *, confirm_key: str, flash_key: str
) -> None:
    """Delete in two clicks: Delete, then Yes, delete (BUG-021)."""
    if st.session_state.get(confirm_key) != assessment.id:
        if st.button("Delete", key=f"delete_{assessment.id}", width="stretch"):
            st.session_state[confirm_key] = assessment.id
            st.rerun()
        return

    work = _work_count(assessment, viewer)
    if not work:
        consequence = ""
    elif viewer.is_student:
        consequence = f" Your {_plural(work, 'attempt')} on it will be deleted too."
    else:
        consequence = (
            f" {_plural(work, 'piece')} of student work on it, and the marks, "
            "will be deleted too."
        )
    st.caption(f"Delete this set?{consequence} This cannot be undone.")
    if st.button(
        "Yes, delete",
        key=f"confirm_delete_{assessment.id}",
        type="primary",
        width="stretch",
    ):
        st.session_state.pop(confirm_key, None)
        try:
            service.delete_assessment(assessment.id)
        except Exception:  # noqa: BLE001 - a database refusal, shown plainly
            st.error(
                "This set could not be deleted. Refresh the page and try again.",
                icon=":material/error:",
            )
            return
        st.session_state[flash_key] = f"Deleted **{assessment.title}**."
        st.rerun()
    if st.button("Cancel", key=f"cancel_delete_{assessment.id}", width="stretch"):
        st.session_state.pop(confirm_key, None)
        st.rerun()
