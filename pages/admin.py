"""Admin - teacher invite codes and teachers.

Opened with the ADMIN_PASSKEY secret, not with an account: nobody has to be
signed in, and the page is reached at /admin or from the link on the sign-in
form. See services/admin_service.py for how the passkey and the service-role
key are handled, and db/migrations/011_admin_passkey.sql for the functions it
calls, which only the service role can run.

WHAT IS SHOWN
  Teachers appear by display name and profile id, never by email: the Profile
  page promises your own email is the only one anywhere in the app. A new invite
  code is shown once, straight after it is made, because only its hash is kept.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import streamlit as st

from components.layout import page_header
from services import admin_service

page_header(
    "Admin",
    "Create teacher invite codes, see who is a teacher, and remove teacher access.",
)

FLASH = "_admin_flash"
NEW_CODE = "_admin_new_code"

problem = admin_service.setup_problem()
if problem:
    st.error(problem, icon=":material/lock:")
    st.stop()

if not admin_service.is_unlocked():
    wait = admin_service.locked_for()
    if wait:
        st.warning(
            f"Too many wrong passkeys. Try again in {wait} seconds.",
            icon=":material/lock_clock:",
        )
    with st.form("admin_unlock"):
        passkey = st.text_input(
            "Admin passkey",
            type="password",
            autocomplete="off",
            max_chars=admin_service.MAX_PASSKEY_INPUT_CHARS,
            help="The ADMIN_PASSKEY secret set for this app.",
        )
        if st.form_submit_button("Unlock", type="primary"):
            outcome = admin_service.unlock(passkey)
            if outcome.ok:
                st.rerun()
            st.error(outcome.message, icon=":material/error:")
    st.stop()

flash = st.session_state.pop(FLASH, None)
if flash:
    ok, message = flash
    if ok:
        st.success(message, icon=":material/check_circle:")
    else:
        st.error(message, icon=":material/error:")

if st.button("Lock admin", icon=":material/lock:"):
    admin_service.lock()
    st.rerun()


def _done(outcome: admin_service.AdminOutcome) -> None:
    st.session_state[FLASH] = (outcome.ok, outcome.message)
    st.rerun()


def _when(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


# --------------------------------------------------------------------------
# Create an invite code
# --------------------------------------------------------------------------
st.markdown("#### Create a teacher invite code")

new_code = st.session_state.pop(NEW_CODE, None)
if new_code:
    st.success(
        "Send this code to the teacher privately. It is shown only now: once you "
        "leave or refresh this page it cannot be shown again. They sign up, then "
        "enter it on their Profile page.",
        icon=":material/key:",
    )
    st.code(new_code, language=None)

with st.form("admin_create_invite", clear_on_submit=True):
    note = st.text_input(
        "Who is it for?",
        placeholder="e.g. Ms Rao, maths",
        max_chars=admin_service.MAX_NOTE_CHARS,
        help="Only admins see this note. It helps you tell codes apart.",
    )
    uses_col, days_col = st.columns(2)
    with uses_col:
        max_uses = st.number_input(
            "Number of uses",
            min_value=1,
            max_value=admin_service.MAX_USES,
            value=1,
            step=1,
            help="1 for one teacher. More for a whole department.",
        )
    with days_col:
        valid_days = st.number_input(
            "Days valid",
            min_value=1,
            max_value=admin_service.MAX_VALID_DAYS,
            value=7,
            step=1,
        )
    if st.form_submit_button("Create code", type="primary"):
        outcome = admin_service.create_teacher_invite(note, int(max_uses), int(valid_days))
        if outcome.ok and outcome.code:
            st.session_state[NEW_CODE] = outcome.code
            st.rerun()
        _done(outcome)

# --------------------------------------------------------------------------
# Existing codes
# --------------------------------------------------------------------------
st.divider()
st.markdown("#### Invite codes")

invites, invite_error = admin_service.list_teacher_invites()
if invite_error:
    st.error(invite_error, icon=":material/error:")
elif not invites:
    st.info("No invite codes yet. Create one above.", icon=":material/info:")
else:
    now = datetime.now(timezone.utc)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "For": invite.note or "(no note)",
                    "Status": invite.status(now),
                    "Used": f"{invite.use_count} of {invite.max_uses}",
                    "Expires": _when(invite.expires_at),
                    "Last used by": invite.last_used_by or "",
                    "Created": _when(invite.created_at),
                }
                for invite in invites
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    active = [invite for invite in invites if invite.status(now) == "Active"]
    if active:
        with st.form("admin_cancel_invite"):
            chosen = st.selectbox(
                "Cancel an active code",
                active,
                format_func=lambda i: f"{i.note or '(no note)'}, expires {_when(i.expires_at)}",
            )
            if st.form_submit_button("Cancel code"):
                _done(admin_service.cancel_teacher_invite(chosen.id))

# --------------------------------------------------------------------------
# Teachers
# --------------------------------------------------------------------------
st.divider()
st.markdown("#### Teachers")

teachers, teacher_error = admin_service.list_teachers()
if teacher_error:
    st.error(teacher_error, icon=":material/error:")
elif not teachers:
    st.info("No teachers yet. They appear here once they redeem a code.", icon=":material/info:")
else:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Name": teacher.display_name,
                    "Profile id": teacher.profile_id,
                    "Students": teacher.student_count,
                }
                for teacher in teachers
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    with st.expander("Remove teacher access", icon=":material/person_remove:"):
        st.caption(
            "The account becomes a student account. Their assessments and the "
            "work handed in against them stay."
        )
        with st.form("admin_demote_teacher"):
            target = st.selectbox(
                "Teacher",
                teachers,
                format_func=lambda t: f"{t.display_name} ({t.profile_id})",
            )
            release = st.checkbox(
                "Also take their students off their class",
                value=True,
                help="Otherwise their students stay linked to an account "
                "that is no longer a teacher.",
            )
            confirm = st.text_input('Type "REMOVE" to confirm')
            if st.form_submit_button("Remove teacher access"):
                if confirm.strip() != "REMOVE":
                    st.error('Type "REMOVE" to confirm.', icon=":material/error:")
                else:
                    _done(admin_service.demote_teacher(target.profile_id, release))
