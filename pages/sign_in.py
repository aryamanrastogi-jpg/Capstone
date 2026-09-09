"""Sign in - the real one, not the demo dropdown.

WHAT A PERSON CAN AND CANNOT CHOOSE HERE
  They can choose their email and their password. That is the whole list.

  There is no role selector, and there will not be one. The role is written by a
  database trigger at sign-up and is always `student`; a teacher is promoted by
  an operator running one statement, documented in
  db/migrations/002_auth_profiles.sql. A form that let you pick "I am a teacher"
  would hand the class register to anybody who asked for it, and every read
  policy downstream would believe the answer.

  There is no display-name field either. Students are identified by an anonymous
  code the database generates. The privacy notice on every page promises real
  identities are not stored, so the sign-up form does not invite one.

WHY THIS PAGE STILL OFFERS TO CARRY ON WITHOUT SIGNING IN
  Demo mode is not a fallback for a broken sign-in - it is how the app is shown
  to somebody who has no account and no reason to make one. Refusing to open
  without credentials would make the project undemonstrable.
"""

from __future__ import annotations

import streamlit as st

from services import auth_service
from services.supabase_client import get_connection_status
from utils.config import APP_NAME, APP_TAGLINE, PRIVACY_NOTICE

st.title(f"Sign in to {APP_NAME}")
st.caption(APP_TAGLINE)

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
        "this app can change."
    )
    if st.button("Sign out", type="primary"):
        auth_service.sign_out()
        st.rerun()
    st.stop()

st.caption(
    "Signing in switches this session from the sample dataset to your own "
    "saved work."
)

sign_in_tab, sign_up_tab = st.tabs(["Sign in", "Create an account"])

with sign_in_tab:
    with st.form("sign_in_form"):
        email = st.text_input("Email", key="sign_in_email")
        password = st.text_input("Password", type="password", key="sign_in_password")
        submitted = st.form_submit_button("Sign in", type="primary")

    if submitted:
        if not email.strip() or not password:
            st.error("Enter both an email and a password.", icon=":material/error:")
        else:
            outcome = auth_service.sign_in(email, password)
            if outcome.ok:
                st.rerun()
            else:
                st.error(outcome.message, icon=":material/error:")

with sign_up_tab:
    st.caption(
        "New accounts are students. Teacher access is granted by whoever "
        "administers this instance, not from this form."
    )
    with st.form("sign_up_form"):
        new_email = st.text_input("Email", key="sign_up_email")
        new_password = st.text_input(
            "Password",
            type="password",
            key="sign_up_password",
            help="At least six characters.",
        )
        confirm = st.text_input(
            "Confirm password", type="password", key="sign_up_confirm"
        )
        created = st.form_submit_button("Create account", type="primary")

    if created:
        if not new_email.strip() or not new_password:
            st.error("Enter both an email and a password.", icon=":material/error:")
        elif new_password != confirm:
            st.error("The two passwords do not match.", icon=":material/error:")
        else:
            outcome = auth_service.sign_up(new_email, new_password)
            if outcome.ok and not outcome.needs_confirmation:
                st.rerun()
            elif outcome.ok:
                st.success(outcome.message, icon=":material/mark_email_read:")
            else:
                st.error(outcome.message, icon=":material/error:")

st.divider()
st.caption(PRIVACY_NOTICE)
