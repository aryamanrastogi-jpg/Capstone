"""Schools - which schools have a teacher on Camp Prep AI.

Opens without an account, like Privacy: a parent or a school deciding whether
to use the app can see who already does. Names only, and only schools with a
teacher on the app - services/school_service.py says why.
"""

from __future__ import annotations

import streamlit as st

from components.layout import empty_state, page_header, plain, privacy_notice
from services import school_service

page_header("Schools", "Schools with a teacher on Camp Prep AI.")

schools = school_service.list_schools()

if not schools:
    empty_state(
        "No schools yet.",
        hint="A school appears here once a teacher from it is on the app.",
    )
else:
    st.markdown("\n".join(f"- {plain(school)}" for school in schools))
    st.caption(
        f"{len(schools)} school{'' if len(schools) == 1 else 's'}. Not listed? "
        "Students can still type their school when they sign up; a school is "
        "listed once one of its teachers is on the app."
    )

st.divider()
privacy_notice()
