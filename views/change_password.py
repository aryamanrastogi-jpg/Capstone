"""Choose your password - the one page an admin-created account can reach at first.

An admin types a temporary password when they create a teacher account
(services/admin_service.py), so the admin, and anyone who saw it on its way to
the teacher, knows it. While `auth_service.must_change_password()` is true,
app.py therefore registers only this page: no menu, no other page. Saving a
password clears that flag in the same request (`auth_service.choose_password`),
so the next run opens the app as normal.

It asks for the new password twice and nothing else: the person signed in with
the temporary one a moment ago. The two boxes are checked here for a typo, and
again in the service for everything else.
"""

from __future__ import annotations

import streamlit as st

from components.layout import page_header
from services import auth_service
from services import state as store

page_header(
    "Choose your password",
    "An admin set a temporary password when they made your account. Choose "
    "your own to carry on.",
)

user = auth_service.current_user()
if user is None:
    st.error("Sign in to choose a password.", icon=":material/error:")
    st.stop()

with st.form("choose_password_form"):
    new_password = st.text_input(
        "New password",
        type="password",
        autocomplete="new-password",
        key="choose_password_new",
        max_chars=auth_service.MAX_PASSWORD_CHARS,
        help=(
            f"At least {auth_service.MIN_PASSWORD_CHARS} characters, "
            "with at least one letter and one number."
        ),
    )
    confirm = st.text_input(
        "Confirm new password",
        type="password",
        autocomplete="new-password",
        key="choose_password_confirm",
        max_chars=auth_service.MAX_PASSWORD_CHARS,
    )
    saved = st.form_submit_button("Save password", type="primary")

if saved:
    if not new_password or not confirm:
        st.error("Enter your new password, then enter it again.", icon=":material/error:")
    elif new_password != confirm:
        st.error("The two passwords do not match.", icon=":material/error:")
    else:
        outcome = auth_service.choose_password(new_password)
        if outcome.ok:
            st.rerun()
        st.error(outcome.message, icon=":material/error:")

st.divider()
if st.button("Sign out", icon=":material/logout:"):
    auth_service.sign_out()
    store.leave_demo()
    st.rerun()
