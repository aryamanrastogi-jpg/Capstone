"""Welcome page - what Camp Prep AI is, plus sign in, sign up or try the demo.

Shown by app.py to anyone who is not signed in and has not chosen the demo.
The look follows the HackerRank landing page Aryaman picked: a dark canvas, a
huge centred headline with a glowing button under it, a white "choose your
path" panel with one dark card per audience, then how it works and the
account card. The styles live with the rest in components/layout.py.

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
from services import state as store
from services.supabase_client import get_connection_status
from utils import palette
from utils.config import APP_NAME, PRIVACY_NOTICE

# Styles are injected once by app.py; a second copy here only added work.
# Everything static below is drawn with st.html rather than st.markdown: it
# paints immediately, while raw-HTML markdown waits for a lazily loaded plugin
# and then pushed the already-drawn widgets down (BUG-023, CLS 0.54).

# There is no sidebar here, so `st.logo` never shows. The emblem on its white
# disc holds up on the dark canvas; the name is set beside it as text.
_LOGO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo.svg")
with open(_LOGO, "rb") as handle:
    _logo_uri = "data:image/svg+xml;base64," + base64.b64encode(handle.read()).decode()

status = get_connection_status()
_brand = f'<span class="cp-brand"><img src="{_logo_uri}" alt="">{APP_NAME}</span>'
# Without accounts the card at the foot only offers the demo.
_account_label = "Sign in" if status.connected else "Try it"

st.html(
    f'''<nav class="cp-nav" aria-label="{APP_NAME}">{_brand}
<div class="cp-nav-links"><a href="#how-it-works">How it works</a>
<a href="#who-its-for">Students and teachers</a>
<a class="cp-nav-pill" href="#account">{_account_label}</a></div></nav>
<section class="cp-hero">
<span class="campprep-hero-eyebrow"><b>New</b> IGCSE Years 10–11 · teacher-reviewed</span>
<h1 class="campprep-hero-title">Know where you went wrong.
<span>Fix it before the <i aria-hidden="true"></i>exam.</span></h1>
<p class="campprep-hero-lede">{APP_NAME} marks your work, shows you which topics
are slipping and points you at what to practise. Pointers, not answers - and a
teacher confirms every mark.</p>
</section>'''
)

with st.container(horizontal=True, horizontal_alignment="center", key="landing_cta"):
    if st.button(
        "Explore the demo",
        icon=":material/arrow_forward:",
        type="primary",
        key="landing_demo",
    ):
        store.enter_demo()
        st.rerun()
    if status.connected:
        st.html(
            '<a class="cp-ghost" href="#account">Sign in or create an account</a>',
            width="content",
        )

st.html(
    f'''<div class="cp-proof">
<span><b style="color:{palette.CYAN}">?</b>Hints, never answers</span>
<span><b style="color:{palette.GREEN}">✓</b>Every mark teacher-checked</span>
<span><b style="color:{palette.ORANGE}">★</b>Practise your weak spots</span>
</div>
<section class="cp-panel" id="who-its-for">
<span class="cp-kicker">Students and teachers</span>
<h2 class="cp-section-title">Choose your <em>path</em></h2>
<p class="cp-section-lede">Students find and fix their weak topics. Teachers keep
an eye on the class and sign off every mark.</p>
<div class="cp-paths">
<article class="cp-path">
<h3>For students</h3>
<p>See your weak topics, practise them in Study Camp and track your progress.</p>
<ul><li>Upload homework or a mock exam you have already done</li>
<li>See which topics cost you marks</li>
<li>Practise weak spots in Study Camp, with hints rather than answers</li></ul>
<a href="#account">Get started →</a>
</article>
<article class="cp-path cp-path--teacher">
<h3>For teachers</h3>
<p>Set assessments, review AI-suggested marks and keep an eye on the class.</p>
<ul><li>Set an assessment and upload the class's responses</li>
<li>Review every AI-suggested mark before it counts</li>
<li>See where the class is slipping</li></ul>
<small>Create an account, then enter the invite code from your administrator
on your Profile page.</small>
<a href="#account">Set up teacher access →</a>
</article>
</div>
</section>'''
)

# A picture of the product rather than a description of it: the kind of
# topic breakdown a student gets back. Illustrative figures, not data. On the
# dark card the bands use the palette's bright colours, and a lighter blue
# stands in for PRIMARY, which would vanish against it.
bars = [
    ("Fractions", 86, palette.CORRECT, "Secure"),
    ("Linear equations", 64, "#6874D6", "Developing"),
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
    f'''<section class="cp-how" id="how-it-works">
<div>
<span class="cp-kicker">How it works</span>
<h2 class="cp-section-title">From past work to <em>exam-ready</em></h2>
<p class="cp-section-lede">Bring the work you have already done. {APP_NAME}
finds the pattern across all of it.</p>
<div class="campprep-steps">
<div class="campprep-step"><b>01</b><h2>Add your work</h2>
<p>Upload homework or a mock exam you have already done.</p></div>
<div class="campprep-step"><b>02</b><h2>See what slipped</h2>
<p>Get an estimate and the topics that cost you marks.</p></div>
<div class="campprep-step"><b>03</b><h2>Fix it in camp</h2>
<p>Targeted practice until the weak topic is secure.</p></div>
</div>
</div>
<div class="campprep-preview">
<div class="campprep-preview-head"><strong>Your topics</strong><span>Example</span></div>
{rows}
<div class="campprep-preview-foot">
<span style="background:rgba(29,206,216,0.12);color:{palette.CYAN}">? Hint: check the ratio order</span>
<span style="background:rgba(118,196,87,0.14);color:{palette.GREEN}">✓ Approved by teacher</span>
</div></div>
</section>'''
)

with st.container(key="landing_account_row"):
    # The jump target sits above both columns: on the heading beside the
    # card, the taller, centred card started above the screen (cut in half).
    st.html('<div id="account"></div>')
    intro, auth = st.columns([1, 1.05], gap="large", vertical_alignment="center")

with intro:
    st.html(
        '''<div class="cp-account-copy">
<span class="cp-kicker">Get started</span>
<h2 class="cp-section-title">Start in under <em>a minute</em></h2>
<p class="cp-section-lede">Make an account to keep your work and progress, or
look around with sample data first. AI marks are estimates until a teacher
confirms them.</p>
</div>'''
    )

with auth:
    with st.container(border=True, key="landing_account"):
        no_account = (
            '<hr class="campprep-rule">'
            '<p class="campprep-small">No account? Look around with sample data first: '
            "use Explore the demo at the top of the page.</p>"
        )
        if status.connected:
            st.html(
                '<div class="campprep-panel-head"><h2>Welcome back 👋</h2>'
                "<p>Sign in, or make an account in under a minute.</p></div>"
            )
            auth_forms()
            privacy_details()
            st.html(no_account)
        else:
            # One block, with a notice in st.info's colours: drawn in one go,
            # so nothing in the panel is painted first and then pushed down.
            panel = (
                f'<div class="campprep-panel-head"><h2>Try {APP_NAME}</h2>'
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

st.html(
    f'''<footer class="cp-footer">{_brand}
<p>{html.escape(PRIVACY_NOTICE)}</p></footer>'''
)
