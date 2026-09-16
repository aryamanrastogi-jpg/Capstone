"""The sign-in and create-account forms, shared by the landing and Sign In pages.

Sign-up asks for a name, an email and a password. There is no role field, for
the reasons set out at the top of pages/sign_in.py. Teacher access comes from
an invite code redeemed on the Profile page once the account exists.

WHAT THIS MODULE NEVER DOES
  It never echoes an email, a password or a token back onto the page, and never
  logs one. Error messages come from auth_service, which summarises rather than
  repeats what Supabase said. Every text input has `max_chars`, and the service
  re-checks the same limits, because a form limit is only a browser courtesy.
"""

from __future__ import annotations

import streamlit as st

from services import auth_service
from utils.config import PRIVACY_DETAILS


def privacy_details(expanded: bool = False) -> None:
    """The full privacy statement, folded away beside the forms."""
    with st.expander(
        "How we use your name and email",
        icon=":material/shield_person:",
        expanded=expanded,
    ):
        for line in PRIVACY_DETAILS:
            st.markdown(f"- {line}")


def auth_forms() -> None:
    """Draw the "Sign in" and "Create an account" tabs."""
    sign_in_tab, sign_up_tab = st.tabs(["Sign in", "Create an account"])

    with sign_in_tab:
        locked = auth_service.sign_in_locked_for()
        if locked:
            st.warning(
                f"Too many failed attempts. Try again in {locked} seconds.",
                icon=":material/lock_clock:",
            )
        with st.form("sign_in_form"):
            email = st.text_input(
                "Email", key="sign_in_email", max_chars=auth_service.MAX_EMAIL_CHARS
            )
            password = st.text_input(
                "Password",
                type="password",
                key="sign_in_password",
                max_chars=auth_service.MAX_PASSWORD_CHARS,
            )
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
            "New accounts are students. Teachers: create your account here, then "
            "enter the invite code you were given on your Profile page."
        )
        st.caption(
            "We store your name and email to run your account. Your teacher can "
            "see your name on their class list. You can delete your account at "
            "any time from Profile."
        )
        with st.form("sign_up_form"):
            full_name = st.text_input(
                "Full name", key="sign_up_name", max_chars=auth_service.MAX_NAME_CHARS
            )
            new_email = st.text_input(
                "Email", key="sign_up_email", max_chars=auth_service.MAX_EMAIL_CHARS
            )
            new_password = st.text_input(
                "Password",
                type="password",
                key="sign_up_password",
                max_chars=auth_service.MAX_PASSWORD_CHARS,
                help=(
                    f"At least {auth_service.MIN_PASSWORD_CHARS} characters, "
                    "with at least one letter and one number."
                ),
            )
            confirm = st.text_input(
                "Confirm password",
                type="password",
                key="sign_up_confirm",
                max_chars=auth_service.MAX_PASSWORD_CHARS,
            )
            created = st.form_submit_button("Create account", type="primary")

        if created:
            problem = (
                auth_service.password_problem(new_password) if new_password else None
            )
            if not full_name.strip() or not new_email.strip() or not new_password:
                st.error(
                    "Enter your name, an email and a password.",
                    icon=":material/error:",
                )
            elif problem:
                st.error(problem, icon=":material/error:")
            elif new_password != confirm:
                st.error("The two passwords do not match.", icon=":material/error:")
            else:
                outcome = auth_service.sign_up(new_email, new_password, full_name)
                if outcome.ok and not outcome.needs_confirmation:
                    st.rerun()
                elif outcome.ok:
                    st.success(outcome.message, icon=":material/mark_email_read:")
                else:
                    st.error(outcome.message, icon=":material/error:")
