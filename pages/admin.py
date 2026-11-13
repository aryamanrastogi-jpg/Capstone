"""Admin - teacher invite codes and teachers.

Shown only to signed-in accounts on `app_admins` (db/migrations/010_admin.sql).
The page decides nothing: every action is a database function that refuses
anybody who is not an admin, so the check below is only there to show a clear
message instead of a failed call.

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
from services import admin_service, auth_service

page_header(
    "Admin",
    "Create teacher invite codes, see who is a teacher, and remove teacher access.",
)

user = auth_service.current_user()
if user is None or not user.is_admin:
    st.error(
        "This page is for admins. Admin access is given by whoever runs this "
        "instance.",
        icon=":material/lock:",
    )
    st.stop()

FLASH = "_admin_flash"
NEW_CODE = "_admin_new_code"

flash = st.session_state.pop(FLASH, None)
if flash:
    ok, message = flash
    if ok:
        st.success(message, icon=":material/check_circle:")
    else:
        st.error(message, icon=":material/error:")


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
        "leave or refresh this page it cannot be shown again.",
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
                    "Admin": "Yes" if teacher.is_admin else "",
                }
                for teacher in teachers
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    removable = [t for t in teachers if not t.is_admin and t.profile_id != user.id]
    if removable:
        with st.expander("Remove teacher access", icon=":material/person_remove:"):
            st.caption(
                "The account becomes a student account. Their assessments and the "
                "work handed in against them stay. Admins cannot be removed here."
            )
            with st.form("admin_demote_teacher"):
                target = st.selectbox(
                    "Teacher",
                    removable,
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
