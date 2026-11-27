"""The welcome page's styles: contrast, type scale, focus ring and the phone layout.

These read the one style block in components/layout.py, because the problems
they guard against live in that CSS and a unit test is the cheapest place to
keep them from coming back:

  * ARY-004 / BUG-004: the green kicker on the white panel was 2.14:1.
  * ARY-006 / BUG-006: the welcome page used 17 font sizes.
  * ARY-007 / BUG-007: Practice Generator used the sparkle icon.
  * BUG-012: the main "Explore the demo" button showed no focus ring.
  * BUG-014: the same button sat at the left edge on phones.

The real page is measured separately in a browser (computed styles); these
are the guards.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

import pytest

from components import layout
from components.navigation import PAGE_SPECS
from utils import palette

Rule = Tuple[Tuple[str, ...], str, Dict[str, str]]


# --------------------------------------------------------------------------
# A small CSS reader: enough for this one style block (rules, @media, @supports)
# --------------------------------------------------------------------------
def _declarations(body: str) -> Dict[str, str]:
    declarations: Dict[str, str] = {}
    depth, quote, start = 0, "", 0
    parts: List[str] = []
    for index, char in enumerate(body):
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == ";" and depth == 0:
            parts.append(body[start:index])
            start = index + 1
    parts.append(body[start:])
    for part in parts:
        name, sep, value = part.partition(":")
        if sep and name.strip():
            declarations[name.strip()] = " ".join(value.split())
    return declarations


def _parse(css: str, context: Tuple[str, ...] = ()) -> List[Rule]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = css.replace("<style>", "").replace("</style>", "")
    rules: List[Rule] = []
    position = 0
    while True:
        opening = css.find("{", position)
        if opening == -1:
            return rules
        selector = " ".join(css[position:opening].split())
        depth, closing = 1, opening + 1
        while depth and closing < len(css):
            depth += {"{": 1, "}": -1}.get(css[closing], 0)
            closing += 1
        body = css[opening + 1 : closing - 1]
        if selector.startswith(("@media", "@supports")):
            rules.extend(_parse(body, context + (selector,)))
        elif not selector.startswith("@"):
            rules.append((context, selector, _declarations(body)))
        position = closing


def _welcome_css() -> str:
    start = layout._STYLES.index("/* --- Landing page")
    end = layout._STYLES.index("/* --- Responsive")
    return layout._STYLES[start:end]


def _luminance(colour: str) -> float:
    colour = colour.lstrip("#")
    channels = [int(colour[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


# --------------------------------------------------------------------------
# ARY-004: the kicker on the white panel
# --------------------------------------------------------------------------
def test_the_kicker_on_the_white_panel_is_readable() -> None:
    rules = [
        rule for rule in _parse(_welcome_css()) if rule[1].endswith(".cp-panel .cp-kicker")
    ]
    assert rules, "the kicker on the white panel still uses the dark-canvas green"
    colour = rules[0][2]["color"]
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", colour), colour
    assert _contrast(colour, palette.SURFACE) >= 4.5


def test_the_green_kicker_stays_on_the_dark_canvas_only() -> None:
    """palette.GREEN is 2.14:1 on white, so the base rule must be for the dark page."""
    base = [r for r in _parse(_welcome_css()) if r[1].endswith(".cp-kicker")]
    assert base and base[0][2]["color"] == palette.GREEN
    assert _contrast(palette.GREEN, palette.NIGHT_DEEP) >= 4.5


# --------------------------------------------------------------------------
# ARY-006: one type scale for the welcome page
# --------------------------------------------------------------------------
def _scale() -> Dict[str, str]:
    [root] = [
        decls
        for context, selector, decls in _parse(layout._STYLES)
        if selector == ":root" and not context
    ]
    return {k: v for k, v in root.items() if k.startswith("--cp-fs-")}


def test_every_welcome_font_size_comes_from_the_scale() -> None:
    sizes = [
        declarations["font-size"]
        for _, _, declarations in _parse(_welcome_css())
        if "font-size" in declarations
    ]
    assert sizes, "the welcome page styles set no font sizes at all"
    loose = [size for size in sizes if not re.fullmatch(r"var\(--cp-fs-[a-z]+\)", size)]
    assert loose == [], f"sizes written inline instead of from the scale: {loose}"


def test_the_scale_has_no_more_than_six_sizes() -> None:
    scale = _scale()
    assert 2 <= len(scale) <= 6, scale
    used = {
        re.search(r"--cp-fs-[a-z]+", declarations["font-size"]).group(0)
        for _, _, declarations in _parse(_welcome_css())
        if "font-size" in declarations
    }
    assert used <= set(scale), f"used but not defined: {used - set(scale)}"
    assert len(set(scale.values())) == len(scale), "two tokens share one size"


def test_the_scale_keeps_the_label_floor_and_the_body_size() -> None:
    """12px is the smallest legible label (the app's floor); 1rem is the body size."""
    scale = _scale()
    assert scale["--cp-fs-xs"] == "0.8rem"
    assert scale["--cp-fs-md"] == "1rem"


# --------------------------------------------------------------------------
# ARY-007: no sparkle icon
# --------------------------------------------------------------------------
SPARKLES = ("auto_awesome", "auto_fix", "magic", "stars", "sparkle", "wand")


def test_no_menu_entry_uses_a_sparkle_icon() -> None:
    offenders = [
        (spec["title"], spec["icon"])
        for spec in PAGE_SPECS
        if any(word in spec["icon"] for word in SPARKLES)
    ]
    assert offenders == []


def test_every_menu_icon_is_a_real_material_icon() -> None:
    from streamlit.material_icon_names import ALL_MATERIAL_ICONS

    for spec in PAGE_SPECS:
        match = re.fullmatch(r":material/([a-z0-9_]+):", spec["icon"])
        assert match and match.group(1) in ALL_MATERIAL_ICONS, spec


# --------------------------------------------------------------------------
# BUG-012: a visible focus ring on the main button
# --------------------------------------------------------------------------
def test_the_demo_button_shows_a_focus_ring() -> None:
    rules = [
        declarations
        for _, selector, declarations in _parse(_welcome_css())
        if ".st-key-landing_demo" in selector and ":focus-visible" in selector
    ]
    assert rules, "no :focus-visible rule for the Explore the demo button"
    outline = rules[0].get("outline", "none")
    assert "none" not in outline
    assert float(re.search(r"([\d.]+)px", outline).group(1)) >= 2


# --------------------------------------------------------------------------
# BUG-022: hit areas of the small built-in controls
# --------------------------------------------------------------------------
def _rule(selector_part: str):
    matches = [d for _, selector, d in _parse(layout._STYLES) if selector_part in selector]
    assert matches, f"no rule for {selector_part}"
    return matches[0]


def test_the_chip_remove_button_has_a_24px_hit_area() -> None:
    rule = _rule('[data-testid="stMultiSelect"] button[aria-label^="Remove"]')
    assert rule["min-width"] == "24px" and rule["min-height"] == "24px"


def test_the_help_and_heading_link_icons_get_a_24px_target_without_moving() -> None:
    """15px icon + 4.5px padding each side = 24px, and the same negative margin
    keeps the layout where it was."""
    rule = _rule(".stTooltipIcon button")
    assert rule["box-sizing"] == "content-box"
    assert rule["padding"] == "4.5px" and rule["margin"] == "-4.5px"
    assert 15 + 2 * 4.5 >= 24


def test_the_welcome_nav_links_are_24px_tall() -> None:
    rules = [
        d for _, selector, d in _parse(_welcome_css())
        if selector.endswith(".cp-nav-links a")
    ]
    assert rules and rules[0]["min-height"] == "24px"


# --------------------------------------------------------------------------
# BUG-014: the button on a phone
# --------------------------------------------------------------------------
@pytest.mark.parametrize("selector_part", ["landing_cta"])
def test_the_demo_button_fills_the_row_on_a_phone(selector_part: str) -> None:
    phone = [
        (selector, declarations)
        for context, selector, declarations in _parse(_welcome_css())
        if any("max-width: 720px" in c for c in context) and selector_part in selector
    ]
    widths = [d.get("width") for _, d in phone]
    assert "100%" in widths, f"nothing makes the button's container full width: {phone}"
