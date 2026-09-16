"""The sign-in and create-account forms, shared by the landing and Sign In pages.

Email and password only. There is no role and no name field, for the reasons
set out at the top of pages/sign_in.py.
"""

from __future__ import annotations

import streamlit as st

from services import auth_service


def auth_forms() -> None:
    """Draw the "Sign in" and "Create an account" tabs."""
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
