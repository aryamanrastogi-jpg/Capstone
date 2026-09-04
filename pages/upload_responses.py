"""Upload Responses - paste or upload an anonymised student response."""

from __future__ import annotations

import streamlit as st
from pydantic import ValidationError as PydanticValidationError

from components.layout import empty_state, page_header, privacy_notice
from components.navigation import goto
from services import assessment_service as service
from services import document_service
from services import state as store
from services.grading_service import grade_submission
from utils.config import ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_BYTES

EXTRACTED_KEY = "upload_extracted"

# Teacher-only page. Navigation already keeps students out; this is the second
# line of defence if the page is reached directly.
_viewer = store.get_current_user()
if _viewer is None or not _viewer.is_teacher:
    st.error("Sign in as a teacher to use this page.", icon=":material/error:")
    st.stop()

page_header(
    "Upload Responses",
    "Add a student response by pasting the text or uploading a file.",
    "Digital PDFs and plain text files are supported. Handwritten or scanned pages "
    "are not readable in this version.",
)

st.warning(
    "Use an anonymous student code such as S-8201. Do not enter real student names.",
    icon=":material/privacy_tip:",
)

assessments = service.list_assessments()
if not assessments:
    empty_state(
        "You need an assessment before you can add responses.",
        "Create one first, then come back to this page.",
        icon=":material/assignment_late:",
    )
    if st.button("Create an assessment", type="primary"):
        goto("Create Assessment")
    st.stop()

# ---------------------------------------------------------------------------
# Choose the assessment
# ---------------------------------------------------------------------------
labels = {a.id: f"{a.title} · Grade {a.grade_level} · {a.max_marks} marks" for a in assessments}
selected_id = st.selectbox(
    "Assessment *",
    options=list(labels.keys()),
    format_func=lambda key: labels[key],
)
assessment = service.get_assessment(selected_id)

if assessment is None:
    st.error("That assessment could not be found. Please pick another.", icon=":material/error:")
    st.stop()

with st.expander("View the questions in this assessment"):
    for index, question in enumerate(assessment.questions, start=1):
        st.markdown(f"**Q{index}. ({question.max_marks} marks)** {question.question_text}")

st.divider()

# ---------------------------------------------------------------------------
# Student identifier and response
# ---------------------------------------------------------------------------
teacher = store.get_current_user()
roster = service.list_students_for_teacher(teacher.id) if teacher else []

id_col, mode_col = st.columns([1, 1])
with id_col:
    if roster:
        # Picking from the roster links the submission to a student account, so
        # it shows up in their own progress view as well as yours.
        codes = {u.display_name: u.id for u in roster}
        student_identifier = st.selectbox(
            "Student *",
            options=list(codes.keys()),
            help="Anonymous codes only. Picking a student links this to their progress.",
        )
        selected_student_id = codes.get(student_identifier)
    else:
        student_identifier = st.text_input(
            "Anonymous student identifier *",
            placeholder="e.g. S-8201",
            max_chars=40,
            help="A code you can map back to a student privately. Never a real name.",
        )
        selected_student_id = None
with mode_col:
    input_mode = st.radio(
        "How is the response being provided?",
        ["Paste typed answer", "Upload a file"],
        horizontal=True,
    )

response_text = ""
uploaded_name = None

if input_mode == "Paste typed answer":
    st.session_state.pop(EXTRACTED_KEY, None)
    response_text = st.text_area(
        "Student response *",
        height=240,
        placeholder="Paste the full typed response here, covering every question.",
    )
else:
    allowed = ", ".join(sorted(ext.lstrip(".") for ext in ALLOWED_UPLOAD_EXTENSIONS))
    st.caption(
        f"Allowed file types: {allowed}. Maximum size: "
        f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
    )
    uploaded = st.file_uploader(
        "Response file",
        type=[ext.lstrip(".") for ext in sorted(ALLOWED_UPLOAD_EXTENSIONS)],
        accept_multiple_files=False,
    )

    if uploaded is not None:
        extraction = document_service.read_uploaded_file(uploaded)
        if extraction.success:
            st.session_state[EXTRACTED_KEY] = {
                "text": extraction.text,
                "filename": extraction.filename,
            }
            st.success(extraction.message, icon=":material/check_circle:")
        else:
            st.session_state.pop(EXTRACTED_KEY, None)
            st.error(extraction.message, icon=":material/error:")

    stored = st.session_state.get(EXTRACTED_KEY)
    if stored:
        uploaded_name = stored["filename"]
        st.markdown("**Preview of the extracted text** — edit it if the layout came out oddly.")
        response_text = st.text_area(
            "Extracted text *",
            value=stored["text"],
            height=240,
        )

st.divider()

# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------
grade_now = st.checkbox(
    "Run mock grading straight away",
    value=True,
    help="Produces AI recommendations for each question. Nothing is finalised until you "
    "review them on the Review Grading page.",
)

if st.button("Confirm submission", type="primary"):
    problems = []
    if not student_identifier.strip():
        problems.append("An anonymous student identifier is required.")
    if not (response_text or "").strip():
        problems.append("The response text is empty - paste an answer or upload a readable file.")

    if problems:
        st.error("Please fix the following:", icon=":material/error:")
        for problem in problems:
            st.markdown(f"- {problem}")
    else:
        try:
            submission = service.build_submission(
                assessment_id=assessment.id,
                student_identifier=student_identifier,
                submission_text=response_text,
                uploaded_filename=uploaded_name,
                student_id=selected_student_id,
            )
            service.save_submission(submission)
        except PydanticValidationError as exc:
            st.error("This submission could not be saved:", icon=":material/error:")
            for issue in exc.errors():
                st.markdown(f"- {issue['msg']}")
        else:
            if grade_now:
                for result in grade_submission(
                    assessment.questions, submission.submission_text, submission.id
                ):
                    service.save_grading_result(result)
                st.success(
                    f"Submission from **{submission.student_identifier}** saved and graded. "
                    "The suggestions are waiting for your review.",
                    icon=":material/check_circle:",
                )
            else:
                st.success(
                    f"Submission from **{submission.student_identifier}** saved.",
                    icon=":material/check_circle:",
                )

            st.session_state.pop(EXTRACTED_KEY, None)
            if st.button("Go to Review Grading"):
                goto("Review Grading")

# ---------------------------------------------------------------------------
# Existing submissions for this assessment
# ---------------------------------------------------------------------------
st.divider()
st.subheader(f"Responses recorded for '{assessment.title}'")

existing = service.list_submissions(assessment.id)
if not existing:
    empty_state("No responses recorded for this assessment yet.")
else:
    from components.status_badges import submission_status_label

    st.dataframe(
        [
            {
                "Student": s.student_identifier,
                "Source": s.uploaded_filename or "Typed / pasted",
                "Status": submission_status_label(s.status),
                "Submitted": s.submitted_at.strftime("%d %b %Y, %H:%M"),
            }
            for s in sorted(existing, key=lambda s: s.submitted_at, reverse=True)
        ],
        hide_index=True,
        width="stretch",
    )

privacy_notice()
