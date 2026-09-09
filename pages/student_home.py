"""My Work - the student's landing page.

WHAT THIS FILE DOES
  Lets a student upload a past piece of work (homework, exercise, mock exam),
  runs the mock grader over it, and shows an AI *estimate* plus pointers.

WHAT IT DELIBERATELY DOES NOT DO
  It never shows the model answer or the marking scheme. Everything the student
  sees goes through `grading_service.student_safe_view`, which strips anything
  that would turn the app into a way of getting homework answers.

TRY CHANGING THIS
  Swap the `st.metric` for `st.progress` and see how the estimate reads.
"""

from __future__ import annotations

import streamlit as st
from pydantic import ValidationError as PydanticValidationError

from components.layout import empty_state, metric_row, page_header, privacy_notice
from components.navigation import goto
from components.status_badges import confidence_badge, error_chip
from services import analytics_service as analytics
from services import assessment_service as service
from services import document_service
from services import state as store
from services.grading_service import grade_submission, student_safe_view
from utils.config import ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_BYTES

EXTRACTED_KEY = "student_upload_extracted"

student = store.get_current_user()
if student is None or not student.is_student:
    st.error("Sign in as a student to use this page.", icon=":material/error:")
    st.stop()

page_header(
    "My Work",
    f"Signed in as {student.display_name}",
    "Add work you have already done and get an instant estimate of how it would "
    "score, plus what to work on. Your teacher's mark is always the real one.",
)

st.info(
    "AssessAI gives you **pointers, not answers**. It will tell you where you went "
    "wrong and what to practise - it will not do your homework for you.",
    icon=":material/lightbulb:",
)

# ---------------------------------------------------------------------------
# Where the student currently stands
# ---------------------------------------------------------------------------
assessments = service.list_assessments_for_student(student.id)
my_submissions = service.list_submissions(student_id=student.id)
my_results = service.list_grading_results(student_id=student.id)
frame = analytics.student_dataframe(student.id, my_results, assessments, my_submissions)

average = round(float(frame["percentage"].mean()), 1) if not frame.empty else None
weakest = analytics.weakest_topics(frame, limit=1)

metric_row(
    [
        ("Pieces of work", len(my_submissions), "Everything you have added so far."),
        (
            "Average score",
            f"{average}%" if average is not None else "—",
            "Across every question you have uploaded.",
        ),
        (
            "Topics covered",
            frame["topic"].nunique() if not frame.empty else 0,
            "More topics means a more reliable picture.",
        ),
        (
            "Weakest topic",
            weakest[0] if weakest else "—",
            "Where a study camp would help most.",
        ),
    ]
)

if weakest:
    action_a, action_b = st.columns([3, 1])
    with action_a:
        st.warning(
            f"**{weakest[0]}** is your weakest topic right now.",
            icon=":material/priority_high:",
        )
    with action_b:
        if st.button("Build a study camp", type="primary", width="stretch"):
            goto("Study Camp")

st.divider()

# ---------------------------------------------------------------------------
# Add a piece of work
# ---------------------------------------------------------------------------
st.subheader("Add a piece of work")

if not assessments:
    empty_state(
        "There are no question sets to work from yet.",
        "Type up the questions you have been set on My Questions, then come back "
        "here to work through them.",
        icon=":material/assignment_late:",
    )
    if st.button("Add my questions", type="primary"):
        goto("My Questions")
    privacy_notice()
    st.stop()

labels = {
    a.id: (
        f"{a.title} · {a.assessment_type.label} · {a.topic}"
        + (" · mine" if a.student_created else "")
    )
    for a in assessments
}
selected_id = st.selectbox(
    "Which piece of work is this?",
    options=list(labels.keys()),
    format_func=lambda key: labels[key],
)
assessment = service.get_assessment(selected_id)
if assessment is None:
    st.error("That assessment could not be found.", icon=":material/error:")
    st.stop()

if not assessment.is_gradable:
    # Scoring needs something to mark against. Rather than invent a number, say
    # so - and point at the one thing that would fix it.
    missing = len(assessment.questions_missing_model_answers)
    st.warning(
        f"**{assessment.title}** cannot be scored yet: {missing} question(s) have "
        "no answer to mark against. Add the answers on My Questions when you have "
        "the mark scheme.",
        icon=":material/info:",
    )
    with st.expander("See the questions", expanded=True):
        for index, question in enumerate(assessment.questions, start=1):
            st.markdown(
                f"**Q{index}. ({question.max_marks:g} marks)** {question.question_text}"
            )
    if st.button("Add the answers", type="primary"):
        goto("My Questions")
    privacy_notice()
    st.stop()

with st.expander("See the questions"):
    for index, question in enumerate(assessment.questions, start=1):
        st.markdown(f"**Q{index}. ({question.max_marks} marks)** {question.question_text}")

mode = st.radio(
    "How do you want to add your answers?",
    ["Question by question", "One block of text", "Upload a file"],
    horizontal=True,
    help="Answering question by question is better: it lets AssessAI tell you "
    "exactly which questions to try again.",
)

response_text = ""
uploaded_name = None
# question_id -> answer. Stays None unless the student answers per question,
# which is what tells the grader to mark each question on its own.
answers: dict[str, str] | None = None

if mode == "Question by question":
    st.session_state.pop(EXTRACTED_KEY, None)
    st.caption(
        "Leave a question blank if you did not attempt it — that is useful "
        "information, not a problem."
    )
    answers = {}
    for index, question in enumerate(assessment.questions, start=1):
        answers[question.id] = st.text_area(
            f"Q{index}. ({question.max_marks:g} marks) {question.question_text}",
            height=120,
            key=f"answer_{assessment.id}_{question.id}",
            placeholder="Your answer, including your working.",
        )
    response_text = "\n".join(a for a in answers.values() if a.strip())
elif mode == "One block of text":
    st.session_state.pop(EXTRACTED_KEY, None)
    response_text = st.text_area(
        "Your answers",
        height=200,
        placeholder="Write out what you answered, including your working.",
    )
else:
    allowed = ", ".join(sorted(ext.lstrip(".") for ext in ALLOWED_UPLOAD_EXTENSIONS))
    st.caption(
        f"Allowed: {allowed}. Max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
        "Photos of handwriting are not readable yet."
    )
    uploaded = st.file_uploader("Your work", type=["txt", "pdf"])
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
        st.markdown("**What we read from your file** — fix anything that came out wrong.")
        response_text = st.text_area("Your answers", value=stored["text"], height=200)

known_mark = st.checkbox(
    "My teacher already marked this",
    help="Adding the mark you were given lets AssessAI flag if it reads the work "
    "very differently - worth asking your teacher about.",
)
teacher_mark = None
if known_mark:
    teacher_mark = st.number_input(
        f"Mark your teacher gave (out of {assessment.max_marks})",
        min_value=0.0,
        max_value=float(assessment.max_marks),
        value=0.0,
        step=0.5,
    )

if st.button("Get my estimate", type="primary"):
    if not (response_text or "").strip():
        st.error(
            "Add your answers first - type them in or upload a readable file.",
            icon=":material/error:",
        )
    else:
        try:
            submission = service.build_submission(
                assessment_id=assessment.id,
                student_identifier=student.display_name,
                # Left empty for a per-question submission so the service
                # composes a properly numbered transcript from the answers.
                submission_text="" if answers else response_text,
                answers=answers,
                questions=assessment.questions,
                uploaded_filename=uploaded_name,
                student_id=student.id,
                is_self_study=True,
                teacher_awarded_score=teacher_mark,
            )
            service.save_submission(submission)
        except PydanticValidationError as exc:
            st.error("That could not be saved:", icon=":material/error:")
            for issue in exc.errors():
                st.markdown(f"- {issue['msg']}")
        else:
            for result in grade_submission(
                assessment.questions,
                submission.submission_text,
                submission.id,
                answers=submission.answers or None,
            ):
                service.save_grading_result(result)
            st.session_state.pop(EXTRACTED_KEY, None)
            st.success(
                "Added. Your estimate is below.", icon=":material/check_circle:"
            )
            st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Recent work and its estimates
# ---------------------------------------------------------------------------
st.subheader("Your recent work")

if not my_submissions:
    empty_state(
        "You have not added any work yet.",
        "Add a piece above and you will get an estimate straight away.",
        icon=":material/inbox:",
    )
    privacy_notice()
    st.stop()

recent = sorted(my_submissions, key=lambda s: s.submitted_at, reverse=True)[:5]
assessments_by_id = {a.id: a for a in assessments}

for submission in recent:
    parent = assessments_by_id.get(submission.assessment_id)
    if parent is None:
        continue
    results = service.list_grading_results(submission_id=submission.id)
    if not results:
        continue

    awarded = sum(r.suggested_score for r in results)
    available = sum(r.max_marks for r in results)
    official = all(r.is_finalised for r in results)

    header = (
        f"{parent.title} · {submission.submitted_at.strftime('%d %b %Y')} · "
        f"{awarded:g}/{available:g}"
    )
    with st.expander(header, expanded=submission is recent[0]):
        if official:
            st.success(
                "Your teacher has reviewed this, so these are real marks.",
                icon=":material/verified:",
            )
        else:
            st.info(
                "This is an **AI estimate**, not a real mark. Your teacher decides "
                "your actual grade.",
                icon=":material/smart_toy:",
            )

        for index, result in enumerate(results, start=1):
            question = parent.get_question(result.question_id)
            if question is None:
                continue
            view = student_safe_view(result, question)

            st.markdown(f"**Q{index}.** {view['question_text']}")
            score_col, detail_col = st.columns([1, 3])
            with score_col:
                st.metric(
                    "Estimate" if view["is_estimate"] else "Mark",
                    f"{view['score']:g} / {view['max_marks']:g}",
                )
                confidence_badge(view["confidence"])
            with detail_col:
                st.markdown("*What went well*")
                for item in view["strengths"]:
                    st.markdown(f"- {item}")
                if view["error_labels"]:
                    st.markdown("*What to look at*")
                    st.markdown(
                        " ".join(error_chip(label, render=False) for label in view["error_labels"]),
                        unsafe_allow_html=True,
                    )
                st.markdown("*Next steps*")
                for pointer in view["pointers"]:
                    st.markdown(f"- {pointer}")
            if index < len(results):
                st.markdown("---")

privacy_notice()
