"""My Class - the roster, from whichever side you are on.

One page, two views, because it is one relationship. A teacher manages who is in
their class; a student sees which class they are in and can leave it.

WHAT A TEACHER SEES OF A STUDENT HERE
  An anonymous code, a year group, and how much work they have submitted. No
  name and no email - the app never holds either, and this page is not the
  place to start.

TRY CHANGING THIS
  A teacher with a large class will want to sort the roster by "least work
  submitted" to find who has gone quiet. The data is already here.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.layout import empty_state, page_header, privacy_notice
from services import assessment_service, roster_service
from services import state as store

user = store.get_current_user()

if user is None:
    page_header("My Class")
    empty_state("Nobody is signed in.")
    st.stop()


# --------------------------------------------------------------------------
# Teacher view
# --------------------------------------------------------------------------
def _teacher_view() -> None:
    page_header(
        "My Class",
        "Who is in your class, and how they join.",
    )

    roster = roster_service.list_roster(user.id)
    code = roster_service.class_code(user.id)

    left, right = st.columns([2, 1])

    with right:
        st.markdown("#### Class code")
        if code:
            st.code(code, language=None)
            st.caption(
                "Students enter this on their My Class page to join. Share it "
                "however you normally share things with your class."
            )
        else:
            st.caption("You have not issued a class code yet.")

        label = "Issue a new code" if code else "Issue a class code"
        if st.button(label, type="primary", width="stretch"):
            new_code = roster_service.rotate_class_code(user.id)
            st.session_state["_roster_notice"] = f"New class code: {new_code}"
            st.rerun()

        if code:
            st.caption(
                ":material/info: Issuing a new code stops the old one working. "
                "Students already in your class stay in it."
            )

    with left:
        st.markdown(f"#### Students ({len(roster)})")

        if not roster:
            empty_state(
                "No students have joined yet.",
                hint="Issue a class code and give it to your class.",
            )
            return

        # One query, then counted in Python: a call per student would be a
        # round trip per row once this is on Supabase.
        submissions = assessment_service.list_submissions()
        counts: dict[str, int] = {}
        for submission in submissions:
            if submission.student_id:
                counts[submission.student_id] = counts.get(submission.student_id, 0) + 1

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Student": student.display_name,
                        "Year": student.year_group or "-",
                        "Pieces of work": counts.get(student.id, 0),
                    }
                    for student in roster
                ]
            ),
            hide_index=True,
            width="stretch",
        )

        with st.expander("Remove a student from this class"):
            st.caption(
                "Removing a student does not delete anything they have made. "
                "It stops their work appearing in your class views, and stops "
                "your assessments appearing for them."
            )
            chosen = st.selectbox(
                "Student",
                options=[s.id for s in roster],
                format_func=lambda sid: next(
                    s.display_name for s in roster if s.id == sid
                ),
            )
            if st.button("Remove from class"):
                outcome = roster_service.remove_from_roster(user.id, chosen)
                st.session_state["_roster_notice"] = outcome.message
                st.rerun()


# --------------------------------------------------------------------------
# Student view
# --------------------------------------------------------------------------
def _student_view() -> None:
    page_header("My Class", "Which class you are in.")

    if user.teacher_id:
        teacher = assessment_service.get_user(user.teacher_id)
        name = teacher.display_name if teacher else "your teacher"
        st.success(f"You are in {name}'s class.", icon=":material/groups:")
        st.caption(
            "That is why their assessments show up in My Work, and why they can "
            "see the work you submit."
        )

        with st.expander("Leave this class"):
            st.caption(
                "Your uploads and your own question sets stay yours and are not "
                "deleted. Your teacher stops seeing your work, and their "
                "assessments stop appearing for you."
            )
            if st.button("Leave class"):
                outcome = roster_service.leave_class(user.id)
                st.session_state["_roster_notice"] = outcome.message
                st.rerun()
        return

    st.info(
        "You are not in a class yet.",
        icon=":material/group_add:",
    )
    st.caption(
        "You can still upload your own work and type up your own questions "
        "without one. Joining a class adds your teacher's assessments, and "
        "lets them see how you are getting on."
    )

    with st.form("join_class"):
        code = st.text_input(
            "Class code",
            max_chars=6,
            placeholder="ABC234",
            help="Six characters. Your teacher will give you this.",
        )
        joined = st.form_submit_button("Join class", type="primary")

    if joined:
        outcome = roster_service.join_class(user.id, code)
        if outcome.ok:
            st.session_state["_roster_notice"] = outcome.message
            st.rerun()
        else:
            st.error(outcome.message, icon=":material/error:")


# --------------------------------------------------------------------------
notice = st.session_state.pop("_roster_notice", None)

if user.is_teacher:
    _teacher_view()
else:
    _student_view()

if notice:
    st.toast(notice)

st.divider()
privacy_notice()
