"""Shared layout helpers.

Deliberately light on custom CSS: a small colour token block for headings and
badges, and Streamlit-native components for everything else.
"""

from __future__ import annotations

from typing import Optional, Sequence

import streamlit as st

from services import state as store
from utils.config import AI_DISCLAIMER, APP_NAME, APP_TAGLINE, PRIVACY_NOTICE

NAVY = "#0F2D52"
TEAL = "#0F766E"

_STYLES = f"""
<style>
  .assessai-title {{
      color: {NAVY};
      font-size: 1.9rem;
      font-weight: 700;
      margin: 0 0 0.15rem 0;
      line-height: 1.2;
  }}
  .assessai-subtitle {{
      color: #475569;
      font-size: 0.95rem;
      margin: 0 0 0.35rem 0;
  }}
  .assessai-rule {{
      border: none;
      border-top: 3px solid {TEAL};
      width: 72px;
      margin: 0 0 1.1rem 0;
  }}
  .assessai-badge {{
      display: inline-block;
      padding: 0.15rem 0.6rem;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 600;
      line-height: 1.5;
      white-space: nowrap;
  }}
  .assessai-card {{
      border: 1px solid #E2E8F0;
      border-left: 4px solid {TEAL};
      border-radius: 8px;
      padding: 0.85rem 1rem;
      margin-bottom: 0.6rem;
      background: #FFFFFF;
  }}
  .assessai-card h4 {{
      color: {NAVY};
      margin: 0 0 0.2rem 0;
      font-size: 1rem;
  }}
  .assessai-card p {{
      margin: 0;
      color: #475569;
      font-size: 0.86rem;
  }}
</style>
"""


def inject_styles() -> None:
    """Inject the (small) shared style block once per rerun."""
    st.markdown(_STYLES, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", help_text: str = "") -> None:
    """Standard page heading used by every page."""
    inject_styles()
    st.markdown(f'<p class="assessai-title">{title}</p>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<p class="assessai-subtitle">{subtitle}</p>', unsafe_allow_html=True)
    st.markdown('<hr class="assessai-rule" />', unsafe_allow_html=True)
    if help_text:
        st.caption(help_text)


def sidebar_status() -> None:
    """Backend status, the demo identity switch and the privacy notice."""
    status = store.backend_status()
    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.caption(APP_TAGLINE)

        if status["demo_mode"]:
            st.warning("Demo Mode", icon=":material/science:")
        else:
            st.success("Connected to Supabase", icon=":material/cloud_done:")

        if status["is_error"]:
            st.error(status["message"], icon=":material/error:")
        else:
            st.caption(status["message"])

        st.divider()
        _identity_switcher()

        if st.button(
            "Reset demo data",
            width="stretch",
            help="Restore the seeded sample dataset.",
        ):
            store.reset_to_samples()
            st.rerun()

        st.divider()
        st.caption(PRIVACY_NOTICE)


def _identity_switcher() -> None:
    """Pick who you are signed in as. Demo only - not authentication.

    Real sign-in belongs in Supabase Auth, where the role is stored server side
    and cannot be chosen by the person using the app. Until that exists this is
    a convenience for demoing both journeys, and it is labelled as such.
    """
    users = store.get_users()
    if not users:
        st.caption("No users loaded.")
        return

    current = store.get_current_user()
    ordered = sorted(users, key=lambda u: (u.role.value, u.display_name))
    labels = {u.id: f"{u.display_name} · {u.role.label}" for u in ordered}
    index = next(
        (i for i, u in enumerate(ordered) if current and u.id == current.id), 0
    )

    chosen = st.selectbox(
        "Signed in as",
        options=[u.id for u in ordered],
        format_func=lambda uid: labels[uid],
        index=index,
        help="Demo identity switch. This is not real authentication.",
    )
    if current is None or chosen != current.id:
        store.set_current_user(chosen)
        st.rerun()

    st.caption(":material/info: Demo switch, not a login.")


def ai_disclaimer(extra: str = "") -> None:
    st.info(f"{AI_DISCLAIMER} {extra}".strip(), icon=":material/gavel:")


def privacy_notice() -> None:
    st.caption(f":material/lock: {PRIVACY_NOTICE}")


def metric_row(metrics: Sequence[tuple]) -> None:
    """Render (label, value, help) tuples as an even row of st.metric cards."""
    if not metrics:
        return
    columns = st.columns(len(metrics))
    for column, item in zip(columns, metrics):
        label, value = item[0], item[1]
        helper: Optional[str] = item[2] if len(item) > 2 else None
        with column:
            st.metric(label, value, help=helper)


def info_card(title: str, body: str) -> None:
    st.markdown(
        f'<div class="assessai-card"><h4>{title}</h4><p>{body}</p></div>',
        unsafe_allow_html=True,
    )


def empty_state(message: str, hint: str = "", icon: str = ":material/info:") -> None:
    """A consistent, friendly empty state instead of a blank page."""
    st.info(message, icon=icon)
    if hint:
        st.caption(hint)
