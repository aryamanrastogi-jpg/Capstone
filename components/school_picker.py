"""The school box on sign-up and Profile.

A dropdown of the schools already on the app (services/school_service.py) that
also takes a school typed in, so "Greenfield School" is picked rather than
retyped as "Greenfield Sch." by the next student - but a school that is not
listed yet is never a dead end.
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

from models import clean_school
from services import school_service


def school_picker(label: str = "School", current: Optional[str] = None, key: Optional[str] = None) -> Optional[str]:
    """Show the box and return the tidied school, or None when left empty."""
    options = list(school_service.list_schools())
    current = clean_school(current)
    if current and current.lower() not in {o.lower() for o in options}:
        options.insert(0, current)
    index = next(
        (i for i, o in enumerate(options) if current and o.lower() == current.lower()),
        None,
    )
    choice = st.selectbox(
        label,
        options,
        index=index,
        key=key,
        accept_new_options=True,
        placeholder="Pick your school, or type it",
        help="Optional. Pick it if it is listed; otherwise type its full name.",
    )
    return clean_school(choice)
