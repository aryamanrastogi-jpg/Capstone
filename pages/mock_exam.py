"""Mock Exam - a timed paper on the topics a student has been revising.

WHAT THIS FILE DOES
  Lets a student pick topics (the Study Camp's by default), sit a timed paper
  built from questions that have model answers, and see an AI-estimated score
  next to their starting point on the same topics.

WHERE THE LOGIC LIVES
  `mock_exam_service` builds the paper, keeps time from timestamps and marks it
  with the ordinary grader. This file only collects answers and draws results.

TRY CHANGING THIS
  `MINUTES_PER_QUESTION` in services/mock_exam_service.py sets the time limit.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from components import charts
from components.layout import empty_state, metric_row, page_header, privacy_notice
from components.navigation import goto
from services import analytics_service as analytics
from services import assessment_service as service
from services import mock_exam_service as exams
from services import state as store
from services import study_camp_service as camps
from utils import palette

TEAL = palette.PRIMARY
NAVY = palette.PRIMARY_DARK

student = store.get_current_user()
if student is None or not student.is_student:
    st.error("Sign in as a student to use this page.", icon=":material/error:")
    st.stop()

page_header(
    "Mock Exam",
    "A timed paper to check whether the revision worked.",
    "Pick your topics, answer against the clock, and compare the result with "
    "where you started.",
)

assessments = service.list_assessments_for_student(student.id)
frame = analytics.student_dataframe(
    student.id,
    service.list_grading_results(student_id=student.id),
    assessments,
    service.list_submissions(student_id=student.id),
)

exam = store.get_mock_exam()
if exam is not None and exam.student_id != student.id:
    exam = None


def _answer_key(question_id: str) -> str:
    return f"mock_answer_{exam.id}_{question_id}"


def _save_to_history(paper) -> None:
    """Save the handed-in paper as the student's work. A failure is shown on
    the results screen with a way to try again; the paper itself is kept."""
    try:
        exams.save_to_history(paper, service.student_label(student.display_name), assessments)
    except Exception:  # noqa: BLE001 - shown plainly, with a retry
        paper.save_failed = True


# ---------------------------------------------------------------------------
# No exam yet: set one up
# ---------------------------------------------------------------------------
if exam is None:
    options = exams.available_topics(assessments)
    if not options:
        empty_state(
            "There are no questions with model answers to build a mock exam from yet.",
            "Mock exams can only use questions the grader can mark.",
            icon=":material/inventory_2:",
        )
        if st.button("Go to Study Camp", type="primary"):
            goto("Study Camp")
        privacy_notice()
        st.stop()

    camp = service.active_camp_for(student.id)
    if camp is not None:
        defaults = exams.default_topics(camp.topics, assessments)
        # Only what was really pre-selected: a camp topic with no markable
        # questions in your sets cannot be on the paper.
        if defaults:
            st.info(
                "Pre-selected from your study camp: **" + "**, **".join(defaults) + "**.",
                icon=":material/local_fire_department:",
            )
    else:
        suggested = (
            analytics.weakest_topics(frame, limit=3, ceiling=camps.WEAKNESS_CEILING)
            if not frame.empty
            else []
        )
        defaults = [t for t in suggested if t in options]

    st.subheader("Set up your paper")
    chosen = st.multiselect(
        "Topics",
        options=options,
        default=defaults,
        help="Only topics with markable questions are listed.",
    )
    count = st.slider(
        "Number of questions",
        min_value=1,
        max_value=exams.MAX_QUESTION_COUNT,
        value=exams.DEFAULT_QUESTION_COUNT,
    )
    st.caption(
        f"You get {exams.MINUTES_PER_QUESTION} minutes per question. The clock starts "
        "when you press start. While the paper is open, use Submit or Abandon to leave."
    )

    if st.button("Start the mock exam", type="primary", disabled=not chosen):
        try:
            new_exam = exams.build_exam(student.id, assessments, chosen, frame, question_count=count)
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
        else:
            store.set_mock_exam(new_exam)
            st.rerun()

    privacy_notice()
    st.stop()

# ---------------------------------------------------------------------------
# Exam in progress
# ---------------------------------------------------------------------------
if not exam.is_submitted:
    st.subheader("Your paper")
    st.caption(
        f"{len(exam.items)} questions · {exam.total_marks:g} marks · "
        f"{exam.time_limit_minutes} minutes · {', '.join(exam.topics)}"
    )

    @st.fragment(run_every=1)
    def _clock() -> None:
        remaining = exams.seconds_remaining(exam)
        if remaining > 0:
            st.metric("Time remaining", exams.format_remaining(remaining))
            st.progress(remaining / (exam.time_limit_minutes * 60))
        else:
            st.warning(
                "Time is up. Submit now - answers handed in late are marked but "
                "flagged as over time.",
                icon=":material/timer_off:",
            )

    _clock()

    def _keep_answer(question_id: str) -> None:
        """Copy a draft answer onto the exam itself. Streamlit deletes a widget's
        state when the student moves to another page, but the exam object lives
        in session state, so the answer survives the trip there and back."""
        exam.answers[question_id] = st.session_state.get(_answer_key(question_id), "")

    for number, item in enumerate(exam.items, start=1):
        st.markdown(
            f"**{number}.** {item.question.question_text}  \n"
            f"*{item.topic} · {item.question.max_marks:g} marks*"
        )
        key = _answer_key(item.question.id)
        if key not in st.session_state:
            # Back from another page: restore the draft before the widget draws.
            st.session_state[key] = exam.answers.get(item.question.id, "")
        st.text_area(
            f"Answer to question {number}",
            key=key,
            label_visibility="collapsed",
            placeholder="Show your working.",
            on_change=_keep_answer,
            args=(item.question.id,),
        )

    answers = {
        item.question.id: st.session_state.get(_answer_key(item.question.id), "")
        for item in exam.items
    }
    blank_count = sum(1 for text in answers.values() if not (text or "").strip())
    confirm_key = f"mock_confirm_blank_{exam.id}"

    def _submit() -> None:
        st.session_state.pop(confirm_key, None)
        try:
            exams.submit_exam(exam, answers)
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
        else:
            _save_to_history(exam)
            st.rerun()

    # A blank answer scores 0 and the paper is compared as a real result, so
    # handing in with gaps takes a second, deliberate click.
    if st.session_state.get(confirm_key) and blank_count:
        st.warning(
            f"{blank_count} of {len(exam.items)} question(s) are blank and will "
            "score 0. Submit anyway?",
            icon=":material/warning:",
        )
        confirm_col, back_col = st.columns([1, 1])
        if confirm_col.button("Submit anyway", type="primary", width="stretch"):
            _submit()
        if back_col.button("Keep working", width="stretch"):
            st.session_state.pop(confirm_key, None)
            st.rerun()

    col_a, col_b = st.columns([3, 1])
    with col_a:
        if st.button("Submit my answers", type="primary"):
            if blank_count:
                st.session_state[confirm_key] = True
                st.rerun()
            else:
                _submit()
    with col_b:
        if st.button("Abandon", width="stretch"):
            store.set_mock_exam(None)
            st.rerun()

    privacy_notice()
    st.stop()

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
summary = exams.score_summary(exam, frame)
baseline = summary["baseline"]
change = summary["change"]

st.subheader("Your result")
st.info(
    "These scores are AI estimates from an automated grader, not a teacher's "
    "mark. Use them to see where to focus next.",
    icon=":material/gavel:",
)
if exam.saved_submission_ids:
    st.caption(
        ":material/check_circle: Saved to your work as a mock exam. It now counts "
        "in My Progress and Study Camp, and uses none of your attempts on the sets "
        "its questions came from."
    )
else:
    st.warning(
        "This result could not be saved to My Progress just now. It is still "
        "here until you leave or refresh the page.",
        icon=":material/cloud_off:",
    )
    if st.button("Save it now", key=f"mock_save_{exam.id}"):
        _save_to_history(exam)
        st.rerun()
if exam.ai_unavailable:
    st.warning(
        "The AI marker was busy (it has a free daily limit), so the simpler "
        "built-in marker made these estimates - they are rougher than usual.",
        icon=":material/hourglass_top:",
    )
if summary["late"]:
    st.warning(
        "This paper was submitted after the time limit, so the score is not a "
        "timed result.",
        icon=":material/timer_off:",
    )

metric_row(
    [
        ("Estimated score", f"{summary['score']:g}/{summary['max_score']:g}", "AI estimate."),
        ("Percentage", f"{summary['percentage']}%", "AI estimate across the paper."),
        (
            "Starting point",
            f"{baseline}%" if baseline is not None else "—",
            "Your average on these topics before the exam.",
        ),
        (
            "Change",
            f"{change:+g} pts" if change is not None else "—",
            "Percentage points against your starting point.",
        ),
    ]
)

rows = [t for t in summary["topics"] if t["before"] is not None]
if rows:
    figure = go.Figure()
    figure.add_bar(
        name="Before",
        x=[t["topic"] for t in rows],
        y=[t["before"] for t in rows],
        marker_color=palette.PRIMARY,
    )
    figure.add_bar(
        name="Mock exam",
        x=[t["topic"] for t in rows],
        y=[t["after"] for t in rows],
        marker_color=palette.ORANGE,
    )
    figure.update_layout(barmode="group", yaxis=dict(range=[0, 105], title="Score (%)"))
    charts.render(figure, height=300)

st.markdown("#### Feedback by question")
st.caption("Pointers on where to look again - not worked answers.")
by_id = {r.question_id: r for r in exam.results}
for number, item in enumerate(exam.items, start=1):
    result = by_id.get(item.question.id)
    if result is None:
        continue
    with st.expander(
        f"{number}. {item.topic} · estimated {result.suggested_score:g}/{result.max_marks:g}"
    ):
        st.markdown(item.question.question_text)
        st.markdown("**Your answer**")
        st.text(exam.answers.get(item.question.id) or "(left blank)")
        if result.student_feedback:
            st.markdown("**Pointers**")
            st.markdown(result.student_feedback)

if st.button("Take another mock exam", type="primary"):
    store.set_mock_exam(None)
    st.rerun()

privacy_notice()
