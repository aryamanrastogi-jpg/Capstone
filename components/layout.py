"""Shared layout: the app's design system and the sidebar.

The rule this file exists to enforce: a page describes *what* it is showing,
never *how* it looks. Colours come from `utils.palette`, shape and type come
from `.streamlit/config.toml`, and the things Streamlit's theme cannot express
- the page banner, card surfaces, chunky buttons, badges, and the responsive
rules that keep a row of columns from being squashed on a phone - come from
the one style block below.

The look, in one breath: a deep indigo sidebar rail, a pale indigo canvas,
white cards with soft shadows, and a gradient banner at the top of every page.
The six palette colours appear together in one place only - the stripe under
the banner - and everywhere else each colour keeps the single job it was
given in `utils.palette`.

Responsiveness, in three moves:
  1. Columns wrap instead of shrinking, and stack outright below 720px.
  2. `metric_row` splits a long run of metrics over several rows rather than
     slicing each one down to an ellipsis.
  3. Buttons and tab strips go full width once stacked, so a thumb has
     something to hit.
"""

from __future__ import annotations

from html import escape
from typing import Iterable, Optional, Sequence

import streamlit as st

from services import state as store
from utils import palette
from utils.config import AI_DISCLAIMER, PRIVACY_NOTICE

HEADING = palette.INK
ACCENT = palette.PRIMARY

# Widths below this stack; between this and the wide breakpoint, columns wrap
# onto as many rows as they need instead of being compressed.
_STACK_BREAKPOINT = "720px"
_WRAP_BREAKPOINT = "1100px"

# Everything rendered through `st.markdown(..., unsafe_allow_html=True)` lands
# inside this container, and Streamlit's own rule for the paragraphs in it is
# more specific than a bare class. Prefixing our selectors with it is what makes
# a heading actually render as a heading.
# `st.html` blocks (used where content must paint without waiting for the
# markdown renderer, e.g. the welcome page) are matched the same way.
_IN = ':is([data-testid="stMarkdownContainer"], [data-testid="stHtml"])'

_SIDEBAR = '[data-testid="stSidebar"]'

# The banner gradient: deep blue into indigo into night, with a cyan glow top
# right and a warm orange one bottom right so the corner never looks flat.
_BANNER = (
    "radial-gradient(120% 140% at 100% 0%, rgba(29, 206, 216, 0.38) 0%, "
    "rgba(29, 206, 216, 0) 42%), "
    "radial-gradient(90% 120% at 85% 120%, rgba(255, 145, 0, 0.30) 0%, "
    "rgba(255, 145, 0, 0) 48%), "
    f"linear-gradient(125deg, {palette.BLUE_DEEP} 0%, {palette.BLUE_INDIGO} 55%, "
    f"{palette.NIGHT} 100%)"
)


def _stripe(colours: Sequence[str]) -> str:
    """Equal hard-stopped bands of colour, left to right - the brand motif."""
    step = 100 / len(colours)
    bands = ", ".join(
        f"{colour} {i * step:.2f}% {(i + 1) * step:.2f}%"
        for i, colour in enumerate(colours)
    )
    return f"linear-gradient(90deg, {bands})"


# All six on a light surface. On the dark banner and sidebar the two blues
# would vanish into the background, so those carry the four accents only.
_STRIPE = _stripe(palette.PALETTE)
_STRIPE_ON_DARK = _stripe((palette.CYAN, palette.GREEN, palette.ORANGE, palette.RED))

# Tile accents, handed out by column position so a row of four metrics reads
# as four different things at a glance.
_TILE_ACCENTS = (palette.PRIMARY, palette.HINT, palette.WARNING, palette.CORRECT)

# Icon tile tones for `info_card`: (tile background, glyph colour).
_TONES = {
    "primary": (palette.TINT_PRIMARY[0], palette.PRIMARY),
    "hint": (palette.TINT_HINT[0], palette.TINT_HINT[1]),
    "correct": (palette.TINT_CORRECT[0], palette.TINT_CORRECT[1]),
    "warning": (palette.TINT_WARNING[0], palette.TINT_WARNING[1]),
    "incorrect": (palette.TINT_INCORRECT[0], palette.TINT_INCORRECT[1]),
}

_tile_rules = "\n".join(
    f'  [data-testid="stColumn"]:nth-child(4n+{i + 1}) [data-testid="stMetric"] '
    f"{{ --cp-tile: {colour}; }}"
    for i, colour in enumerate(_TILE_ACCENTS)
)

_STYLES = f"""
<style>
  :root {{
      --cp-primary: {palette.PRIMARY};
      --cp-primary-dark: {palette.PRIMARY_DARK};
      --cp-lip: {palette.PRIMARY_LIP};
      --cp-hint: {palette.HINT};
      --cp-ink: {palette.INK};
      --cp-muted: {palette.MUTED};
      --cp-border: {palette.BORDER};
      --cp-surface: {palette.SURFACE};
      --cp-surface-alt: {palette.SURFACE_ALT};
      --cp-radius: 18px;
      --cp-radius-sm: 12px;
      --cp-shadow: 0 1px 2px rgba(14, 19, 64, 0.04),
                   0 10px 30px -18px rgba(27, 44, 193, 0.28);
      --cp-shadow-lift: 0 2px 4px rgba(14, 19, 64, 0.05),
                        0 18px 40px -20px rgba(27, 44, 193, 0.38);
      --cp-stripe: {_STRIPE};
      --cp-stripe-dark: {_STRIPE_ON_DARK};
  }}

  /* --- Page canvas ----------------------------------------------------- */
  /* A measured column rather than the full width of a 27" monitor: long
     feedback text is unreadable at 1800px. */
  /* The top padding clears Streamlit's header strip (56px), which the page
     banner otherwise starts underneath. */
  .stMainBlockContainer {{
      max-width: 1180px;
      padding-top: 4.4rem;
      padding-bottom: 4rem;
  }}
  [data-testid="stHeader"] {{
      background: rgba(246, 247, 254, 0.8);
      backdrop-filter: blur(10px);
  }}
  .stMainBlockContainer h1, .stMainBlockContainer h2,
  .stMainBlockContainer h3, .stMainBlockContainer h4 {{
      letter-spacing: -0.02em;
      color: {palette.INK};
  }}
  hr {{ border-color: {palette.BORDER} !important; }}

  /* --- Page banner ----------------------------------------------------- */
  {_IN} .campprep-header {{
      position: relative;
      overflow: hidden;
      background: {_BANNER};
      border-radius: 24px;
      padding: 1.7rem 2rem 2.1rem 2rem;
      margin: 0 0 1.4rem 0;
      box-shadow: 0 20px 44px -26px rgba(27, 44, 193, 0.75);
      isolation: isolate;
  }}
  /* Two quiet shapes in the corner: a cyan ring and an orange dot. */
  {_IN} .campprep-header::before {{
      content: "";
      position: absolute;
      right: -70px;
      top: -90px;
      width: 260px;
      height: 260px;
      border-radius: 50%;
      border: 34px solid rgba(255, 255, 255, 0.07);
      z-index: -1;
  }}
  {_IN} .campprep-header::after {{
      content: "";
      position: absolute;
      right: 150px;
      bottom: 26px;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: {palette.ORANGE};
      box-shadow: -60px -54px 0 -3px {palette.CYAN}, 90px -70px 0 -4px {palette.GREEN};
      opacity: 0.9;
      z-index: -1;
  }}
  {_IN} .campprep-stripe {{
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: 6px;
      background: var(--cp-stripe-dark);
  }}
  {_IN} .campprep-eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      color: #FFFFFF;
      background: rgba(255, 255, 255, 0.14);
      border: 1px solid rgba(255, 255, 255, 0.22);
      border-radius: 999px;
      padding: 0.18rem 0.7rem;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 0.7rem;
  }}
  {_IN} .campprep-eyebrow::before {{
      content: "";
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: {palette.CYAN};
  }}
  {_IN} .campprep-title {{
      color: #FFFFFF;
      font-size: clamp(1.6rem, 1.2rem + 1.5vw, 2.3rem);
      font-weight: 800;
      letter-spacing: -0.03em;
      margin: 0 0 0.3rem 0;
      padding: 0;
      line-height: 1.1;
  }}
  {_IN} .campprep-header [data-testid="stHeaderActionElements"] {{
      display: none;
  }}
  {_IN} .campprep-subtitle {{
      color: rgba(233, 236, 255, 0.86);
      font-size: 0.98rem;
      margin: 0;
      max-width: 62ch;
  }}

  /* --- Badges ---------------------------------------------------------- */
  {_IN} .campprep-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      padding: 0.2rem 0.7rem;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 700;
      line-height: 1.5;
      white-space: nowrap;
  }}
  /* Badges are laid out by the browser, not by st.columns: any number of them
     wraps onto the next line instead of overflowing a fixed column. */
  {_IN} .campprep-badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      margin: 0.2rem 0 0.5rem 0;
  }}

  /* --- Cards ----------------------------------------------------------- */
  {_IN} .campprep-card {{
      display: flex;
      gap: 0.9rem;
      align-items: flex-start;
      border: 1px solid {palette.BORDER};
      border-radius: var(--cp-radius);
      padding: 1rem 1.1rem;
      margin-bottom: 0.7rem;
      background: {palette.SURFACE};
      box-shadow: var(--cp-shadow);
      transition: transform 160ms ease, box-shadow 160ms ease;
  }}
  {_IN} .campprep-card:hover {{
      transform: translateY(-2px);
      box-shadow: var(--cp-shadow-lift);
  }}
  {_IN} .campprep-card-icon {{
      flex: 0 0 auto;
      display: grid;
      place-items: center;
      width: 42px;
      height: 42px;
      border-radius: 13px;
      font-size: 1.2rem;
      font-weight: 800;
      line-height: 1;
  }}
  {_IN} .campprep-card h2 {{
      color: {HEADING};
      margin: 0 0 0.2rem 0;
      padding: 0;
      font-size: 1.02rem;
      font-weight: 750;
  }}
  {_IN} .campprep-card p {{
      margin: 0;
      color: {palette.MUTED};
      font-size: 0.88rem;
      line-height: 1.55;
  }}

  {_IN} .campprep-hint {{
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      background: {palette.TINT_HINT[0]};
      color: {palette.TINT_HINT[1]};
      border: 1px solid rgba(29, 206, 216, 0.45);
      border-radius: 999px;
      padding: 0.3rem 0.85rem 0.3rem 0.35rem;
      margin: 0.5rem 0 0.6rem 0;
      font-size: 0.86rem;
      font-weight: 700;
  }}
  {_IN} .campprep-hint::before {{
      content: "?";
      display: grid;
      place-items: center;
      width: 22px;
      height: 22px;
      border-radius: 50%;
      background: {palette.TINT_HINT[1]};
      color: #FFFFFF;
      font-size: 0.8rem;
      font-weight: 800;
  }}

  /* --- Bordered containers --------------------------------------------- */
  /* `st.container(border=True)` becomes a white card on the tinted canvas. */
  /* Streamlit marks a bordered container only by the scroll attributes it
     gives it - plain layout blocks never carry them. */
  .stMainBlockContainer [data-testid="stVerticalBlock"][data-test-scroll-behavior] {{
      background: {palette.SURFACE};
      border-color: {palette.BORDER};
      border-radius: 22px;
      box-shadow: var(--cp-shadow);
  }}

  /* --- Metrics as tiles ------------------------------------------------ */
  /* Streamlit clips a long metric value to an ellipsis. A weakest-topic tile
     reading "Ratio and ..." tells a student nothing, so values wrap instead. */
  [data-testid="stMetric"] {{
      --cp-tile: {palette.PRIMARY};
      position: relative;
      overflow: hidden;
      background: {palette.SURFACE};
      border: 1px solid {palette.BORDER};
      border-radius: var(--cp-radius);
      padding: 1rem 1.1rem 1.05rem 1.1rem;
      height: 100%;
      box-shadow: var(--cp-shadow), inset 0 4px 0 var(--cp-tile);
  }}
  /* A soft blob of the tile colour in the corner. */
  [data-testid="stMetric"]::after {{
      content: "";
      position: absolute;
      right: -22px;
      top: -22px;
      width: 76px;
      height: 76px;
      border-radius: 50%;
      background: var(--cp-tile);
      opacity: 0.1;
      pointer-events: none;
  }}
{_tile_rules}
  [data-testid="stMetricValue"] {{
      font-size: clamp(1.25rem, 0.95rem + 1vw, 1.85rem);
      line-height: 1.15;
      letter-spacing: -0.02em;
      color: {palette.INK};
      white-space: normal;
      /* `break-word`, not `anywhere`: `anywhere` also shrinks the tile's
         min-content width, which collapses the column to nothing. */
      overflow-wrap: break-word;
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
      font-weight: 700;
      letter-spacing: 0.07em;
      text-transform: uppercase;
  }}

  /* --- Buttons --------------------------------------------------------- */
  /* Chunky, with a darker lip underneath: a press sinks the button into it.
     Deliberately playful - the people pressing them are 12 to 15. */
  .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button,
  [data-testid="stPageLink"] a {{
      font-weight: 700;
      border-radius: 14px;
      transition: transform 90ms ease, box-shadow 90ms ease,
                  background-color 150ms ease, border-color 150ms ease;
  }}
  .stMainBlockContainer button[kind="secondary"],
  .stMainBlockContainer button[kind="secondaryFormSubmit"] {{
      background: {palette.SURFACE};
      border: 1.5px solid {palette.BORDER};
      box-shadow: 0 3px 0 #D5DAF3;
  }}
  .stMainBlockContainer button[kind="secondary"]:hover,
  .stMainBlockContainer button[kind="secondaryFormSubmit"]:hover {{
      border-color: {palette.PRIMARY};
      color: {palette.PRIMARY};
      transform: translateY(-1px);
      box-shadow: 0 4px 0 #C3CAF0;
  }}
  button[kind="primary"], button[kind="primaryFormSubmit"] {{
      background: linear-gradient(180deg, #2A3BDB 0%, {palette.PRIMARY} 100%);
      border: none;
      color: #FFFFFF;
      box-shadow: 0 4px 0 {palette.PRIMARY_LIP},
                  0 10px 20px -10px rgba(27, 44, 193, 0.7);
  }}
  button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover {{
      background: linear-gradient(180deg, #3446E4 0%, #2233CC 100%);
      color: #FFFFFF;
      transform: translateY(-1px);
      box-shadow: 0 5px 0 {palette.PRIMARY_LIP},
                  0 14px 24px -12px rgba(27, 44, 193, 0.75);
  }}
  .stMainBlockContainer button:active:not(:disabled) {{
      transform: translateY(3px) !important;
      box-shadow: 0 1px 0 {palette.PRIMARY_LIP} !important;
  }}
  .stMainBlockContainer button[kind^="secondary"]:active:not(:disabled) {{
      box-shadow: 0 0 0 #C3CAF0 !important;
  }}

  /* --- Inputs ---------------------------------------------------------- */
  /* Inputs keep the theme's tinted fill; focus adds a soft primary halo.
     Streamlit 1.5x draws its widgets with react-aria, so the hooks are the
     `...RootElement` test ids rather than the old BaseWeb attributes. */
  .stMainBlockContainer [data-testid$="RootElement"],
  .stMainBlockContainer [data-testid="stNumberInputContainer"] {{
      border-radius: 12px;
      transition: box-shadow 150ms ease;
  }}
  .stMainBlockContainer [data-testid$="RootElement"]:focus-within,
  .stMainBlockContainer [data-testid="stNumberInputContainer"]:focus-within {{
      box-shadow: 0 0 0 4px rgba(27, 44, 193, 0.12);
  }}
  [data-testid="stFileUploaderDropzone"] {{
      background: {palette.TINT_PRIMARY[0]};
      border: 2px dashed #AEB6EC;
      border-radius: var(--cp-radius);
  }}
  [data-testid="stWidgetLabel"] p {{ font-weight: 650; }}

  /* --- Tabs ------------------------------------------------------------ */
  /* A segmented control rather than an underlined strip. */
  [data-testid="stTabs"] [role="tablist"] {{
      gap: 0.25rem;
      background: {palette.SURFACE_ALT};
      border: 1px solid {palette.BORDER};
      border-radius: 14px;
      padding: 0.3rem;
      width: fit-content;
      max-width: 100%;
      height: auto;
      overflow-x: auto;
      scrollbar-width: thin;
      box-shadow: none;
  }}
  [data-testid="stTab"] {{
      white-space: nowrap;
      height: auto;
      padding: 0.42rem 0.95rem;
      border-radius: 10px;
      background: transparent;
      transition: background-color 150ms ease;
  }}
  [data-testid="stTab"] p {{ font-weight: 650; color: {palette.MUTED}; }}
  [data-testid="stTab"]:hover p {{ color: {palette.PRIMARY}; }}
  [data-testid="stTab"][aria-selected="true"] {{
      background: {palette.SURFACE};
      box-shadow: 0 1px 2px rgba(14, 19, 64, 0.08),
                  0 4px 10px -6px rgba(27, 44, 193, 0.4);
  }}
  [data-testid="stTab"][aria-selected="true"] p {{ color: {palette.PRIMARY}; }}
  /* The sliding underline - the white pill already says which tab is open. */
  [data-testid="stTab"] > div:not([data-testid]) {{ display: none; }}

  /* --- Alerts, expanders, tables --------------------------------------- */
  [data-testid="stAlertContainer"] {{
      border-radius: 14px;
      border: 1px solid rgba(14, 19, 64, 0.06);
  }}
  [data-testid="stExpander"] details {{
      background: {palette.SURFACE};
      border-radius: 14px;
      border-color: {palette.BORDER};
  }}
  [data-testid="stExpander"] summary p {{ font-weight: 650; }}
  [data-testid="stDataFrame"], [data-testid="stTable"] {{
      border-radius: 14px;
      overflow-x: auto;
  }}
  [data-testid="stProgress"] [role="progressbar"] > div > div > div {{
      background: linear-gradient(90deg, {palette.CYAN}, {palette.PRIMARY});
  }}

  /* --- Sidebar --------------------------------------------------------- */
  /* One dark rail: blue at the top fading to night at the foot. */
  {_SIDEBAR} {{
      background: linear-gradient(185deg, {palette.BLUE_DEEP} 0%, #16209F 38%,
                  {palette.NIGHT} 100%);
  }}
  {_SIDEBAR} [data-testid="stSidebarContent"],
  {_SIDEBAR} [data-testid="stSidebarHeader"] {{ background: transparent; }}
  {_SIDEBAR}::after {{
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: 4px;
      background: var(--cp-stripe-dark);
      pointer-events: none;
  }}
  [data-testid="stSidebarNavLink"] {{
      border-radius: 12px;
      margin: 1px 0;
      transition: background-color 150ms ease;
  }}
  [data-testid="stSidebarNavLink"]:hover {{ background: rgba(255, 255, 255, 0.08); }}
  [data-testid="stSidebarNavLink"][aria-current="page"] {{
      background: rgba(29, 206, 216, 0.16);
      box-shadow: inset 3px 0 0 {palette.CYAN};
  }}
  [data-testid="stSidebarNavLink"][aria-current="page"] span {{
      color: #FFFFFF !important;
      font-weight: 700;
  }}
  [data-testid="stNavSectionHeader"] p {{
      font-size: 0.8rem !important;  /* 12px: the smallest legible label */
      font-weight: 700 !important;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #E9ECFF !important;
  }}
  [data-testid="stSidebarNavSeparator"] {{ border-color: rgba(255, 255, 255, 0.1); }}
  [data-testid="stSidebarUserContent"] {{ padding-top: 0.75rem; }}
  /* Under the menu: who you are, then the demo controls and Feedback. */
  {_IN} .cp-side-pill {{
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      margin: 0 0 0.2rem 0;
      padding: 0.3rem 0.75rem;
      border-radius: 999px;
      background: rgba(255, 145, 0, 0.16);
      color: #FFD9A8;
      font-size: max(12px, 0.78rem);
      font-weight: 650;
  }}
  {_IN} .cp-side-pill b {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: {palette.ORANGE};
  }}
  {_IN} .cp-side-who {{
      display: flex;
      align-items: center;
      gap: 0.7rem;
      padding: 0.7rem 0.8rem;
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.07);
      border: 1px solid rgba(255, 255, 255, 0.1);
  }}
  {_IN} .cp-side-who img, {_IN} .cp-side-who i {{
      flex: none;
      width: 38px;
      height: 38px;
      border-radius: 50%;
      object-fit: cover;
  }}
  {_IN} .cp-side-who i {{
      display: grid;
      place-items: center;
      font-style: normal;
      font-weight: 800;
      background: {palette.CYAN};
      color: {palette.NIGHT};
  }}
  {_IN} .cp-side-who b {{ display: block; color: #FFFFFF; font-size: 0.92rem; }}
  {_IN} .cp-side-who span {{ display: block; color: #C9CEF5; font-size: max(12px, 0.78rem); }}
  .st-key-sidebar_demo_actions {{ gap: 0.5rem; }}
  .st-key-sidebar_demo_actions button {{ min-height: 2.3rem; padding: 0 0.5rem; font-size: 0.85rem; }}
  {_SIDEBAR} .st-key-sidebar_feedback {{
      margin-top: 0.4rem;
      padding-top: 0.9rem;
      border-top: 1px solid rgba(255, 255, 255, 0.12);
  }}
  {_SIDEBAR} .st-key-sidebar_feedback button[kind] {{
      background: rgba(29, 206, 216, 0.14);
      border: 1px solid rgba(29, 206, 216, 0.55);
      box-shadow: none;
  }}
  {_SIDEBAR} .st-key-sidebar_feedback button[kind]:hover {{
      background: rgba(29, 206, 216, 0.24);
      border-color: {palette.CYAN};
  }}
  {_SIDEBAR} [data-testid="stCaptionContainer"] p {{ color: #E9ECFF; }}
  {_SIDEBAR} hr {{ border-color: rgba(255, 255, 255, 0.12) !important; }}
  {_SIDEBAR} button[kind="secondary"] {{
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.18);
      color: #FFFFFF;
      box-shadow: 0 3px 0 rgba(4, 8, 48, 0.55);
  }}
  {_SIDEBAR} button[kind="secondary"]:hover {{
      background: rgba(255, 255, 255, 0.14);
      border-color: {palette.CYAN};
      color: #FFFFFF;
  }}
  {_SIDEBAR} button[kind="secondary"]:active {{
      transform: translateY(3px);
      box-shadow: 0 0 0 transparent;
  }}

  /* --- Landing page ---------------------------------------------------- */
  /* The welcome page is the app's one dark screen, after the HackerRank
     landing page Aryaman picked: a near-black canvas, a huge centred
     headline with an icon set into it, a green glow under the main button,
     then a white "choose your path" panel and dark product sections. Every
     rule is scoped to this page (through its h1 or a cp- class), so the
     inner pages keep their pale indigo canvas. */
  .stApp:has(.campprep-hero-title) {{
      background: {palette.NIGHT_DEEP};
      color: {palette.ON_DARK};
  }}
  /* Streamlit's header strip lies over the top bar and swallowed clicks on
     its links. Clicks fall through it; its own menu button still takes them. */
  .stApp:has(.campprep-hero-title) [data-testid="stHeader"] {{
      background: transparent;
      backdrop-filter: none;
  }}
  .stApp:has(.campprep-hero-title) [data-testid="stHeader"],
  .stApp:has(.campprep-hero-title) [data-testid="stHeader"] * {{
      pointer-events: none;
  }}
  .stApp:has(.campprep-hero-title) [data-testid="stHeader"] button {{
      color: {palette.ON_DARK_MUTED};
      pointer-events: auto;
  }}
  /* Leaving the demo or signing out comes back here with the sidebar the
     inner pages drew still open and empty: the welcome page has none. */
  .stApp:has(.campprep-hero-title) [data-testid="stSidebar"],
  .stApp:has(.campprep-hero-title) [data-testid="stSidebarCollapsedControl"],
  .stApp:has(.campprep-hero-title) [data-testid="stExpandSidebarButton"] {{
      display: none;
  }}
  /* The top bar starts below Streamlit's header strip, where Community
     Cloud puts its Share and GitHub buttons. */
  .stMainBlockContainer:has(.campprep-hero-title) {{
      max-width: 1240px;
      padding-top: 4.25rem;
  }}
  /* Anchor jumps stop short of the header strip. */
  {_IN} :is(#account, #how-it-works, #who-its-for) {{ scroll-margin-top: 4.5rem; }}

  /* Top bar: the emblem and name, and anchors down the page. */
  {_IN} .cp-nav {{
      position: relative;
      z-index: 2;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
  }}
  {_IN} .cp-brand {{
      display: inline-flex;
      align-items: center;
      gap: 0.65rem;
      color: #FFFFFF;
      font-size: 1.05rem;
      font-weight: 800;
      letter-spacing: -0.01em;
  }}
  {_IN} .cp-brand img {{ width: 38px; height: 38px; }}
  {_IN} .cp-nav-links {{
      display: flex;
      align-items: center;
      gap: 1.7rem;
  }}
  {_IN} .cp-nav-links a {{
      color: {palette.ON_DARK_MUTED};
      font-size: 0.9rem;
      font-weight: 600;
      text-decoration: none;
      transition: color 150ms ease, border-color 150ms ease;
  }}
  {_IN} .cp-nav-links a:hover {{ color: #FFFFFF; }}
  {_IN} .cp-nav-links a.cp-nav-pill {{
      color: #FFFFFF;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 999px;
      padding: 0.45rem 1.05rem;
  }}
  {_IN} .cp-nav-links a.cp-nav-pill:hover {{ border-color: {palette.GREEN}; }}

  /* Hero: a faint grid fading out from the centre, and a green glow where
     the button sits. */
  {_IN} .cp-hero {{
      position: relative;
      isolation: isolate;
      text-align: center;
      padding: 5.5rem 0 0.4rem 0;
  }}
  {_IN} .cp-hero::before {{
      content: "";
      position: absolute;
      inset: -3rem 0 -9rem 0;
      z-index: -1;
      pointer-events: none;
      background-image:
          linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
      background-size: 64px 64px;
      -webkit-mask-image: radial-gradient(55% 60% at 50% 45%, #000 0%, transparent 75%);
      mask-image: radial-gradient(55% 60% at 50% 45%, #000 0%, transparent 75%);
  }}
  {_IN} .cp-hero::after {{
      content: "";
      position: absolute;
      left: 50%;
      bottom: -9rem;
      width: min(760px, 100%);
      height: 340px;
      transform: translateX(-50%);
      z-index: -1;
      pointer-events: none;
      background: radial-gradient(closest-side, rgba(118, 196, 87, 0.22), rgba(118, 196, 87, 0));
  }}
  {_IN} .campprep-hero-eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      color: {palette.ON_DARK};
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 999px;
      padding: 0.3rem 0.95rem 0.3rem 0.35rem;
      font-size: 0.8rem;
      font-weight: 650;
  }}
  {_IN} .campprep-hero-eyebrow b {{
      background: rgba(118, 196, 87, 0.16);
      color: {palette.GREEN};
      border-radius: 999px;
      padding: 0.08rem 0.6rem;
      font-size: 0.8rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
  }}
  /* Grey fading up into white, the way the reference's headline does. */
  {_IN} .campprep-hero-title {{
      font-size: clamp(2.5rem, 0.9rem + 5vw, 5.2rem);
      font-weight: 600;
      line-height: 1.02;
      letter-spacing: -0.055em;
      margin: 1.6rem auto 1.5rem auto;
      padding: 0;
      background: linear-gradient(180deg, #4F557F 0%, #B9BEE0 100%);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
  }}
  {_IN} .campprep-hero-title span {{
      display: block;
      padding-bottom: 0.06em;
      background: linear-gradient(180deg, #FFFFFF 35%, #C9CDEA 100%);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
  }}
  /* The glowing tick set into the second line. */
  {_IN} .campprep-hero-title i {{
      display: inline-grid;
      place-items: center;
      width: 0.82em;
      height: 0.82em;
      margin: 0 0.1em 0 0.06em;
      vertical-align: -0.08em;
      border-radius: 0.24em;
      background: radial-gradient(circle at 30% 25%, #9BE07D 0%, {palette.GREEN} 45%, #2F7A1B 100%);
      box-shadow: 0 0 0 1px rgba(155, 224, 125, 0.5),
                  0 0 34px rgba(118, 196, 87, 0.55);
  }}
  /* The tick is drawn in CSS: st.html strips inline SVG. */
  {_IN} .campprep-hero-title i::after {{
      content: "";
      width: 0.2em;
      height: 0.38em;
      margin-top: -0.08em;
      border: solid #0B1A05;
      border-width: 0 0.07em 0.07em 0;
      border-radius: 0.02em;
      transform: rotate(45deg);
  }}
  {_IN} .campprep-hero-lede {{
      font-size: 1.12rem;
      line-height: 1.65;
      color: {palette.ON_DARK_MUTED};
      max-width: 40rem;
      margin: 0 auto;
  }}

  /* The two calls to action, centred under the lede. */
  .st-key-landing_cta {{
      gap: 0.9rem;
      margin-top: 0.6rem;
  }}
  .stMainBlockContainer .st-key-landing_demo button[kind] {{
      background: {palette.SURFACE_DARK};
      color: #FFFFFF;
      border: 1px solid rgba(118, 196, 87, 0.75);
      border-radius: 12px;
      padding: 0.75rem 1.6rem;
      min-height: 3rem;
      box-shadow: 0 0 0 4px rgba(118, 196, 87, 0.08),
                  0 0 34px -4px rgba(118, 196, 87, 0.55);
  }}
  .stMainBlockContainer .st-key-landing_demo button[kind]:hover {{
      background: #101633;
      color: #FFFFFF;
      border-color: #9BE07D;
      box-shadow: 0 0 0 4px rgba(118, 196, 87, 0.12),
                  0 0 44px -2px rgba(118, 196, 87, 0.7);
  }}
  .stMainBlockContainer .st-key-landing_demo button[kind]:active:not(:disabled) {{
      transform: translateY(1px) !important;
      box-shadow: 0 0 22px -4px rgba(118, 196, 87, 0.55) !important;
  }}
  {_IN} .cp-ghost {{
      display: inline-flex;
      align-items: center;
      min-height: 3rem;
      padding: 0 1.4rem;
      border-radius: 12px;
      border: 1px solid rgba(255, 255, 255, 0.16);
      color: {palette.ON_DARK};
      font-size: 0.95rem;
      font-weight: 700;
      text-decoration: none;
      transition: border-color 150ms ease, color 150ms ease;
  }}
  {_IN} .cp-ghost:hover {{ border-color: rgba(255, 255, 255, 0.4); color: #FFFFFF; }}
  {_IN} .cp-proof {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 0.5rem 1.6rem;
      margin: 1.6rem 0 0 0;
      color: {palette.ON_DARK_MUTED};
      font-size: 0.86rem;
      font-weight: 600;
  }}
  {_IN} .cp-proof span {{ display: inline-flex; align-items: center; gap: 0.45rem; }}
  {_IN} .cp-proof b {{ font-weight: 800; }}

  /* Shared section headings. */
  {_IN} .cp-kicker {{
      display: block;
      font-size: 0.8rem;
      font-weight: 800;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: {palette.GREEN};
      margin: 0 0 0.9rem 0;
  }}
  {_IN} .cp-section-title {{
      font-size: clamp(2rem, 1.1rem + 2.8vw, 3.3rem);
      font-weight: 600;
      line-height: 1.05;
      letter-spacing: -0.045em;
      margin: 0 0 0.9rem 0;
      padding: 0;
      color: #FFFFFF;
  }}
  {_IN} .cp-section-title em {{ font-style: normal; color: {palette.GREEN}; }}
  {_IN} .cp-section-lede {{
      font-size: 1rem;
      line-height: 1.65;
      color: {palette.ON_DARK_MUTED};
      max-width: 34rem;
      margin: 0;
  }}

  /* "Choose your path": a white panel with big rounded corners holding the
     two dark cards, one per audience. */
  {_IN} .cp-panel {{
      background: {palette.SURFACE};
      border-radius: 40px;
      padding: 4.5rem clamp(1.1rem, 4vw, 3.5rem) 3.6rem clamp(1.1rem, 4vw, 3.5rem);
      margin: 7rem 0 0 0;
      text-align: center;
      box-shadow: 0 -30px 90px -50px rgba(118, 196, 87, 0.55);
  }}
  {_IN} .cp-panel .cp-section-title {{ color: {palette.INK}; }}
  {_IN} .cp-panel .cp-section-title em {{ color: {palette.GREEN_ON_LIGHT}; }}
  {_IN} .cp-panel .cp-section-lede {{ color: {palette.MUTED}; margin: 0 auto 2.6rem auto; }}
  {_IN} .cp-paths {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 1.2rem;
      text-align: left;
  }}
  {_IN} .cp-path {{
      display: flex;
      flex-direction: column;
      border-radius: 26px;
      padding: 2.1rem 2rem 2rem 2rem;
      color: {palette.ON_DARK};
      background:
          radial-gradient(90% 70% at 100% 0%, rgba(118, 196, 87, 0.2) 0%, rgba(118, 196, 87, 0) 60%),
          {palette.SURFACE_DARK};
  }}
  {_IN} .cp-path--teacher {{
      background:
          radial-gradient(90% 70% at 100% 0%, rgba(29, 206, 216, 0.18) 0%, rgba(29, 206, 216, 0) 60%),
          {palette.SURFACE_DARK};
  }}
  {_IN} .cp-path h3 {{
      color: #FFFFFF;
      font-size: 1.65rem;
      font-weight: 650;
      letter-spacing: -0.03em;
      margin: 0 0 0.5rem 0;
      padding: 0;
  }}
  {_IN} .cp-path p {{
      color: {palette.ON_DARK_MUTED};
      font-size: 0.95rem;
      line-height: 1.6;
      margin: 0 0 1.2rem 0;
  }}
  {_IN} .cp-path ul {{
      list-style: none;
      display: grid;
      gap: 0.6rem;
      margin: 0 0 1.8rem 0;
      padding: 0;
  }}
  {_IN} .cp-path li {{
      display: flex;
      gap: 0.6rem;
      margin: 0;
      font-size: 0.93rem;
      line-height: 1.5;
      color: {palette.ON_DARK};
  }}
  {_IN} .cp-path li::before {{ content: "✓"; color: {palette.GREEN}; font-weight: 800; }}
  {_IN} .cp-path--teacher li::before {{ color: {palette.CYAN}; }}
  {_IN} .cp-path small {{
      display: block;
      color: {palette.ON_DARK_MUTED};
      font-size: 0.8rem;
      line-height: 1.5;
      margin: -0.6rem 0 1.4rem 0;
  }}
  {_IN} .cp-path a {{
      align-self: flex-start;
      margin-top: auto;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      border-radius: 11px;
      padding: 0.72rem 1.25rem;
      font-size: 0.93rem;
      font-weight: 700;
      text-decoration: none;
      background: {palette.GREEN};
      color: #0B1A05;
      transition: filter 150ms ease, border-color 150ms ease;
  }}
  {_IN} .cp-path a:hover {{ filter: brightness(1.08); }}
  {_IN} .cp-path--teacher a {{
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.18);
      color: #FFFFFF;
  }}
  {_IN} .cp-path--teacher a:hover {{ border-color: {palette.CYAN}; filter: none; }}

  /* How it works: three statements beside a picture of the product. Where
     the browser supports scroll-driven animation, each statement brightens
     as it scrolls into view, as in the reference. */
  {_IN} .cp-how {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: clamp(2rem, 6vw, 5.5rem);
      align-items: center;
      padding: 7rem 0 1rem 0;
  }}
  {_IN} .campprep-steps {{ display: grid; gap: 2.1rem; margin-top: 2.4rem; }}
  {_IN} .campprep-step {{
      border-left: 2px solid rgba(255, 255, 255, 0.1);
      padding: 0.1rem 0 0.1rem 1.4rem;
  }}
  {_IN} .campprep-step b {{
      display: block;
      font-size: 0.8rem;
      font-weight: 800;
      letter-spacing: 0.1em;
      color: {palette.GREEN};
      margin-bottom: 0.35rem;
  }}
  {_IN} .campprep-step h2 {{
      margin: 0 0 0.3rem 0;
      padding: 0;
      font-size: 1.55rem;
      font-weight: 600;
      letter-spacing: -0.03em;
      color: #FFFFFF;
  }}
  {_IN} .campprep-step p {{
      margin: 0;
      font-size: 0.95rem;
      line-height: 1.6;
      color: {palette.ON_DARK_MUTED};
  }}
  @keyframes cp-step-in {{
      from {{ opacity: 0.25; border-left-color: rgba(255, 255, 255, 0.1); }}
      to {{ opacity: 1; border-left-color: {palette.GREEN}; }}
  }}
  @supports (animation-timeline: view()) {{
      @media (prefers-reduced-motion: no-preference) {{
          {_IN} .campprep-step {{
              animation: cp-step-in linear both;
              animation-timeline: view();
              animation-range: entry 30% cover 45%;
          }}
      }}
  }}
  /* The product picture: the topic breakdown a student gets back. */
  {_IN} .campprep-preview {{
      position: relative;
      background: {palette.SURFACE_DARK};
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 26px;
      padding: 1.6rem 1.6rem 1.5rem 1.6rem;
      box-shadow: 0 0 0 1px rgba(118, 196, 87, 0.06),
                  0 40px 100px -40px rgba(118, 196, 87, 0.45);
  }}
  {_IN} .campprep-preview-head {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin: 0 0 1.2rem 0;
  }}
  {_IN} .campprep-preview-head strong {{ font-size: 1rem; color: #FFFFFF; }}
  {_IN} .campprep-preview-head span {{
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: {palette.ON_DARK_MUTED};
  }}
  {_IN} .campprep-bar {{ margin: 0 0 1rem 0; }}
  {_IN} .campprep-bar-label {{
      display: flex;
      justify-content: space-between;
      font-size: 0.85rem;
      font-weight: 650;
      color: {palette.ON_DARK};
      margin-bottom: 0.4rem;
  }}
  {_IN} .campprep-bar-track {{
      height: 10px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.07);
      overflow: hidden;
  }}
  {_IN} .campprep-bar-track i {{ display: block; height: 100%; border-radius: 999px; }}
  {_IN} .campprep-preview-foot {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 1.3rem;
      padding-top: 1.2rem;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
  }}
  {_IN} .campprep-preview-foot span {{
      border-radius: 999px;
      padding: 0.3rem 0.75rem;
      font-size: 0.8rem;
      font-weight: 700;
  }}

  /* Account: a heading on the dark canvas beside a white card that holds
     the sign-in forms. */
  {_IN} .cp-account-copy {{ padding: 1rem 0; }}
  {_IN} .cp-account-copy .cp-section-lede {{ margin-bottom: 1.2rem; }}
  .stMainBlockContainer .st-key-landing_account[data-testid] {{
      background: {palette.SURFACE};
      color: {palette.INK};
      border: none;
      border-radius: 26px;
      padding: 1.4rem;
      box-shadow: 0 40px 100px -50px rgba(118, 196, 87, 0.5);
  }}
  /* A keyed container carries the same scroll attributes as a bordered
     one, so it would pick up the white card surface too. */
  .stMainBlockContainer .st-key-landing_account_row[data-testid] {{
      background: transparent;
      box-shadow: none;
      margin-top: 6rem;
  }}
  {_IN} .campprep-panel-head {{
      position: relative;
      overflow: hidden;
      background: {_BANNER};
      border-radius: 16px;
      padding: 1.2rem 1.3rem 1.35rem 1.3rem;
      margin: 0 0 0.6rem 0;
      color: #FFFFFF;
  }}
  {_IN} .campprep-panel-head h2 {{
      color: #FFFFFF;
      margin: 0 0 0.15rem 0;
      padding: 0;
      font-size: 1.3rem;
      font-weight: 800;
  }}
  {_IN} .campprep-panel-head p {{
      margin: 0;
      color: rgba(233, 236, 255, 0.85);
      font-size: 0.88rem;
  }}
  /* Welcome-page stand-ins for st.info / st.divider / st.caption, drawn
     with st.html so the whole page paints in one go (BUG-023). */
  {_IN} .campprep-notice {{
      border-radius: 1rem;
      padding: 1rem;
      font-size: 0.95rem;
      line-height: 1.5;
      margin: 0 0 0.5rem 0;
  }}
  {_IN} .campprep-rule {{
      border: none;
      border-top: 1px solid {palette.BORDER};
      margin: 1.5rem 0 1rem 0;
  }}
  {_IN} .campprep-small {{
      color: {palette.MUTED};
      font-size: 0.82rem;
      line-height: 1.5;
      margin: 0 0 0.6rem 0;
  }}

  /* Footer. */
  {_IN} .cp-footer {{
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      justify-content: space-between;
      gap: 1rem 3rem;
      margin-top: 5rem;
      padding-top: 2rem;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
  }}
  {_IN} .cp-footer p {{
      max-width: 40rem;
      margin: 0;
      color: {palette.ON_DARK_MUTED};
      font-size: 0.8rem;
      line-height: 1.6;
  }}

  @media (max-width: {_WRAP_BREAKPOINT}) {{
      {_IN} .cp-how {{ grid-template-columns: 1fr; padding-top: 5rem; }}
  }}
  @media (max-width: {_STACK_BREAKPOINT}) {{
      {_IN} .cp-nav-links a:not(.cp-nav-pill) {{ display: none; }}
      {_IN} .cp-hero {{ padding-top: 3.2rem; }}
      {_IN} .campprep-hero-lede {{ font-size: 1rem; }}
      {_IN} .cp-panel {{ border-radius: 28px; margin-top: 5rem; padding-top: 3rem; }}
      {_IN} .cp-paths {{ grid-template-columns: 1fr; }}
      {_IN} .cp-path {{ padding: 1.6rem 1.3rem; }}
      {_IN} .campprep-step h2 {{ font-size: 1.3rem; }}
      .st-key-landing_cta {{ flex-direction: column; align-items: stretch; }}
      {_IN} .cp-ghost {{ justify-content: center; width: 100%; }}
      .stMainBlockContainer .st-key-landing_account_row[data-testid] {{ margin-top: 4rem; }}
      .stMainBlockContainer .st-key-landing_account[data-testid] {{ padding: 1rem; }}
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
          padding-top: 4.1rem;
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
      [data-testid="stTabs"] [role="tablist"] {{ width: 100%; }}
      [data-testid="stMetric"] {{ padding: 0.8rem 0.9rem 0.85rem 0.9rem; }}
      {_IN} .campprep-header {{ padding: 1.3rem 1.2rem 1.7rem 1.2rem; border-radius: 20px; }}
      {_IN} .campprep-header::after {{ display: none; }}
      {_IN} .campprep-subtitle {{ font-size: 0.9rem; }}
  }}

  /* Sidebar copy inherits Streamlit's muted/disabled styles in a few states.
     Pin a readable foreground and a 12px floor across labels and captions. */
  [data-testid="stSidebar"] {{ color: #E9ECFF; }}
  [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] [data-testid="stWidgetLabel"] {{
      color: #E9ECFF !important;
      font-size: max(12px, 0.8rem) !important;
  }}
  /* Alerts carry their own dark-on-tint text (the Demo Mode badge is dark
     amber on pale yellow); the light sidebar colour above would erase it. */
  [data-testid="stSidebar"] [data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"] {{
      color: inherit !important;
  }}
  [data-testid="stSidebar"] a {{ color: #E9ECFF !important; }}
  [data-testid="stSidebar"] a[aria-current="page"] {{ color: #1DCED8 !important; }}

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

    `st.html` rather than `st.markdown`: a style-only st.html block takes no
    space in the layout, and it arrives together with the welcome page's own
    st.html content instead of after it (BUG-023, welcome page CLS 0.54).
    """
    st.html(_STYLES)


def page_header(
    title: str,
    subtitle: str = "",
    help_text: str = "",
    eyebrow: Optional[str] = None,
) -> None:
    """Standard page banner used by every page.

    The eyebrow is the small capitalised label above the title, and it says
    where in the workflow this page sits. Left alone it is read off the
    navigation, so a page and the menu item that leads to it can never
    disagree; pass a string to override it, or "" to leave it off.
    """
    inject_styles()
    if eyebrow is None:
        eyebrow = _section_for(title)
    parts = ['<div class="campprep-header">']
    if eyebrow:
        parts.append(f'<span class="campprep-eyebrow">{escape(eyebrow)}</span>')
    # A real <h1>: one per page, for screen readers and document outline.
    parts.append(f'<h1 class="campprep-title">{escape(title)}</h1>')
    if subtitle:
        parts.append(f'<p class="campprep-subtitle">{escape(subtitle)}</p>')
    parts.append('<span class="campprep-stripe"></span></div>')
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
    """Who you are, the demo controls and the Feedback button.

    Kept short on purpose. The menu above already links Privacy, so the long
    notice and its second link are gone from here, and so are the emblem and
    the About blurb: the rail is for getting around, not for reading.
    """
    from components.feedback import feedback_dialog

    status = store.backend_status()
    with st.sidebar:
        # User-facing copy only. The backend message is setup advice for
        # whoever deploys the app (env vars, pip), so it stays out of the UI.
        if status["is_error"]:
            st.error(
                "We couldn't reach the account service, so you are in demo "
                "mode - sample data, nothing is saved.",
                icon=":material/error:",
            )

        _identity_switcher(status["demo_mode"])

        if st.button(
            "Give feedback",
            icon=":material/rate_review:",
            width="stretch",
            key="sidebar_feedback",
        ):
            feedback_dialog()


def _identity_switcher(demo_mode: bool) -> None:
    """Who is using the app. In the demo, a switch between sample people -
    not authentication.

    Hidden entirely once somebody is really signed in: the role then comes from
    their profile row, and offering a control that appears to change it would be
    a lie about what the app can do.
    """
    from services import auth_service

    signed_in = auth_service.current_user()
    if signed_in is not None:
        avatar = (
            f'<img src="{escape(signed_in.avatar_url, quote=True)}" alt="">'
            if signed_in.avatar_url
            else f"<i>{escape(signed_in.display_name[:1].upper())}</i>"
        )
        st.html(
            f'<div class="cp-side-who">{avatar}<div><b>{escape(signed_in.display_name)}</b>'
            f"<span>{escape(signed_in.role.label)} · work saved to your account</span>"
            "</div></div>"
        )
        if st.button("Sign out", icon=":material/logout:", width="stretch"):
            auth_service.sign_out()
            store.leave_demo()
            st.rerun()
        return

    if demo_mode:
        st.html(
            '<p class="cp-side-pill"><b></b>Demo · sample data, not saved</p>'
        )

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
        "Viewing as",
        options=[u.id for u in ordered],
        format_func=lambda uid: labels[uid],
        index=index,
        help="Switch between the sample student and teacher. This is not a login.",
    )
    if current is None or chosen != current.id:
        store.set_current_user(chosen)
        st.rerun()

    with st.container(horizontal=True, key="sidebar_demo_actions"):
        if st.button(
            "Welcome page",
            icon=":material/arrow_back:",
            width="stretch",
            help="Leave the demo and go back to the welcome page.",
        ):
            store.leave_demo()
            st.rerun()
        # Only meaningful while the sample data IS the data. Offering it to a
        # signed-in user would imply it resets their saved work, which it does
        # not touch.
        if demo_mode and st.button(
            "Reset",
            icon=":material/restart_alt:",
            width="stretch",
            help="Restore the sample data.",
        ):
            store.reset_to_samples()
            st.rerun()


def ai_disclaimer(extra: str = "") -> None:
    st.info(f"{AI_DISCLAIMER} {extra}".strip(), icon=":material/gavel:")


def privacy_notice() -> None:
    st.caption(f":material/lock: {PRIVACY_NOTICE}")
    # The active timed paper deliberately registers only itself in Streamlit's
    # hidden navigation. A second page link would be rejected by that router.
    from services.state import get_mock_exam

    exam = get_mock_exam()
    if exam is None or exam.is_submitted:
        _privacy_page_link("Read the full privacy details")


def _privacy_page_link(label: str, icon: str | None = None) -> None:
    """Use Streamlit's in-app navigation, with a direct-page test fallback.

    The application registers Privacy in `app.py`. A few focused page tests run
    an individual script without that navigation registry, where `page_link`
    raises instead of rendering. The fallback is still a same-app URL.
    """
    from streamlit.errors import StreamlitPageNotFoundError

    try:
        st.page_link("pages/privacy.py", label=label, icon=icon)
    except StreamlitPageNotFoundError:
        st.markdown(f"[{escape(label)}](/privacy)")


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
    st.markdown(f'<div class="campprep-badges">{html}</div>', unsafe_allow_html=True)


def info_card_html(title: str, body: str, icon: str = "", tone: str = "primary") -> str:
    """The markup behind `info_card`, for pages that draw several in one block."""
    tile = ""
    if icon:
        background, colour = _TONES.get(tone, _TONES["primary"])
        tile = (
            f'<span class="campprep-card-icon" '
            f'style="background:{background};color:{colour};">{escape(icon)}</span>'
        )
    return (
        f'<div class="campprep-card">{tile}<div><h2>{escape(title)}</h2>'
        f'<p>{escape(body)}</p></div></div>'
    )


def info_card(title: str, body: str, icon: str = "", tone: str = "primary") -> None:
    """A white card with an optional coloured icon tile beside the text.

    `icon` is a short glyph (an emoji or a character or two); `tone` picks the
    tile colour from the palette roles - primary, hint, correct, warning or
    incorrect.
    """
    # st.html, not markdown: raw-HTML markdown waits for a lazily loaded plugin
    # and then pushes already-drawn content down (BUG-023).
    st.html(info_card_html(title, body, icon, tone))


def hint_note(text: str) -> None:
    """A hint heading, in the hint colour.

    Hints get their own colour so a student can tell at a glance that what
    follows is a nudge, not a verdict on their answer.
    """
    st.markdown(f'<div class="campprep-hint">{escape(text)}</div>', unsafe_allow_html=True)


def empty_state(message: str, hint: str = "", icon: str = ":material/info:") -> None:
    """A consistent, friendly empty state instead of a blank page."""
    st.info(message, icon=icon)
    if hint:
        st.caption(hint)
