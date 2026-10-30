"""The sign-in and create-account forms, shared by the landing and Sign In pages.

Sign-up asks for a name, an email and a password, and whether you are a student
or a teacher. Choosing "Teacher" sends no role anywhere: it only asks for the
invite code, which is redeemed through `auth_service.redeem_teacher_invite` as
soon as the account is signed in. The database decides whether the code is
good, for the reasons set out at the top of pages/sign_in.py; a refused code
leaves a student account, and the code can be tried again on Profile.

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

# An invite code typed at sign-up, held until the account can sign in: an
# account that needs its email confirmed has no session to redeem it with yet.
PENDING_INVITE = "_pending_teacher_invite"

STUDENT_CHOICE = "Student"
TEACHER_CHOICE = "Teacher"


def _redeem_pending_invite() -> bool:
    """Redeem an invite code held from sign-up. False if one was refused."""
    code = st.session_state.pop(PENDING_INVITE, None)
    if not code:
        return True
    outcome = auth_service.redeem_teacher_invite(code)
    if not outcome.ok:
        st.warning(
            "You are signed in with a student account: that invite code was not "
            "accepted. Check it and enter it again on your Profile page.",
            icon=":material/key_off:",
        )
    return outcome.ok


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
                "Email", key="sign_in_email", max_chars=auth_service.MAX_EMAIL_CHARS,
                type="email", autocomplete="email",
            )
            password = st.text_input(
                "Password",
                type="password",
                autocomplete="current-password",
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
                    if _redeem_pending_invite():
                        st.rerun()
                else:
                    st.error(outcome.message, icon=":material/error:")

    with sign_up_tab:
        # Outside the form, so the invite code field appears as soon as
        # "Teacher" is picked. The landing page's teacher link preselects it.
        wants_teacher = st.query_params.get("as") == "teacher"
        choice = st.radio(
            "I am a",
            [STUDENT_CHOICE, TEACHER_CHOICE],
            index=1 if wants_teacher else 0,
            horizontal=True,
            key="sign_up_role",
        )
        is_teacher = choice == TEACHER_CHOICE
        if is_teacher:
            st.caption(
                "Teacher accounts need the invite code from whoever runs this "
                "app. You only see students who join with your class code."
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
                "Email", key="sign_up_email", max_chars=auth_service.MAX_EMAIL_CHARS,
                type="email", autocomplete="email",
            )
            new_password = st.text_input(
                "Password",
                type="password",
                autocomplete="new-password",
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
                autocomplete="new-password",
                key="sign_up_confirm",
                max_chars=auth_service.MAX_PASSWORD_CHARS,
            )
            invite_code = ""
            if is_teacher:
                invite_code = st.text_input(
                    "Teacher invite code",
                    type="password",
                    key="sign_up_invite",
                    max_chars=auth_service.MAX_INVITE_CODE_CHARS,
                )
            created = st.form_submit_button(
                "Create teacher account" if is_teacher else "Create account",
                type="primary",
            )

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
            elif is_teacher and not invite_code.strip():
                st.error(
                    "Enter your teacher invite code, or choose Student.",
                    icon=":material/error:",
                )
            else:
                outcome = auth_service.sign_up(new_email, new_password, full_name)
                if outcome.ok and is_teacher:
                    st.session_state[PENDING_INVITE] = invite_code
                if outcome.ok and not outcome.needs_confirmation:
                    if _redeem_pending_invite():
                        st.rerun()
                elif outcome.ok:
                    st.success(
                        outcome.message
                        + (
                            " Sign in here and your invite code is applied."
                            if is_teacher
                            else ""
                        ),
                        icon=":material/mark_email_read:",
                    )
                else:
                    st.error(outcome.message, icon=":material/error:")
