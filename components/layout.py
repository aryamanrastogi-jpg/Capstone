"""Shared layout: the app's design system and the sidebar.

The rule this file exists to enforce: a page describes *what* it is showing,
never *how* it looks. Colours come from `utils.palette`, shape and type come
from `.streamlit/config.toml`, and the handful of things Streamlit's theme
cannot express - card surfaces, badges, and the responsive rules that keep a
row of columns from being squashed on a phone - come from the one style block
below.

Responsiveness, in three moves:
  1. Columns wrap instead of shrinking, and stack outright below 720px.
  2. `metric_row` splits a long run of metrics over several rows rather than
     slicing each one down to an ellipsis.
  3. Buttons and tab strips go full width once stacked, so a thumb has
     something to hit.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

import streamlit as st

from services import state as store
from utils import palette
from utils.config import AI_DISCLAIMER, APP_TAGLINE, PRIVACY_NOTICE

HEADING = palette.PRIMARY_DARK
ACCENT = palette.PRIMARY

# Widths below this stack; between this and the wide breakpoint, columns wrap
# onto as many rows as they need instead of being compressed.
_STACK_BREAKPOINT = "720px"
_WRAP_BREAKPOINT = "1100px"

# Everything rendered through `st.markdown(..., unsafe_allow_html=True)` lands
# inside this container, and Streamlit's own rule for the paragraphs in it is
# more specific than a bare class. Prefixing our selectors with it is what makes
# a heading actually render as a heading.
_IN = '[data-testid="stMarkdownContainer"]'

_STYLES = f"""
<style>
  :root {{
      --aa-primary: {palette.PRIMARY};
      --aa-primary-dark: {palette.PRIMARY_DARK};
      --aa-hint: {palette.HINT};
      --aa-ink: {palette.INK};
      --aa-muted: {palette.MUTED};
      --aa-border: {palette.BORDER};
      --aa-surface: {palette.SURFACE};
      --aa-surface-alt: {palette.SURFACE_ALT};
      --aa-radius: 12px;
      --aa-shadow: 0 1px 2px rgba(15, 23, 42, 0.04),
                   0 8px 24px -16px rgba(15, 23, 42, 0.18);
  }}

  /* --- Page canvas ----------------------------------------------------- */
  /* A measured column rather than the full width of a 27" monitor: long
     feedback text is unreadable at 1800px. */
  .stMainBlockContainer {{
      max-width: 1180px;
      padding-top: 2.4rem;
      padding-bottom: 4rem;
  }}

  /* --- Page header ----------------------------------------------------- */
  {_IN} .assessai-header {{ margin: 0 0 1.15rem 0; }}
  {_IN} .assessai-eyebrow {{
      display: inline-block;
      color: {palette.TINT_PRIMARY[1]};
      background: {palette.TINT_PRIMARY[0]};
      border-radius: 999px;
      padding: 0.1rem 0.6rem;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      margin-bottom: 0.5rem;
  }}
  {_IN} .assessai-title {{
      color: {HEADING};
      font-size: clamp(1.5rem, 1.15rem + 1.4vw, 2.05rem);
      font-weight: 700;
      letter-spacing: -0.015em;
      margin: 0 0 0.2rem 0;
      line-height: 1.15;
  }}
  {_IN} .assessai-subtitle {{
      color: {palette.MUTED};
      font-size: 0.95rem;
      margin: 0;
      max-width: 62ch;
  }}
  {_IN} .assessai-rule {{
      border: none;
      border-top: 3px solid {ACCENT};
      border-radius: 3px;
      width: 64px;
      margin: 0.85rem 0 0 0;
  }}

  /* --- Badges ---------------------------------------------------------- */
  {_IN} .assessai-badge {{
      display: inline-block;
      padding: 0.15rem 0.6rem;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 600;
      line-height: 1.5;
      white-space: nowrap;
  }}
  /* Badges are laid out by the browser, not by st.columns: any number of them
     wraps onto the next line instead of overflowing a fixed column. */
  {_IN} .assessai-badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      margin: 0.2rem 0 0.4rem 0;
  }}

  /* --- Cards ----------------------------------------------------------- */
  {_IN} .assessai-card {{
      border: 1px solid {palette.BORDER};
      border-left: 4px solid {ACCENT};
      border-radius: var(--aa-radius);
      padding: 0.9rem 1.05rem;
      margin-bottom: 0.6rem;
      background: {palette.SURFACE};
      box-shadow: var(--aa-shadow);
  }}
  {_IN} .assessai-card h4 {{
      color: {HEADING};
      margin: 0 0 0.25rem 0;
      font-size: 1rem;
      font-weight: 650;
  }}
  {_IN} .assessai-card p {{
      margin: 0;
      color: {palette.MUTED};
      font-size: 0.86rem;
      line-height: 1.5;
  }}

  {_IN} .assessai-hint {{
      border-left: 4px solid {palette.HINT};
      background: {palette.TINT_HINT[0]};
      color: {palette.TINT_HINT[1]};
      border-radius: 0 var(--aa-radius) var(--aa-radius) 0;
      padding: 0.55rem 0.85rem;
      margin: 0.5rem 0 0.6rem 0;
      font-size: 0.88rem;
      font-weight: 600;
  }}

  /* --- Metrics as tiles ------------------------------------------------ */
  /* Streamlit clips a long metric value to an ellipsis. A weakest-topic tile
     reading "Ratio and ..." tells a student nothing, so values wrap instead. */
  [data-testid="stMetric"] {{
      background: {palette.SURFACE};
      border: 1px solid {palette.BORDER};
      border-radius: var(--aa-radius);
      padding: 0.75rem 0.95rem 0.85rem 0.95rem;
      height: 100%;
      box-shadow: var(--aa-shadow);
  }}
  [data-testid="stMetricValue"] {{
      font-size: clamp(1.15rem, 0.9rem + 0.9vw, 1.6rem);
      line-height: 1.2;
      white-space: normal;
      overflow-wrap: anywhere;
  }}
  [data-testid="stMetricValue"] > div,
  [data-testid="stMetricValue"] p {{
      white-space: normal;
      overflow: visible;
      text-overflow: clip;
  }}
  [data-testid="stMetricLabel"] p {{
      color: {palette.MUTED};
      font-size: 0.8rem;
      font-weight: 600;
      letter-spacing: 0.01em;
  }}

  /* --- Tabs ------------------------------------------------------------ */
  .stTabs [data-baseweb="tab-list"] {{
      gap: 0.25rem;
      overflow-x: auto;
      scrollbar-width: thin;
  }}
  .stTabs [data-baseweb="tab"] {{ white-space: nowrap; }}

  /* --- Sidebar --------------------------------------------------------- */
  [data-testid="stSidebarNavLink"] {{ border-radius: 8px; }}
  [data-testid="stSidebarUserContent"] {{ padding-top: 0.75rem; }}
  {_IN} .assessai-brand {{
      font-size: 0.78rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: {palette.MUTED};
      margin: 0 0 0.2rem 0;
  }}

  /* --- Responsive ------------------------------------------------------ */
  /* Columns wrap rather than compress once the row would get tight. */
  @media (max-width: {_WRAP_BREAKPOINT}) {{
      [data-testid="stHorizontalBlock"] {{
          flex-wrap: wrap;
          row-gap: 0.75rem;
      }}
      [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
          min-width: 220px;
      }}
  }}

  /* Below the stack breakpoint every column is its own full-width row. */
  @media (max-width: {_STACK_BREAKPOINT}) {{
      .stMainBlockContainer {{
          padding-top: 1.4rem;
          padding-left: 1rem;
          padding-right: 1rem;
          padding-bottom: 2.5rem;
      }}
      [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
          flex: 1 1 100% !important;
          min-width: 100% !important;
          width: 100% !important;
      }}
      /* Full-width controls: a half-width button is a hard target on a phone. */
      .stButton > button,
      .stDownloadButton > button,
      .stFormSubmitButton > button {{
          width: 100% !important;
      }}
      [data-testid="stMetric"] {{ padding: 0.65rem 0.8rem 0.75rem 0.8rem; }}
      {_IN} .assessai-subtitle {{ font-size: 0.9rem; }}
  }}

  /* Wide tables scroll inside themselves rather than pushing the page
     sideways. */
  [data-testid="stDataFrame"], [data-testid="stTable"] {{ overflow-x: auto; }}

  @media (prefers-reduced-motion: reduce) {{
      * {{
          animation-duration: 0.01ms !important;
          transition-duration: 0.01ms !important;
      }}
  }}
</style>
"""


def inject_styles() -> None:
    """Inject the shared style block.

    Called once from `app.py` before anything draws, and once from
    `page_header` so that a page rendered on its own - as the tests do - is
    still styled. Every other helper assumes the block is already there rather
    than adding another copy of it to the DOM on each call.
    """
    st.markdown(_STYLES, unsafe_allow_html=True)


def page_header(
    title: str,
    subtitle: str = "",
    help_text: str = "",
    eyebrow: Optional[str] = None,
) -> None:
    """Standard page heading used by every page.

    The eyebrow is the small capitalised label above the title, and it says
    where in the workflow this page sits. Left alone it is read off the
    navigation, so a page and the menu item that leads to it can never
    disagree; pass a string to override it, or "" to leave it off.
    """
    inject_styles()
    if eyebrow is None:
        eyebrow = _section_for(title)
    parts = ['<div class="assessai-header">']
    if eyebrow:
        parts.append(f'<span class="assessai-eyebrow">{eyebrow}</span>')
    parts.append(f'<p class="assessai-title">{title}</p>')
    if subtitle:
        parts.append(f'<p class="assessai-subtitle">{subtitle}</p>')
    parts.append('<hr class="assessai-rule" /></div>')
    st.markdown("".join(parts), unsafe_allow_html=True)
    if help_text:
        st.caption(help_text)


def _section_for(title: str) -> str:
    """The navigation section a page title belongs to, or "" if it has none.

    Imported here rather than at module scope so that `components.navigation`,
    which is only needed for this lookup, is not a hard dependency of every
    page that draws a heading.
    """
    from components.navigation import PAGE_SPECS

    match = next((spec for spec in PAGE_SPECS if spec["title"] == title), None)
    return match["section"] if match else ""


def sidebar_status() -> None:
    """Backend status, the demo identity switch and the privacy notice."""
    status = store.backend_status()
    with st.sidebar:
        # The wordmark is drawn above the navigation by `st.logo` in app.py, so
        # all this block owes the reader is what the app is for and whether it
        # is talking to a real backend.
        st.markdown('<p class="assessai-brand">About</p>', unsafe_allow_html=True)
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

        # Only meaningful while the sample data IS the data. Offering it to a
        # signed-in user would imply it resets their saved work, which it does
        # not touch.
        if status["demo_mode"] and st.button(
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

    Hidden entirely once somebody is really signed in: the role then comes from
    their profile row, and offering a control that appears to change it would be
    a lie about what the app can do.
    """
    from services import auth_service

    signed_in = auth_service.current_user()
    if signed_in is not None:
        st.markdown(f"**{signed_in.display_name}**")
        st.caption(f"{signed_in.role.label} · signed in")
        if st.button("Sign out", width="stretch"):
            auth_service.sign_out()
            st.rerun()
        return

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


def metric_row(metrics: Sequence[tuple], per_row: int = 4) -> None:
    """Render (label, value, help) tuples as rows of st.metric tiles.

    Splitting at `per_row` is the responsive part: five metrics in one
    `st.columns` call gives five unreadable slivers, whereas four then one
    stays legible, and the CSS above collapses each row to a single column on
    a phone.
    """
    if not metrics:
        return
    items = list(metrics)
    per_row = max(1, per_row)
    for start in range(0, len(items), per_row):
        chunk = items[start : start + per_row]
        columns = st.columns(len(chunk))
        for column, item in zip(columns, chunk):
            label, value = item[0], item[1]
            helper: Optional[str] = item[2] if len(item) > 2 else None
            with column:
                st.metric(label, value, help=helper)


def badge_row(badges: Iterable[str]) -> None:
    """Draw pre-rendered badge HTML in a container that wraps.

    Badges come from `components.status_badges` with `render=False`. Laying
    them out here rather than in columns means a question with six error chips
    wraps onto a second line instead of squashing them.
    """
    html = "".join(badges)
    if not html:
        return
    st.markdown(f'<div class="assessai-badges">{html}</div>', unsafe_allow_html=True)


def info_card(title: str, body: str) -> None:
    st.markdown(
        f'<div class="assessai-card"><h4>{title}</h4><p>{body}</p></div>',
        unsafe_allow_html=True,
    )


def hint_note(text: str) -> None:
    """A hint heading, in the hint colour.

    Hints get their own colour so a student can tell at a glance that what
    follows is a nudge, not a verdict on their answer.
    """
    st.markdown(f'<div class="assessai-hint">{text}</div>', unsafe_allow_html=True)


def empty_state(message: str, hint: str = "", icon: str = ":material/info:") -> None:
    """A consistent, friendly empty state instead of a blank page."""
    st.info(message, icon=icon)
    if hint:
        st.caption(hint)
