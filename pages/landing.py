"""Welcome page - what CampPrep AI is, plus sign in, sign up or try the demo.

Shown by app.py to anyone who is not signed in and has not chosen the demo.
The sign-in forms are the same ones as on the Sign In page. Sign-up collects a
real name and an email, so the full privacy statement sits directly under the
forms rather than only in the one-line notice at the foot of the page.
"""

from __future__ import annotations

import base64
import html
import os

import streamlit as st

from components.auth_forms import auth_forms, privacy_details
from components.layout import info_card_html
from services import state as store
from services.supabase_client import get_connection_status
from utils import palette
from utils.config import APP_NAME, PRIVACY_NOTICE

# Styles are injected once by app.py; a second copy here only added work.
# Everything static below is drawn with st.html rather than st.markdown: it
# paints immediately, while raw-HTML markdown waits for a lazily loaded plugin
# and then pushed the already-drawn widgets down (BUG-023, CLS 0.54).

# There is no sidebar here, so `st.logo` never shows: the wordmark is drawn
# inline, from the light-background version of the logo.
_LOGO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo_dark.svg")
with open(_LOGO, "rb") as handle:
    _logo_uri = "data:image/svg+xml;base64," + base64.b64encode(handle.read()).decode()

status = get_connection_status()

_students_card = info_card_html(
    "For students",
    "See your weak topics, practise them in Study Camp and track your progress.",
    icon="🎒",
    tone="hint",
)
_teachers_card = info_card_html(
    "For teachers",
    "Set assessments, review AI-suggested marks and keep an eye on the class. "
    "Create an account, then enter the invite code from your administrator "
    "on your Profile page.",
    icon="🍎",
    tone="warning",
)

intro, auth = st.columns([1.2, 1], gap="large")

with intro:
    st.html(
        f'''<div class="campprep-logo"><img src="{_logo_uri}" alt="{APP_NAME}" height="34"></div>
<span class="campprep-hero-eyebrow"><b>New</b> IGCSE Years 10–11 · teacher-reviewed</span>
<h1 class="campprep-hero-title">Know where you went <em>wrong</em>.
<span>Fix it before the exam.</span></h1>
<p class="campprep-hero-lede">{APP_NAME} marks your work, shows you which topics
are slipping and points you at what to practise. Pointers, not answers - and a
teacher confirms every mark.</p>
<div class="campprep-chips">
<span class="campprep-chip"><i style="background:{palette.CYAN}">?</i>Hints, never answers</span>
<span class="campprep-chip"><i style="background:{palette.GREEN}">✓</i>Every mark teacher-checked</span>
<span class="campprep-chip"><i style="background:{palette.ORANGE}">★</i>Practise your weak spots</span>
</div>
<div class="campprep-steps">
<div class="campprep-step"><b style="background:{palette.PRIMARY}">1</b>
<h5>Add your work</h5><p>Upload homework or a mock exam you have already done.</p></div>
<div class="campprep-step"><b style="background:{palette.CYAN}">2</b>
<h5>See what slipped</h5><p>Get an estimate and the topics that cost you marks.</p></div>
<div class="campprep-step"><b style="background:{palette.ORANGE}">3</b>
<h5>Fix it in camp</h5><p>Targeted practice until the weak topic is secure.</p></div>
</div>
<div class="campprep-card-pair">{_students_card}{_teachers_card}</div>'''
    )

with auth:
    with st.container(border=True):
        no_account = (
            '<hr class="campprep-rule">'
            '<p class="campprep-small">No account? Look around with sample data first.</p>'
        )
        if status.connected:
            st.html(
                '<div class="campprep-panel-head"><h3>Welcome back 👋</h3>'
                "<p>Sign in, or make an account in under a minute.</p></div>"
            )
            auth_forms()
            privacy_details()
            st.html(no_account)
        else:
            # One block, with a notice in st.info's colours: drawn in one go,
            # so nothing in the panel is painted first and then pushed down.
            panel = (
                f'<div class="campprep-panel-head"><h3>Try {APP_NAME}</h3>'
                "<p>Everything works with sample data - no account needed.</p></div>"
                f'<div class="campprep-notice" style="background:{palette.TINT_PRIMARY[0]};'
                f'color:{palette.TINT_PRIMARY[1]}">Accounts are not available on this '
                "instance because it is not connected to Supabase. You can still "
                "explore everything with sample data.</div>"
            )
            if status.is_error:
                st.html(panel)
                st.error(
                    "We couldn't reach the account service, so accounts are "
                    "unavailable right now.",
                    icon=":material/error:",
                )
                st.html(no_account)
            else:
                st.html(panel + no_account)

        # When accounts are off, the demo is the only way in, so it gets the
        # primary button; otherwise signing in does.
        if st.button(
            "Explore the demo",
            icon=":material/arrow_forward:",
            type="secondary" if status.connected else "primary",
            width="stretch",
        ):
            store.enter_demo()
            st.rerun()

    # A picture of the product rather than a description of it: the kind of
    # topic breakdown a student gets back. Illustrative figures, not data.
    bars = [
        ("Fractions", 86, palette.CORRECT, "Secure"),
        ("Linear equations", 64, palette.PRIMARY, "Developing"),
        ("Ratio and proportion", 38, palette.WARNING, "Needs work"),
    ]
    rows = "".join(
        f'<div class="campprep-bar"><div class="campprep-bar-label"><span>{name}</span>'
        f'<span style="color:{colour}">{band}</span></div>'
        f'<div class="campprep-bar-track"><i style="width:{pct}%;background:{colour}"></i>'
        "</div></div>"
        for name, pct, colour, band in bars
    )
    st.html(
        f'''<div class="campprep-preview">
<div class="campprep-preview-head"><strong>Your topics</strong><span>Example</span></div>
{rows}
<div class="campprep-preview-foot">
<span class="campprep-badge" style="background:{palette.TINT_HINT[0]};color:{palette.TINT_HINT[1]}">? Hint: check the ratio order</span>
<span class="campprep-badge" style="background:{palette.TINT_CORRECT[0]};color:{palette.TINT_CORRECT[1]}">✓ Approved by teacher</span>
</div></div>
<p class="campprep-small campprep-foot">{html.escape(PRIVACY_NOTICE)}</p>'''
    )

