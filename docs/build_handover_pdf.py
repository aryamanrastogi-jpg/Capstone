"""Render docs/handover.html into docs/CampPrep-AI-Handover.pdf.

    python docs/build_handover_pdf.py

Uses PyMuPDF's Story engine, which the project already depends on for reading
uploaded PDFs - so building the handover needs nothing installed that running
the app does not already need.
"""

from __future__ import annotations

import io
import os
import sys

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "handover.html")
# Images in the HTML (the cover logo) are resolved from assets/.
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
OUTPUT = os.path.join(HERE, "CampPrep-AI-Handover.pdf")

# A4 with a generous margin: this is meant to be read, and printed if somebody
# wants it on paper.
PAGE = pymupdf.paper_rect("a4")
MARGIN = 56  # points, ~20mm

TITLE = "Camp Prep AI - Capstone Handover"


def build() -> str:
    with open(SOURCE, encoding="utf-8") as handle:
        html = handle.read()

    story = pymupdf.Story(html=html, archive=pymupdf.Archive(ASSETS))
    # Laid out in memory, then written once: see _stamp_page_numbers.
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    frame = PAGE + (MARGIN, MARGIN, -MARGIN, -MARGIN)

    more = True
    pages = 0
    while more:
        device = writer.begin_page(PAGE)
        more, _ = story.place(frame)
        story.draw(device)
        writer.end_page()
        pages += 1
        if pages > 200:  # a runaway layout should fail loudly, not fill a disk
            raise RuntimeError("handover.html did not finish laying out")

    writer.close()

    # Page numbers are added afterwards: the Story engine lays out a flow, and
    # only once it is finished do we know how many pages there are.
    _stamp_page_numbers(buffer.getvalue())
    return OUTPUT


def _stamp_page_numbers(laid_out: bytes) -> None:
    document = pymupdf.open("pdf", laid_out)
    document.set_metadata({"title": TITLE, "subject": "Code and product handover"})
    total = document.page_count
    for index, page in enumerate(document, start=1):
        if index == 1:
            continue  # the cover page carries no furniture
        page.insert_text(
            pymupdf.Point(PAGE.width - MARGIN - 44, PAGE.height - MARGIN + 22),
            f"{index} / {total}",
            fontsize=8,
            color=(0.28, 0.33, 0.41),
        )
    # Compressed on save: the Story engine stores the cover logo as raw
    # pixels, which is ~10 MB until deflated.
    document.save(OUTPUT, garbage=3, deflate=True, deflate_images=True)
    document.close()


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}", file=sys.stderr)
