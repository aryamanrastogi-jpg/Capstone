"""The app's colour palette.

The six hex values below are the ones Aryaman picked from Coolors in the
9 Sep session. Three of them were given a job in that call and the rest are
assigned here; every colour the UI draws should come from this module rather
than being written inline, so a palette change is a one-file change.

Roles agreed in the session:
    hints      -> blue
    correct    -> #76C457
    incorrect  -> #DF301C
"""

from __future__ import annotations

from typing import Tuple

# --- The six picked colours ------------------------------------------------
BLUE_DEEP = "#1B2CC1"
BLUE_INDIGO = "#2F39A9"
CYAN = "#1DCED8"
GREEN = "#76C457"
RED = "#DF301C"
ORANGE = "#FF9100"

# --- What each one is for --------------------------------------------------
PRIMARY = BLUE_DEEP        # buttons, links, the active nav item
PRIMARY_DARK = BLUE_INDIGO # headings, hover and pressed states
HINT = CYAN                # guidance and hints - never an answer
CORRECT = GREEN
INCORRECT = RED
WARNING = ORANGE           # attempts running out, awaiting review

# --- Neutrals --------------------------------------------------------------
INK = "#0F172A"
MUTED = "#475569"
BORDER = "#E2E8F0"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F1F5F9"

# --- Badge pairs: (background tint, readable text colour) ------------------
# Tints are the palette colour lightened; the text colour is the same hue
# darkened enough to clear WCAG AA on that tint.
TINT_PRIMARY: Tuple[str, str] = ("#E5E7F9", "#1B2CC1")
TINT_HINT: Tuple[str, str] = ("#E0F7F9", "#0B6F76")
TINT_CORRECT: Tuple[str, str] = ("#EAF6E3", "#3B7A22")
TINT_INCORRECT: Tuple[str, str] = ("#FCE6E3", "#96200F")
TINT_WARNING: Tuple[str, str] = ("#FFF1DE", "#8A4E00")
TINT_NEUTRAL: Tuple[str, str] = (SURFACE_ALT, "#334155")

# --- Charts ----------------------------------------------------------------
# Categorical series colours, in the order Plotly hands them out. The two
# colours that carry a meaning elsewhere - green and red - come last, so a
# chart with only a few series never accidentally implies correct/incorrect.
CHART_SEQUENCE = [PRIMARY, HINT, PRIMARY_DARK, WARNING, CORRECT, INCORRECT]

# Strength bands, using the same green-to-red reading as marking.
BAND_COLOURS = {
    "Secure": CORRECT,
    "Developing": PRIMARY,
    "Needs work": WARNING,
    "Priority": INCORRECT,
}
