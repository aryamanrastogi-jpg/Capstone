"""Build docs/ui-one-pager.html from the template and the screenshots here.

The screenshots are embedded as data URIs so the page is one self-contained
file. Re-take a screenshot (same filename) and run this again to refresh it:

    python docs/showcase/build_showcase.py
"""

import base64
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "ui-one-pager.html"

SHOTS = {
    "desktop": "desktop-landing.png",
    "work": "phone-my-work.png",
    "camp": "phone-study-camp.png",
    "practice": "phone-practice.png",
}

html = (HERE / "showcase.template.html").read_text(encoding="utf-8")
for key, name in SHOTS.items():
    data = base64.b64encode((HERE / name).read_bytes()).decode("ascii")
    html = html.replace("{{" + key + "}}", "data:image/png;base64," + data)
assert "{{" not in html, "a placeholder was left unfilled"
OUT.write_text(html, encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
