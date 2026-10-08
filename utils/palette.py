"""The app's colour palette.

The six hex values below are the ones Aryaman picked from Coolors in the
9 Sep session. Three of them were given a job in that call and the rest are
assigned here; every colour the UI draws should come from this module rather
than being written inline, so a palette change is a one-file change.

Roles agreed in the session:
    hints      -> blue
    correct    -> #76C457
    incorrect  -> #DF301C

The redesign keeps the six colours and builds everything else - neutrals,
tints, the sidebar and the banner gradient - out of the two blues, so even
the greys lean indigo and nothing on screen looks borrowed from another app.
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

PALETTE = (BLUE_DEEP, CYAN, BLUE_INDIGO, ORANGE, GREEN, RED)

# --- What each one is for --------------------------------------------------
PRIMARY = BLUE_DEEP        # buttons, links, the active nav item
PRIMARY_DARK = BLUE_INDIGO # headings, hover and pressed states
HINT = CYAN                # guidance and hints - never an answer
CORRECT = GREEN
INCORRECT = RED
WARNING = ORANGE           # attempts running out, awaiting review

# The "lip" under a chunky button: the same hue, a step darker, so a press
# reads as the button sinking into it.
PRIMARY_LIP = "#121D8A"
NIGHT = "#0B1260"          # the darkest stop of the sidebar and banner

# --- Neutrals (indigo-tinted) ----------------------------------------------
INK = "#0E1340"
MUTED = "#555C85"
BORDER = "#E2E5F5"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F1F3FC"
CANVAS = "#F6F7FE"

# --- Badge pairs: (background tint, readable text colour) ------------------
# Tints are the palette colour lightened; the text colour is the same hue
# darkened enough to clear WCAG AA on that tint.
TINT_PRIMARY: Tuple[str, str] = ("#E6E9FC", "#1B2CC1")
TINT_HINT: Tuple[str, str] = ("#DDF7F9", "#086A71")
TINT_CORRECT: Tuple[str, str] = ("#E8F6E1", "#35711E")
TINT_INCORRECT: Tuple[str, str] = ("#FDE5E1", "#962010")
TINT_WARNING: Tuple[str, str] = ("#FFF0DB", "#8A4E00")
TINT_NEUTRAL: Tuple[str, str] = (SURFACE_ALT, "#3A4170")

# --- Charts ----------------------------------------------------------------
# Categorical series colours, in the order Plotly hands them out. The two
# colours that carry a meaning elsewhere - green and red - come last, so a
# chart with only a few series never accidentally implies correct/incorrect.
CHART_SEQUENCE = [PRIMARY, HINT, "#007C91", WARNING, CORRECT, INCORRECT]

# Strength bands, using the same green-to-red reading as marking.
BAND_COLOURS = {
    "Secure": CORRECT,
    "Developing": PRIMARY,
    "Needs work": WARNING,
    "Priority": INCORRECT,
}
