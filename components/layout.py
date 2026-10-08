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
from utils.config import AI_DISCLAIMER, APP_TAGLINE, PRIVACY_NOTICE

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
  .stMainBlockContainer {{
      max-width: 1180px;
      padding-top: 2.2rem;
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
      font-size: 0.7rem;
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
      font-size: 0.78rem;
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
      font-size: 0.78rem;
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
      font-size: 0.72rem;
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
  /* st.logo tops out at 32px, too small for the emblem's detail. The name is
     left off here on purpose, so the emblem can take the room instead. */
  {_SIDEBAR} [data-testid="stSidebarHeader"] {{ height: auto; padding-top: 1.1rem; }}
  {_SIDEBAR} [data-testid="stSidebarLogo"] {{
      height: 4.5rem;
      width: auto;
      max-width: none;
      filter: drop-shadow(0 4px 10px rgba(4, 8, 48, 0.45));
  }}
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
      font-size: 0.68rem !important;
      font-weight: 700 !important;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #E9ECFF !important;
  }}
  [data-testid="stSidebarNavSeparator"] {{ border-color: rgba(255, 255, 255, 0.1); }}
  [data-testid="stSidebarUserContent"] {{ padding-top: 0.75rem; }}
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
  {_IN} .campprep-brand {{
      font-size: 0.68rem;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #E9ECFF;
      margin: 0 0 0.2rem 0;
  }}

  /* --- Landing page ---------------------------------------------------- */
  {_IN} .campprep-hero-eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      color: {palette.PRIMARY};
      background: {palette.SURFACE};
      border: 1px solid {palette.BORDER};
      box-shadow: var(--cp-shadow);
      border-radius: 999px;
      padding: 0.25rem 0.85rem 0.25rem 0.35rem;
      font-size: 0.78rem;
      font-weight: 700;
  }}
  {_IN} .campprep-hero-eyebrow b {{
      background: {palette.TINT_CORRECT[0]};
      color: {palette.TINT_CORRECT[1]};
      border-radius: 999px;
      padding: 0.05rem 0.55rem;
      font-size: 0.68rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
  }}
  {_IN} .campprep-hero-title {{
      font-size: clamp(2.2rem, 1.4rem + 3vw, 3.6rem);
      font-weight: 800;
      line-height: 1.02;
      letter-spacing: -0.045em;
      color: {palette.INK};
      margin: 1.1rem 0 1rem 0;
      padding: 0;
  }}
  {_IN} .campprep-hero-title span {{
      background: linear-gradient(95deg, {palette.PRIMARY} 10%, {palette.TINT_HINT[1]} 95%);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
  }}
  /* An orange marker swipe under one word. */
  {_IN} .campprep-hero-title em {{
      font-style: normal;
      white-space: nowrap;
      background: linear-gradient(180deg, transparent 64%,
                  rgba(255, 145, 0, 0.55) 64%, rgba(255, 145, 0, 0.55) 88%,
                  transparent 88%);
  }}
  {_IN} .campprep-hero-lede {{
      font-size: 1.08rem;
      line-height: 1.65;
      color: {palette.MUTED};
      max-width: 34rem;
      margin: 0 0 1.3rem 0;
  }}
  {_IN} .campprep-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin: 0 0 1.6rem 0;
  }}
  {_IN} .campprep-chip {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: {palette.SURFACE};
      border: 1px solid {palette.BORDER};
      border-radius: 999px;
      padding: 0.3rem 0.8rem 0.3rem 0.4rem;
      font-size: 0.82rem;
      font-weight: 650;
      color: {palette.INK};
  }}
  {_IN} .campprep-chip i {{
      display: grid;
      place-items: center;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      font-style: normal;
      font-size: 0.7rem;
      font-weight: 800;
      color: #FFFFFF;
  }}
  {_IN} .campprep-steps {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.8rem;
      margin: 0.4rem 0 1.2rem 0;
  }}
  {_IN} .campprep-step {{
      background: {palette.SURFACE};
      border: 1px solid {palette.BORDER};
      border-radius: var(--cp-radius);
      padding: 1rem 1rem 1.05rem 1rem;
      box-shadow: var(--cp-shadow);
  }}
  {_IN} .campprep-step b {{
      display: grid;
      place-items: center;
      width: 30px;
      height: 30px;
      border-radius: 10px;
      color: #FFFFFF;
      font-weight: 800;
      margin-bottom: 0.6rem;
  }}
  {_IN} .campprep-step h2 {{
      margin: 0 0 0.2rem 0;
      padding: 0;
      font-size: 0.95rem;
      font-weight: 750;
      color: {palette.INK};
  }}
  {_IN} .campprep-step p {{
      margin: 0;
      font-size: 0.84rem;
      line-height: 1.5;
      color: {palette.MUTED};
  }}
  /* The welcome panel above the sign-in forms. */
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
  {_IN} .campprep-foot {{ margin-top: 1.5rem; }}
  {_IN} .campprep-card-pair {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
      margin-top: 1rem;
  }}
  @media (max-width: {_STACK_BREAKPOINT}) {{
      {_IN} .campprep-card-pair {{ grid-template-columns: 1fr; }}
  }}
  /* The welcome page keeps Streamlit's own page geometry (top padding, full
     wide width). Everything on it is drawn before this stylesheet arrives, so
     a different padding or max-width made the whole page jump once it did. */
  .stMainBlockContainer:has(.campprep-hero-title) {{
      max-width: none;
      padding-top: 6rem;
  }}
  /* A small, static "what you get" card under the sign-in panel. */
  {_IN} .campprep-preview {{
      background: {palette.SURFACE};
      border: 1px solid {palette.BORDER};
      border-radius: 22px;
      padding: 1.1rem 1.2rem 1.2rem 1.2rem;
      margin-top: 0.4rem;
      box-shadow: var(--cp-shadow-lift);
      position: relative;
      overflow: hidden;
  }}
  {_IN} .campprep-preview::before {{
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      top: 0;
      height: 5px;
      background: var(--cp-stripe);
  }}
  {_IN} .campprep-preview-head {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin: 0.2rem 0 0.8rem 0;
  }}
  {_IN} .campprep-preview-head strong {{ font-size: 0.95rem; color: {palette.INK}; }}
  {_IN} .campprep-preview-head span {{ font-size: 0.75rem; color: {palette.MUTED}; font-weight: 600; }}
  {_IN} .campprep-bar {{ margin: 0 0 0.7rem 0; }}
  {_IN} .campprep-bar-label {{
      display: flex;
      justify-content: space-between;
      font-size: 0.8rem;
      font-weight: 650;
      color: {palette.INK};
      margin-bottom: 0.3rem;
  }}
  {_IN} .campprep-bar-track {{
      height: 10px;
      border-radius: 999px;
      background: {palette.SURFACE_ALT};
      overflow: hidden;
  }}
  {_IN} .campprep-bar-track i {{ display: block; height: 100%; border-radius: 999px; }}
  {_IN} .campprep-preview-foot {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      margin-top: 0.9rem;
  }}
  {_IN} .campprep-logo {{ margin: 0 0 1.6rem 0; }}
  {_IN} .campprep-logo img {{ height: 80px; width: auto; max-width: 100%; }}

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
      /* On a phone, put the sign-in/demo action first. The hero remains below
         it, so the account form is reachable without scrolling past the tour. */
      .stMainBlockContainer:has(.campprep-hero-title)
      [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {{
          order: 2;
      }}
      .stMainBlockContainer:has(.campprep-hero-title)
      [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:nth-child(2) {{
          order: 1;
      }}
      .stMainBlockContainer:has(.campprep-hero-title) .campprep-steps,
      .stMainBlockContainer:has(.campprep-hero-title) .campprep-card-pair {{
          display: none;
      }}
      .stMainBlockContainer {{
          padding-top: 1.2rem;
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
      {_IN} .campprep-steps {{ grid-template-columns: 1fr; }}
      {_IN} .campprep-step h2 {{ font-size: 1rem; }}
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
    """Backend status, the demo identity switch and the privacy notice."""
    status = store.backend_status()
    with st.sidebar:
        # The emblem is drawn above the navigation by `st.logo` in app.py, so
        # all this block owes the reader is what the app is for and whether it
        # is talking to a real backend.
        st.markdown('<p class="campprep-brand">About</p>', unsafe_allow_html=True)
        st.caption(APP_TAGLINE)

        if status["demo_mode"]:
            st.warning("Demo Mode", icon=":material/science:")
        else:
            st.success("Connected to Supabase", icon=":material/cloud_done:")

        # User-facing copy only. The backend message is setup advice for
        # whoever deploys the app (env vars, pip), so it stays out of the UI.
        if status["is_error"]:
            st.error(
                "We couldn't reach the account service, so you are in demo "
                "mode - sample data, nothing is saved.",
                icon=":material/error:",
            )
        elif status["demo_mode"]:
            st.caption("Demo mode — sample data, nothing is saved.")
        else:
            st.caption("Your work is saved to your account.")

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
        _privacy_page_link("Privacy details", icon=":material/lock:")


def _identity_switcher() -> None:
    """Pick who you are signed in as. Demo only - not authentication.

    Hidden entirely once somebody is really signed in: the role then comes from
    their profile row, and offering a control that appears to change it would be
    a lie about what the app can do.
    """
    from services import auth_service

    signed_in = auth_service.current_user()
    if signed_in is not None:
        if signed_in.avatar_url:
            st.image(signed_in.avatar_url, width=56)
        st.markdown(f"**{signed_in.display_name}**")
        st.caption(f"{signed_in.role.label} · signed in")
        if st.button("Sign out", width="stretch"):
            auth_service.sign_out()
            store.leave_demo()
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
    if st.button("Back to welcome page", width="stretch"):
        store.leave_demo()
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


def _privacy_page_link(label: str, icon: str = "") -> None:
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
