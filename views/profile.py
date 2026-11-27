"""Profile - see, edit and delete your own account.

Create happens at sign-up. Here you can read your details, update your name,
year group, school and photo, remove the photo, and delete the account. Your
role is shown but cannot be changed: it comes from the database, not from you.

THE TEACHER INVITE BOX
  The one way a role changes from this page is by redeeming an invite code, and
  even then the page decides nothing. The code goes to
  `redeem_teacher_invite` in db/migrations/005_teacher_invites.sql, which checks
  it against a hash the operator stored, promotes only the caller, and answers
  every bad code with the same sentence. The box is offered to students only; a
  teacher has nothing to redeem.

CHANGING YOUR PASSWORD
  Asks for the current password first (`auth_service.change_password` checks it
  on a throwaway session) and signs your other devices out. There is no emailed
  "forgot password" route yet: it needs an email provider and Auth settings
  that are not set up.

WHAT IS SHOWN
  Your own email, read from the signed-in session, is the only email anywhere in
  the app. It is rendered read-only and never logged.
"""

from __future__ import annotations

import html

import streamlit as st

from components.layout import page_header
from components.school_picker import school_picker
from models import Role
from services import auth_service
from services import state as store
from utils import palette

page_header("Profile", "Your account details and profile photo.")

user = auth_service.current_user()
if user is None:
    st.error("Sign in to see your profile.", icon=":material/error:")
    st.stop()

# A message from the last action survives the rerun that follows it.
flash = st.session_state.pop("_profile_flash", None)
if flash:
    ok, message = flash
    if ok:
        st.success(message, icon=":material/check_circle:")
    else:
        st.error(message, icon=":material/error:")


def _done(outcome: auth_service.AuthOutcome) -> None:
    st.session_state["_profile_flash"] = (outcome.ok, outcome.message)
    st.rerun()


PASSWORD_KEYS = (
    "change_password_current",
    "change_password_new",
    "change_password_confirm",
)
# The answer to the last change attempt, shown under the form it belongs to.
PASSWORD_FLASH = "_password_flash"


def _change_password() -> None:
    """Form callback: runs before the page redraws, so it can clear the boxes.

    What was typed stays when the change fails (a typo in one box should not
    cost three), and goes when it works, so a password never sits in a box.
    """
    current, new, confirm = (st.session_state.get(key, "") for key in PASSWORD_KEYS)
    if not current or not new or not confirm:
        outcome = auth_service.AuthOutcome(
            False, "Enter your current password, then your new one twice."
        )
    elif new != confirm:
        outcome = auth_service.AuthOutcome(False, "The two passwords do not match.")
    else:
        outcome = auth_service.change_password(current, new)
    st.session_state[PASSWORD_FLASH] = (outcome.ok, outcome.message)
    if outcome.ok:
        for key in PASSWORD_KEYS:
            st.session_state[key] = ""


photo_col, details_col = st.columns([1, 2], gap="large")

with photo_col:
    st.markdown("## Photo")
    if user.avatar_url:
        st.image(user.avatar_url, width=160)
    else:
        initial = html.escape(user.display_name[:1].upper())
        st.markdown(
            f'<div style="width:160px;height:160px;border-radius:50%;'
            f"background:{palette.SURFACE_ALT};color:{palette.PRIMARY};"
            "display:flex;align-items:center;justify-content:center;"
            f'font-size:3.5rem;font-weight:700">{initial}</div>',
            unsafe_allow_html=True,
        )
    upload = st.file_uploader(
        "Upload a new photo",
        type=["png", "jpg", "jpeg", "webp"],
        help="PNG, JPG or WEBP, up to 2 MB.",
    )
    if upload is not None and st.button("Save photo", type="primary", width="stretch"):
        _done(auth_service.upload_avatar(upload.getvalue(), upload.name))
    if user.avatar_url and st.button("Remove photo", width="stretch"):
        _done(auth_service.remove_avatar())

with details_col:
    st.markdown("## Details")
    st.text_input("Email", value=auth_service.current_email() or "", disabled=True)
    st.text_input(
        "Role",
        value=user.role.label,
        disabled=True,
        help="Set by the database, not from this page. Teacher access comes "
        "from an admin, who creates your teacher account or sends you an invite "
        "code.",
    )
    with st.form("profile_form"):
        name = st.text_input(
            "Full name",
            value=user.display_name,
            max_chars=auth_service.MAX_NAME_CHARS,
        )
        year_options = [None, 7, 8, 9, 10, 11]
        year = st.selectbox(
            "Year group",
            year_options,
            index=year_options.index(user.year_group)
            if user.year_group in year_options
            else 0,
            format_func=lambda y: "Not set" if y is None else f"Year {y}",
        )
        school = school_picker("School", current=user.school, key="profile_school")
        if st.form_submit_button("Save changes", type="primary"):
            _done(auth_service.update_profile(name, year, school))

st.divider()
# Open again after an attempt, with the answer under the button that was pressed:
# a message at the top of the page would be out of sight from down here.
password_flash = st.session_state.pop(PASSWORD_FLASH, None)
with st.expander(
    "Change password", icon=":material/lock_reset:", expanded=password_flash is not None
):
    with st.form("change_password_form"):
        st.text_input(
            "Current password",
            type="password",
            autocomplete="current-password",
            key=PASSWORD_KEYS[0],
            max_chars=auth_service.MAX_PASSWORD_CHARS,
        )
        st.text_input(
            "New password",
            type="password",
            autocomplete="new-password",
            key=PASSWORD_KEYS[1],
            max_chars=auth_service.MAX_PASSWORD_CHARS,
            help=(
                f"At least {auth_service.MIN_PASSWORD_CHARS} characters, "
                "with at least one letter and one number."
            ),
        )
        st.text_input(
            "Confirm new password",
            type="password",
            autocomplete="new-password",
            key=PASSWORD_KEYS[2],
            max_chars=auth_service.MAX_PASSWORD_CHARS,
        )
        st.form_submit_button(
            "Change password", type="primary", on_click=_change_password
        )
    if password_flash:
        ok, message = password_flash
        if ok:
            st.success(message, icon=":material/check_circle:")
        else:
            st.error(message, icon=":material/error:")

if user.role is not Role.TEACHER:
    st.divider()
    with st.expander("Have a teacher invite code?", icon=":material/key:"):
        st.caption(
            "Teacher access is given by whoever runs this instance. If they sent "
            "you an invite code, enter it here. Codes expire and can only be used "
            "a limited number of times. Becoming a teacher removes you from any "
            "class you have joined."
        )
        with st.form("teacher_invite_form", clear_on_submit=True):
            invite_code = st.text_input(
                "Invite code",
                type="password",
                max_chars=auth_service.MAX_INVITE_CODE_CHARS,
            )
            if st.form_submit_button("Redeem code", type="primary"):
                _done(auth_service.redeem_teacher_invite(invite_code))

st.divider()
with st.expander("Delete account", icon=":material/warning:"):
    if user.is_teacher:
        explanation = (
            "This permanently deletes your account and photo. Assessments with "
            "student submissions stay archived with those submissions and grades; "
            "unused assessments are deleted. This cannot be undone."
        )
    else:
        explanation = (
            "This permanently deletes your account, your submissions and your "
            "question sets. A shared set used by another student stays archived "
            "for their history. This cannot be undone."
        )
    st.warning(explanation)
    confirm = st.text_input('Type "DELETE" to confirm', key="delete_confirm")
    if st.button("Delete my account", type="primary", disabled=confirm != "DELETE"):
        outcome = auth_service.delete_account()
        if outcome.ok:
            store.leave_demo()
            st.rerun()
        st.error(outcome.message, icon=":material/error:")
