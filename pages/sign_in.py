"""Sign in - the real one, not the demo dropdown.

WHAT A PERSON CAN AND CANNOT CHOOSE HERE
  They can choose their email and their password. That is the whole list.

  There is no role selector, and there will not be one. The role is written by a
  database trigger at sign-up and is always `student`. A teacher signs up the
  same way, then redeems an invite code on the Profile page; the operator mints
  those codes by hand (db/migrations/005_teacher_invites.sql) and the database
  decides whether one is good. A form that let you pick "I am a teacher" would
  hand the class register to anybody who asked for it, and every read policy
  downstream would believe the answer.

  Sign-up asks for a name, which the database trigger stores as the display
  name (db/migrations/004_profile_details.sql). It can be changed later on the
  Profile page.

WHY THIS PAGE STILL OFFERS TO CARRY ON WITHOUT SIGNING IN
  Demo mode is not a fallback for a broken sign-in - it is how the app is shown
  to somebody who has no account and no reason to make one. Refusing to open
  without credentials would make the project undemonstrable.
"""

from __future__ import annotations

import streamlit as st

from components.auth_forms import auth_forms, privacy_details
from components.layout import page_header
from services import auth_service
from services.supabase_client import get_connection_status
from utils.config import APP_NAME, PRIVACY_NOTICE

page_header(
    "Sign In",
    f"Sign in to {APP_NAME} to work on your own saved data instead of the "
    "shared sample set.",
)

status = get_connection_status()

if not status.connected:
    # No credentials, or credentials that do not work. Signing in is not on the
    # table, and pretending otherwise wastes the reader's time.
    st.info(
        "This instance is not connected to Supabase, so there is nothing to "
        "sign in to. It is running on local sample data.",
        icon=":material/science:",
    )
    if status.is_error:
        st.error(status.message, icon=":material/error:")
    st.stop()

signed_in_user = auth_service.current_user()
if signed_in_user is not None:
    st.success(
        f"Signed in as {signed_in_user.display_name} ({signed_in_user.role.label}).",
        icon=":material/check_circle:",
    )
    st.caption(
        "Your role comes from your profile in the database. It is not something "
        "this app can change - teacher access comes only from an invite code, "
        "redeemed on your Profile page."
    )
    if st.button("Sign out", type="primary"):
        auth_service.sign_out()
        st.rerun()
    st.stop()

st.caption(
    "Signing in switches this session from the sample dataset to your own "
    "saved work."
)

auth_forms()

st.divider()
# The full statement sits here, where the decision to make an account is made,
# not only in the one-line notice at the foot of every page.
privacy_details()
st.caption(PRIVACY_NOTICE)
