"""Welcome page - what AssessAI is, plus sign in, sign up or try the demo.

Shown by app.py to anyone who is not signed in and has not chosen the demo.
The sign-in forms are the same ones as on the Sign In page. Sign-up collects a
real name and an email, so the full privacy statement sits directly under the
forms rather than only in the one-line notice at the foot of the page.
"""

from __future__ import annotations

import streamlit as st

from components.auth_forms import auth_forms, privacy_details
from components.layout import info_card, inject_styles
from services import state as store
from services.supabase_client import get_connection_status
from utils.config import APP_TAGLINE, PRIVACY_NOTICE

inject_styles()

intro, auth = st.columns([1.15, 1], gap="large")

with intro:
    st.markdown(
        f'''<span class="assessai-eyebrow">{APP_TAGLINE}</span>
<p class="assessai-hero-title">Know where you went wrong.
<span>Fix it before the exam.</span></p>
<p class="assessai-hero-lede">AssessAI marks your work, shows you which topics
are slipping and points you at what to practise. Pointers, not answers - and a
teacher confirms every mark.</p>''',
        unsafe_allow_html=True,
    )
    info_card(
        "For students",
        "See your weak topics, practise them in Study Camp and track your progress.",
    )
    info_card(
        "For teachers",
        "Set assessments, review AI-suggested marks and keep an eye on the class. "
        "Create an account, then enter the invite code from your administrator "
        "on your Profile page.",
    )

with auth:
    with st.container(border=True):
        status = get_connection_status()
        if status.connected:
            st.markdown("#### Welcome")
            auth_forms()
            privacy_details()
        else:
            st.markdown("#### Try AssessAI")
            st.info(
                "Accounts are not available on this instance because it is not "
                "connected to Supabase. You can still explore everything with "
                "sample data.",
                icon=":material/science:",
            )
            if status.is_error:
                st.error(status.message, icon=":material/error:")

        st.divider()
        st.caption("No account? Look around with sample data first.")
        if st.button(
            "Explore the demo",
            icon=":material/arrow_forward:",
            width="stretch",
        ):
            store.enter_demo()
            st.rerun()

st.caption(PRIVACY_NOTICE)
