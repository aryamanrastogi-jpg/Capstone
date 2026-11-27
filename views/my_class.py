"""My Class - the roster, from whichever side you are on.

One page, two views, because it is one relationship. A teacher manages their
classes and who is in them; a student sees which class they are in and can
leave it.

SEVERAL CLASSES (db/migrations/013_classes_and_schools.sql)
  A teacher can run Year 9 Maths and Year 10 Maths side by side. Each class has
  a name and its own code; the code a student types decides their class and
  their teacher. Joining still takes a code - there is no list of classes to
  pick from, because picking would let anyone join anyone's class.

WHAT A TEACHER SEES OF A STUDENT HERE
  The name they signed up with, their class, year group, school and how much
  work they have submitted. Never their email.

TRY CHANGING THIS
  A teacher with a large class will want to sort the roster by "least work
  submitted" to find who has gone quiet. The data is already here.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.layout import empty_state, page_header, privacy_notice
from components.layout import plain as _plain
from models import CLASS_NAME_MAX_CHARS
from services import assessment_service, roster_service
from services import state as store

user = store.get_current_user()

if user is None:
    page_header("My Class")
    empty_state("Nobody is signed in.")
    st.stop()

NOTICE = "_roster_notice"


def _notice_and_rerun(message: str) -> None:
    st.session_state[NOTICE] = message
    st.rerun()


# --------------------------------------------------------------------------
# Teacher view
# --------------------------------------------------------------------------
def _class_card(classroom, size: int) -> None:
    with st.container(border=True):
        st.markdown(
            f"**{_plain(classroom.name)}** · {size} student{'' if size == 1 else 's'}"
        )
        if classroom.code:
            st.code(classroom.code, language=None)
        else:
            st.caption("No code yet. Issue one when you are ready to share it.")

        label = "Issue a new code" if classroom.code else "Issue a class code"
        if st.button(
            label,
            key=f"rotate_{classroom.id}",
            type="secondary" if classroom.code else "primary",
            width="stretch",
        ):
            new_code = roster_service.rotate_class_code(user.id, classroom.id)
            _notice_and_rerun(f"New code for {classroom.name}: {new_code}")

        with st.expander("Rename or delete"):
            with st.form(f"rename_{classroom.id}"):
                new_name = st.text_input(
                    "Class name",
                    value=classroom.name,
                    max_chars=CLASS_NAME_MAX_CHARS,
                    key=f"class_name_{classroom.id}",
                )
                if st.form_submit_button("Rename"):
                    outcome = roster_service.rename_class(user.id, classroom.id, new_name)
                    if outcome.ok:
                        _notice_and_rerun(outcome.message)
                    st.error(outcome.message, icon=":material/error:")
            if st.button(
                "Delete class",
                key=f"delete_{classroom.id}",
                disabled=size > 0,
                help="Only an empty class can be deleted." if size else None,
            ):
                outcome = roster_service.delete_class(user.id, classroom.id)
                if outcome.ok:
                    _notice_and_rerun(outcome.message)
                st.error(outcome.message, icon=":material/error:")


def _teacher_view() -> None:
    page_header(
        "My Class",
        "Your classes, who is in them, and how students join.",
    )

    try:
        classes = roster_service.list_classes(user.id)
    except roster_service.ClassesNotSetUp as exc:
        st.error(str(exc), icon=":material/build:")
        return
    roster = roster_service.list_roster(user.id)
    names = {c.id: c.name for c in classes}

    left, right = st.columns([2, 1])

    with right:
        st.markdown("## Classes")
        if not classes:
            st.caption(
                "You have no classes yet. Add one below, or issue a code now "
                "and a class called \"My class\" is made for you."
            )
            if st.button("Issue a class code", type="primary", width="stretch"):
                new_code = roster_service.rotate_class_code(user.id)
                _notice_and_rerun(f"New class code: {new_code}")
        for classroom in classes:
            _class_card(classroom, sum(1 for s in roster if s.class_id == classroom.id))

        st.caption(
            ":material/info: Students enter a class's code on their My Class "
            "page to join it. Issuing a new code stops the old one working; "
            "students already in the class stay in it."
        )
        with st.form("add_class", clear_on_submit=True):
            new_class = st.text_input(
                "Add a class",
                max_chars=CLASS_NAME_MAX_CHARS,
                placeholder="e.g. Year 9 Maths",
            )
            if st.form_submit_button("Add class"):
                outcome = roster_service.create_class(user.id, new_class)
                if outcome.ok:
                    _notice_and_rerun(outcome.message)
                st.error(outcome.message, icon=":material/error:")

    with left:
        st.markdown(f"## Students ({len(roster)})")

        if not roster:
            empty_state(
                "No students have joined yet.",
                hint="Issue a class code and give it to your class.",
            )
            return

        shown = roster
        if len(classes) > 1:
            choice = st.selectbox(
                "Show",
                ["All classes", *[c.id for c in classes]],
                format_func=lambda v: v if v == "All classes" else names[v],
            )
            if choice != "All classes":
                shown = [s for s in roster if s.class_id == choice]

        # One query, then counted in Python: a call per student would be a
        # round trip per row once this is on Supabase.
        submissions = assessment_service.list_submissions()
        counts: dict[str, int] = {}
        for submission in submissions:
            if submission.student_id:
                counts[submission.student_id] = counts.get(submission.student_id, 0) + 1

        if not shown:
            empty_state("Nobody is in this class yet.")
        else:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Student": student.display_name,
                            "Class": names.get(student.class_id or "", "No class"),
                            "Year": student.year_group or "-",
                            "School": student.school or "-",
                            "Pieces of work": counts.get(student.id, 0),
                        }
                        for student in shown
                    ]
                ),
                hide_index=True,
                width="stretch",
            )

        with st.expander("Remove a student from your classes"):
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
                _notice_and_rerun(outcome.message)


# --------------------------------------------------------------------------
# Student view
# --------------------------------------------------------------------------
def _student_view() -> None:
    page_header("My Class", "Which class you are in.")

    membership = roster_service.my_class(user)
    if membership is not None:
        teacher = _plain(membership.teacher_name)
        if membership.class_name:
            line = f"You are in {_plain(membership.class_name)} with {teacher}."
        else:
            line = f"You are in {teacher}'s class."
        st.success(line, icon=":material/groups:")
        if membership.teacher_school:
            st.caption(f"School: {_plain(membership.teacher_school)}")
        st.caption(
            "That is why their assessments show up in My Work, and why they can "
            "see the work you submit. To move to another class, leave this one "
            "and enter the new class's code."
        )

        with st.expander("Leave this class"):
            st.caption(
                "Your uploads and your own question sets stay yours and are not "
                "deleted. Your teacher stops seeing your work, and their "
                "assessments stop appearing for you."
            )
            if st.button("Leave class"):
                outcome = roster_service.leave_class(user.id)
                _notice_and_rerun(outcome.message)
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
            help="Six characters. Your teacher will give you the code for your class.",
        )
        joined = st.form_submit_button("Join class", type="primary")

    if joined:
        outcome = roster_service.join_class(user.id, code)
        if outcome.ok:
            _notice_and_rerun(outcome.message)
        else:
            st.error(outcome.message, icon=":material/error:")


# --------------------------------------------------------------------------
notice = st.session_state.pop(NOTICE, None)

if user.is_teacher:
    _teacher_view()
else:
    _student_view()

if notice:
    st.toast(notice)

st.divider()
privacy_notice()
