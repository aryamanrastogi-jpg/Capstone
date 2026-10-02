"""Build the Camp Prep AI logo family into assets/.

    pip install fonttools
    python tools/build_logo.py

Everything is drawn here as plain geometry, so the logo is a sharp vector at
any size: change a coordinate or a colour, re-run, and every variant follows.
The mark lives in a 512x512 box centred on (256, 256).

The wordmark is outlined from Plus Jakarta Sans, the app's own font (OFL). Put
the variable TTF next to this script as tools/PlusJakartaSans.ttf - it is not
committed - from
https://github.com/google/fonts/raw/main/ofl/plusjakartasans/PlusJakartaSans%5Bwght%5D.ttf
Outlining matters: an SVG shown through <img> never loads web fonts, so live
<text> would fall back to whatever the visitor's machine has.

Outputs (assets/):
    mark.svg       the emblem alone, for light surfaces
    icon.svg       simplified emblem on a white disc: browser tab, collapsed sidebar
    logo.svg       detailed emblem on a white disc: top of the indigo sidebar
    logo_dark.svg  horizontal lockup (emblem, name, strapline) for the landing page
    logo_full.svg  stacked lockup, as in the original artwork: README, documents
    *.png          high-resolution transparent exports, when Edge or Chrome exists

Colours are the ones in utils/palette.py.
"""
import os
import shutil
import subprocess
import tempfile

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets")
FONT = os.path.join(HERE, "PlusJakartaSans.ttf")

# --- palette (utils/palette.py) -------------------------------------------
PRIMARY = "#1B2CC1"
INDIGO = "#2F39A9"
LIP = "#121D8A"
ORANGE = "#FF9100"
MUTED = "#555C85"
SLATE = "#8D93BC"   # the book and shield: the source's grey, leaned indigo
WHITE = "#FFFFFF"


def star(cx, cy, s, pinch=0.16):
    p = s * pinch
    return (
        f"M{cx} {cy - s}"
        f"C{cx + p} {cy - p} {cx + p} {cy - p} {cx + s} {cy}"
        f"C{cx + p} {cy + p} {cx + p} {cy + p} {cx} {cy + s}"
        f"C{cx - p} {cy + p} {cx - p} {cy + p} {cx - s} {cy}"
        f"C{cx - p} {cy - p} {cx - p} {cy - p} {cx} {cy - s}Z"
    )


def node(cx, cy, fill, r=8.5):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{WHITE}" stroke-width="6"/>'


def mark(uid, detail=True, star_colour=ORANGE, ring=PRIMARY, gap=WHITE):
    """The emblem. `detail=False` drops the circuitry for tiny sizes."""
    # Ridges: main apex (256,170) slope 1.53; left back peak (150,250);
    # right back peak (360,236). Everything below is clipped to the ring.
    main = "M256 170L-50 638L562 638Z"
    left = "M148 238L-140 612L300 600Z"
    right = "M362 224L640 586L180 600Z"
    # Shadow face of the main peak: right of a line from the apex.
    main_shadow = "M256 170L562 638L286 638Z"
    right_shadow = "M362 224L640 586L394 600Z"
    left_shadow = "M148 238L300 600L164 600Z"

    parts = [
        f'<defs><clipPath id="{uid}c"><circle cx="256" cy="256" r="213"/></clipPath></defs>',
        # Shield brackets and the open book.
        f'<g fill="none" stroke="{SLATE}" stroke-linejoin="miter" stroke-miterlimit="10">',
        '<path d="M106 120V226Q107 262 132 292" stroke-width="16"/>',
        '<path d="M406 120V226Q405 262 380 292" stroke-width="16"/>',
        '<path d="M138 270V104Q206 96 256 150Q306 96 374 104V270" stroke-width="18"/>',
        "</g>",
        f'<path d="M174 99Q256 30 338 99Q256 82 174 99Z" fill="{SLATE}"/>',
        # Stars.
        f'<path d="{star(306, 198, 23)}" fill="{star_colour}"/>',
        f'<path d="{star(340, 160, 12)}" fill="{star_colour}"/>',
        # Mountains, back to front, each cut out of the one behind by a gap.
        f'<g clip-path="url(#{uid}c)" stroke="{gap}" stroke-width="9" stroke-linejoin="miter">',
        f'<path d="{left}" fill="{INDIGO}"/>',
        f'<path d="{left_shadow}" fill="{LIP}" stroke="none"/>',
        f'<path d="{right}" fill="{INDIGO}"/>',
        f'<path d="{right_shadow}" fill="{LIP}" stroke="none"/>',
        f'<path d="{main}" fill="{PRIMARY}"/>',
        f'<path d="{main_shadow}" fill="{LIP}" stroke="none"/>',
        "</g>",
    ]
    if detail:
        traces = [
            # (path, node, face colour under the node)
            ("M200 520V402L230 364V320", (230, 311), PRIMARY),
            ("M160 520V432L188 396V384", (188, 375), PRIMARY),
            ("M84 500V424L110 392V368", (110, 359), INDIGO),
            ("M308 520V412L290 390V344", (290, 335), LIP),
            ("M346 520V430L328 408V392", (328, 383), LIP),
            ("M432 500V404L414 382V364", (414, 355), LIP),
        ]
        parts.append(
            f'<g clip-path="url(#{uid}c)" fill="none" stroke="{WHITE}" '
            'stroke-width="7" stroke-linecap="round" stroke-linejoin="round">'
        )
        parts += [f'<path d="{d}"/>' for d, _, _ in traces]
        parts.append("</g>")
        parts += [node(x, y, f) for _, (x, y), f in traces]
    parts.append(f'<circle cx="256" cy="256" r="225" fill="none" stroke="{ring}" stroke-width="20"/>')
    return "".join(parts)


# --- text to outlines ------------------------------------------------------
def font_at(weight):
    return instantiateVariableFont(TTFont(FONT), {"wght": weight})


FONTS = {}


def text_path(txt, x, y, size, weight, tracking=0.0):
    """Outline `txt` with its baseline at (x, y). Returns (path d, advance)."""
    if weight not in FONTS:
        FONTS[weight] = font_at(weight)
    f = FONTS[weight]
    upm = f["head"].unitsPerEm
    scale = size / upm
    cmap = f.getBestCmap()
    gs = f.getGlyphSet()
    hmtx = f["hmtx"]
    pen = SVGPathPen(gs)
    cursor = 0.0
    for ch in txt:
        g = cmap[ord(ch)]
        tp = TransformPen(pen, (scale, 0, 0, -scale, x + cursor, y))
        gs[g].draw(tp)
        cursor += hmtx[g][0] * scale + tracking * size
    cursor -= tracking * size
    return pen.getCommands(), cursor


def svg(w, h, body, label="Camp Prep AI", extra=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}" role="img" aria-label="{label}"{extra}>'
        f"{body}</svg>\n"
    )


def write(name, content):
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


# 1. The mark alone, for light surfaces.
write("mark.svg", svg(512, 512, mark("m")))

# 2. App icon: the mark on a white disc, so it holds on the indigo sidebar and
#    on dark browser tabs. Simplified (no circuitry) - it is drawn at 16-32px.
write(
    "icon.svg",
    svg(512, 512, f'<circle cx="256" cy="256" r="256" fill="{WHITE}"/>'
        f'<g transform="translate(256 256) scale(1.06) translate(-256 -256)">{mark("i", detail=False)}</g>'),
)

# 3. Sidebar logo: the detailed mark on a white disc (the name is left off).
write(
    "logo.svg",
    svg(512, 512, f'<circle cx="256" cy="256" r="256" fill="{WHITE}"/>'
        f'<g transform="translate(256 256) scale(1.06) translate(-256 -256)">{mark("s")}</g>'),
)

# 4. Full lockup, stacked, for light backgrounds: mark, name, strapline.
name_d, name_w = text_path("CAMP PREP AI", 0, 0, 96, 800, tracking=0.02)
tag_d, tag_w = text_path("PERSISTENT DIAGNOSTICS & INTENSIVE MASTERY", 0, 0, 30, 600, tracking=0.06)
W = max(name_w, tag_w) + 40
name_d, _ = text_path("CAMP PREP AI", (W - name_w) / 2, 640, 96, 800, tracking=0.02)
tag_d, _ = text_path("PERSISTENT DIAGNOSTICS & INTENSIVE MASTERY", (W - tag_w) / 2, 700, 30, 600, tracking=0.06)
write(
    "logo_full.svg",
    svg(round(W), 720,
        f'<g transform="translate({(W - 512) / 2:.1f} 0)">{mark("f")}</g>'
        f'<path d="{name_d}" fill="{PRIMARY}"/><path d="{tag_d}" fill="{MUTED}"/>'),
)

# 5. Horizontal lockup for the landing page header: mark + name + strapline.
#    The strapline is sized to run exactly the width of the name, as in the
#    stacked version, so it stays readable when the lockup is ~80px tall.
NAME, SLOGAN = "CAMP PREP AI", "PERSISTENT DIAGNOSTICS & INTENSIVE MASTERY"
_, h_name_w = text_path(NAME, 0, 0, 236, 800, tracking=0.01)
_, probe_w = text_path(SLOGAN, 0, 0, 100, 650, tracking=0.03)
tag_size = 100 * h_name_w / probe_w
h_name_d, _ = text_path(NAME, 580, 300, 236, 800, tracking=0.01)
h_tag_d, _ = text_path(SLOGAN, 584, 300 + 40 + tag_size, tag_size, 650, tracking=0.03)
HW = 580 + h_name_w + 16
write(
    "logo_dark.svg",
    svg(round(HW), 512,
        f'{mark("h")}<path d="{h_name_d}" fill="{PRIMARY}"/><path d="{h_tag_d}" fill="{MUTED}"/>'),
)


# --- PNG exports -------------------------------------------------------------
def _browser():
    for path in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ):
        if os.path.exists(path):
            return path
    return shutil.which("chromium") or shutil.which("google-chrome")


def export_png(svg_name, width, height, png_name):
    browser = _browser()
    if not browser:
        print("no Edge/Chrome found; skipped", png_name)
        return
    src = os.path.join(OUT, svg_name).replace(os.sep, "/")
    page = (
        "<!doctype html><style>html,body{margin:0;background:transparent}"
        f"img{{display:block}}</style><img src='file:///{src}' width='{width}' height='{height}'>"
    )
    with tempfile.TemporaryDirectory() as tmp:
        html = os.path.join(tmp, "page.html")
        with open(html, "w", encoding="utf-8") as fh:
            fh.write(page)
        subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--allow-file-access-from-files",
             "--hide-scrollbars", "--default-background-color=00000000",
             "--force-device-scale-factor=1", f"--window-size={width},{height}",
             f"--screenshot={os.path.join(OUT, png_name)}", "file:///" + html.replace(os.sep, "/")],
            check=True, capture_output=True,
        )


export_png("logo_full.svg", round(W) * 2, 1440, "logo_full.png")
export_png("mark.svg", 1024, 1024, "mark.png")
export_png("icon.svg", 512, 512, "icon.png")
print("written to", OUT)
