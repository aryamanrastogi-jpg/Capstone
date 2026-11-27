"""One look for every chart in the app.

Each page builds its own figure - a bar, a line, a before/after pair - and then
hands it to `render` here. Everything that is a *presentation* decision lives in
this file: type, gridlines, margins, the hover card, whether the Plotly toolbar
shows. A page never sets those itself, so no two charts can drift apart.

The responsive part is `automargin`. Fixed margins are what clip an axis title
to "core (%)" once the container narrows, because the label needs more room
than the margin allows; letting Plotly measure the label instead means the
chart gives it exactly the space it needs at whatever width it ends up.
"""

from __future__ import annotations

import textwrap
from typing import List, Optional, Sequence

import streamlit as st

from utils import palette

# The same stack as `.streamlit/config.toml`, so chart text and page text are
# set in one typeface rather than two.
_FONT = "Plus Jakarta Sans, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"

_GRID = palette.BORDER

# The modebar is a desktop affordance that overlaps the plot on a narrow
# screen, and nothing in this app asks a student to export a PNG of a chart.
_CONFIG = {"displayModeBar": False, "responsive": True}


def short_labels(texts: Sequence[str], limit: int = 26) -> List[str]:
    """Axis labels that fit a phone: each text cut at a word to `limit` characters.

    A bar chart of questions puts the whole question beside every bar, and on a
    390px screen Plotly then slides the labels off the left edge (BUG-015). The
    full text belongs in the hover card (see `wrap_for_hover`). Texts that would
    end up with the same label get a number, because Plotly merges bars whose
    category is the same.
    """
    labels: List[str] = []
    seen: dict = {}
    for text in texts:
        clean = " ".join(str(text).split())
        if len(clean) > limit:
            cut = clean[: limit - 1]
            if " " in cut and clean[limit - 1] != " ":
                cut = cut.rsplit(" ", 1)[0]
            clean = cut.rstrip(" ,;:-") + "…"
        seen[clean] = seen.get(clean, 0) + 1
        labels.append(clean if seen[clean] == 1 else f"{clean} ({seen[clean]})")
    return labels


def wrap_for_hover(text: str, width: int = 44) -> str:
    """A long text as lines for a Plotly hover card, which never wraps by itself."""
    return "<br>".join(textwrap.wrap(" ".join(str(text).split()), width)) or str(text)


def style(figure, height: Optional[int] = None, legend: bool = True):
    """Apply the shared chart styling to a Plotly figure, in place."""
    figure.update_layout(
        font=dict(family=_FONT, size=12, color=palette.INK),
        margin=dict(l=8, r=8, t=10, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(
            bgcolor=palette.SURFACE,
            bordercolor=palette.BORDER,
            font=dict(family=_FONT, size=12, color=palette.INK),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            title_text="",
            font=dict(size=11),
        ),
        showlegend=legend,
        # Rounded bar ends, to match the soft corners everywhere else.
        barcornerradius=6,
        bargap=0.28,
    )
    if height is not None:
        figure.update_layout(height=height)

    axis = dict(
        automargin=True,
        gridcolor=_GRID,
        zerolinecolor=_GRID,
        linecolor=_GRID,
        title_font=dict(size=12, color=palette.MUTED),
        tickfont=dict(size=11, color=palette.MUTED),
    )
    figure.update_xaxes(**axis)
    figure.update_yaxes(**axis)
    return figure


def render(figure, height: Optional[int] = None, legend: bool = True) -> None:
    """Style a figure and draw it at the full width of its container."""
    st.plotly_chart(
        style(figure, height=height, legend=legend),
        width="stretch",
        config=_CONFIG,
    )
