"""Profile - see, edit and delete your own account.

Create happens at sign-up. Here you can read your details, update your name,
year group and photo, remove the photo, and delete the account. Your role is
shown but cannot be changed: it comes from the database, not from you.
"""

from __future__ import annotations

import streamlit as st

from components.layout import page_header
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


photo_col, details_col = st.columns([1, 2], gap="large")

with photo_col:
    st.markdown("#### Photo")
    if user.avatar_url:
        st.image(user.avatar_url, width=160)
    else:
        initial = user.display_name[:1].upper()
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
    st.markdown("#### Details")
    st.text_input("Email", value=auth_service.current_email() or "", disabled=True)
    st.text_input(
        "Role",
        value=user.role.label,
        disabled=True,
        help="Set by whoever administers this instance, not from this page.",
    )
    with st.form("profile_form"):
        name = st.text_input("Full name", value=user.display_name, max_chars=60)
        year_options = [None, 7, 8, 9, 10, 11]
        year = st.selectbox(
            "Year group",
            year_options,
            index=year_options.index(user.year_group)
            if user.year_group in year_options
            else 0,
            format_func=lambda y: "Not set" if y is None else f"Year {y}",
        )
        if st.form_submit_button("Save changes", type="primary"):
            _done(auth_service.update_profile(name, year))

st.divider()
with st.expander("Delete account", icon=":material/warning:"):
    st.warning(
        "This permanently deletes your account, your photo and the work saved "
        "under it. It cannot be undone."
    )
    confirm = st.text_input('Type "DELETE" to confirm', key="delete_confirm")
    if st.button("Delete my account", type="primary", disabled=confirm != "DELETE"):
        outcome = auth_service.delete_account()
        if outcome.ok:
            store.leave_demo()
            st.rerun()
        st.error(outcome.message, icon=":material/error:")
