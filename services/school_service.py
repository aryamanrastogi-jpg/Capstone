"""Schools: the school on a profile, and the list of schools on the app.

WHAT A SCHOOL IS HERE
  Free text on a profile (db/migrations/013_classes_and_schools.sql), set at
  sign-up, on Profile, or by an admin for a new teacher. It is tidied
  (models.user.clean_school) so "Greenfield  School " and "Greenfield School"
  are one school, and capped at SCHOOL_MAX_CHARS. It decides nothing about who
  can see what: joining a class still takes the teacher's code.

WHERE THE LIST COMES FROM
  Only schools that have a teacher on the app (list_schools() in migration 013).
  A student types their own school into a public form, and anything typed there
  can be a typo or worse; a teacher's account was made or approved by an admin.
  So the list a visitor sees, and the suggestions under the sign-up box, are
  teachers' schools. A student whose school is not listed can still type it.

  The list is public on purpose (the Schools page opens without an account), so
  it holds school names only: no counts, no people.
"""

from __future__ import annotations

from typing import List, Optional

import streamlit as st

from models import SCHOOL_MAX_CHARS, clean_school
from utils.config import get_settings


def school_problem(value: Optional[str]) -> Optional[str]:
    """Why a typed school cannot be saved, or None (blank is allowed)."""
    cleaned = clean_school(value)
    if cleaned and len(cleaned) > SCHOOL_MAX_CHARS:
        return f"Keep the school under {SCHOOL_MAX_CHARS} characters."
    return None


@st.cache_data(ttl=120, show_spinner=False)
def _schools_from_supabase() -> List[str]:
    """list_schools() on a client with no session: anyone may ask, signed in or not."""
    from services.auth_service import anonymous_client

    client = anonymous_client()
    if client is None:
        return []
    try:
        rows = client.rpc("list_schools", {}).execute().data or []
    except Exception:  # noqa: BLE001 - before migration 013 there is no list yet
        return []
    return [r["school"] for r in rows if r.get("school")]


def _schools_from_demo() -> List[str]:
    from services import state

    names = {u.school for u in state.get_users() if u.is_teacher and u.school}
    return sorted(names, key=str.lower)


def list_schools() -> List[str]:
    """Schools with a teacher on the app, A to Z."""
    if get_settings().supabase_configured:
        return _schools_from_supabase()
    return _schools_from_demo()


def clear_cache() -> None:
    """Forget the cached list (tests, and after an admin adds a teacher)."""
    _schools_from_supabase.clear()
