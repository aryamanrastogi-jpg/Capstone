"""Document text extraction.

Supports plain text files, Word documents (.docx - also what Google Docs
downloads as) and *digital* PDFs (PDFs whose pages carry a real text layer).
Handwriting OCR and image-based answer interpretation are explicitly out of
scope for this phase - scanned or photographed pages are detected and reported
rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import re
import time
from typing import Dict, List, Optional, Tuple

from utils.config import (
    ALLOWED_UPLOAD_EXTENSIONS,
    MAX_PDF_EXTRACTION_SECONDS,
    MAX_UPLOAD_BYTES,
)
from utils.validation import file_extension, sanitize_filename, validate_upload

# A page with fewer characters than this is treated as having no usable text.
MIN_USABLE_CHARS = 15
MAX_PDF_PAGES = 100

NO_TEXT_MESSAGE = (
    "No readable text was found in this PDF. Camp Prep AI reads digital PDFs only - "
    "handwritten or image-only (scanned/photographed) pages are not supported in "
    "this version. Please type or paste the response instead."
)


@dataclass
class ExtractionResult:
    """Outcome of a text-extraction attempt. Never raises at the call site."""

    success: bool
    text: str = ""
    message: str = ""
    filename: str = ""
    page_count: int = 0

    @property
    def char_count(self) -> int:
        return len(self.text)


def extract_text(
    filename: str,
    content: bytes,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> ExtractionResult:
    """Validate an uploaded file and extract its text.

    Returns an ExtractionResult with a user-friendly message on failure rather
    than raising, so pages never surface a traceback.
    """
    safe_name = sanitize_filename(filename)

    ok, message = validate_upload(
        filename=filename,
        content=content,
        allowed_extensions=ALLOWED_UPLOAD_EXTENSIONS,
        max_bytes=max_bytes,
    )
    if not ok:
        return ExtractionResult(success=False, message=message, filename=safe_name)

    ext = file_extension(safe_name)
    if ext == ".txt":
        return _extract_txt(safe_name, content)
    if ext == ".pdf":
        return _extract_pdf(safe_name, content)
    if ext == ".docx":
        return _extract_docx(safe_name, content)

    return ExtractionResult(
        success=False,
        message=f"Unsupported file type '{ext}'.",
        filename=safe_name,
    )


def _extract_txt(safe_name: str, content: bytes) -> ExtractionResult:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")

    text = text.strip()
    if len(text) < MIN_USABLE_CHARS:
        return ExtractionResult(
            success=False,
            message="This text file appears to be empty or too short to grade.",
            filename=safe_name,
        )
    return ExtractionResult(
        success=True,
        text=text,
        message=f"Extracted {len(text)} characters from '{safe_name}'.",
        filename=safe_name,
        page_count=1,
    )


def _load_pymupdf():
    """Import PyMuPDF under whichever module name this release provides."""
    try:
        import pymupdf  # PyMuPDF >= 1.24 exposes the `pymupdf` name
        return pymupdf
    except ImportError:
        pass
    try:
        import fitz  # older PyMuPDF releases; `fitz` is deprecated
        return fitz
    except ImportError:
        return None


def _extract_pdf(safe_name: str, content: bytes) -> ExtractionResult:
    pymupdf = _load_pymupdf()
    if pymupdf is None:
        return ExtractionResult(
            success=False,
            message="PDF support requires PyMuPDF. Run: pip install -r requirements.txt",
            filename=safe_name,
        )

    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                return ExtractionResult(
                    success=False,
                    message=(
                        "This PDF is password protected. Please remove the password "
                        "and upload it again."
                    ),
                    filename=safe_name,
                )
            if document.page_count > MAX_PDF_PAGES:
                return ExtractionResult(
                    success=False,
                    message=f"This PDF has too many pages. The limit is {MAX_PDF_PAGES}.",
                    filename=safe_name,
                    page_count=document.page_count,
                )
            started = time.monotonic()
            pages = []
            for page in document:
                if time.monotonic() - started > MAX_PDF_EXTRACTION_SECONDS:
                    return ExtractionResult(
                        success=False,
                        message="This PDF took too long to read. Please upload a shorter file.",
                        filename=safe_name,
                        page_count=document.page_count,
                    )
                pages.append(page.get_text("text"))
                if time.monotonic() - started > MAX_PDF_EXTRACTION_SECONDS:
                    return ExtractionResult(
                        success=False,
                        message="This PDF took too long to read. Please upload a shorter file.",
                        filename=safe_name,
                        page_count=document.page_count,
                    )
            page_count = len(pages)
    except Exception as exc:  # noqa: BLE001 - reported to the teacher, not hidden
        return ExtractionResult(
            success=False,
            message=(
                f"This PDF could not be read ({type(exc).__name__}). It may be "
                "corrupted or in an unsupported format."
            ),
            filename=safe_name,
        )

    text = "\n\n".join(part.strip() for part in pages if part and part.strip()).strip()

    if len(text) < MIN_USABLE_CHARS:
        return ExtractionResult(
            success=False,
            message=NO_TEXT_MESSAGE,
            filename=safe_name,
            page_count=page_count,
        )

    return ExtractionResult(
        success=True,
        text=text,
        message=(
            f"Extracted {len(text)} characters from {page_count} "
            f"page{'s' if page_count != 1 else ''} of '{safe_name}'."
        ),
        filename=safe_name,
        page_count=page_count,
    )


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MAX_LIST_LEVEL = 8  # Word list levels run 0-8


def _extract_docx(safe_name: str, content: bytes) -> ExtractionResult:
    try:
        import docx  # python-docx
    except ImportError:
        return ExtractionResult(
            success=False,
            message="Word support requires python-docx. Run: pip install -r requirements.txt",
            filename=safe_name,
        )
    try:
        text = _docx_text(docx.Document(io.BytesIO(content)))
    except Exception as exc:  # noqa: BLE001 - reported plainly, never a traceback
        return ExtractionResult(
            success=False,
            message=(
                f"This Word file could not be read ({type(exc).__name__}). It may be "
                "corrupted - try saving it again, or as a PDF."
            ),
            filename=safe_name,
        )
    if len(text) < MIN_USABLE_CHARS:
        return ExtractionResult(
            success=False,
            message="This Word file appears to be empty, or its text is in pictures.",
            filename=safe_name,
        )
    return ExtractionResult(
        success=True,
        text=text,
        message=f"Extracted {len(text)} characters from '{safe_name}'.",
        filename=safe_name,
        page_count=1,
    )


def _docx_text(document) -> str:
    """The document's text in reading order: paragraphs and tables.

    Word keeps a numbered list's "1.", "2." out of the paragraph text - they
    are drawn from the list's settings - so they are put back here. Without
    them a question paper typed as a numbered list would arrive unnumbered.
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    formats = _numbering_formats(document)
    counters: Dict[str, List[int]] = {}
    lines: List[str] = []
    for child in document.element.body.iterchildren():
        if child.tag == _W + "p":
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if text:
                lines.append(_list_prefix(paragraph, formats, counters) + text)
            else:
                lines.append("")
        elif child.tag == _W + "tbl":
            for row in Table(child, document).rows:
                cells: List[str] = []
                for cell in row.cells:
                    value = cell.text.strip()
                    # A merged cell is repeated once per column it spans.
                    if value and (not cells or cells[-1] != value):
                        cells.append(value)
                if cells:
                    lines.append(" | ".join(cells))
            lines.append("")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _numbering_formats(document) -> Dict[Tuple[str, int], Tuple[str, int]]:
    """(list id, level) -> (number format, first number), from the Word file."""
    try:
        numbering = document.part.numbering_part.element
    except Exception:  # noqa: BLE001 - no numbering definitions at all
        return {}
    abstract: Dict[str, Dict[int, Tuple[str, int]]] = {}
    for definition in numbering.findall(_W + "abstractNum"):
        levels: Dict[int, Tuple[str, int]] = {}
        for level in definition.findall(_W + "lvl"):
            fmt = level.find(_W + "numFmt")
            start = level.find(_W + "start")
            levels[int(level.get(_W + "ilvl", "0"))] = (
                fmt.get(_W + "val", "decimal") if fmt is not None else "decimal",
                int(start.get(_W + "val", "1")) if start is not None else 1,
            )
        abstract[definition.get(_W + "abstractNumId")] = levels
    formats: Dict[Tuple[str, int], Tuple[str, int]] = {}
    for num in numbering.findall(_W + "num"):
        ref = num.find(_W + "abstractNumId")
        if ref is None:
            continue
        num_id = num.get(_W + "numId")
        for level, value in abstract.get(ref.get(_W + "val"), {}).items():
            formats[(num_id, level)] = value
        # A list can restart or continue its numbering from its own start
        # value ("startOverride"), e.g. questions 5-8 after a page of notes.
        for override in num.findall(_W + "lvlOverride"):
            start = override.find(_W + "startOverride")
            level = int(override.get(_W + "ilvl", "0"))
            if start is not None:
                fmt = formats.get((num_id, level), ("decimal", 1))[0]
                formats[(num_id, level)] = (fmt, int(start.get(_W + "val", "1")))
    return formats


def _list_prefix(paragraph, formats, counters: Dict[str, List[int]]) -> str:
    """The "3. " or "(b) " Word would draw before this paragraph, if any."""
    num_pr = paragraph._p.pPr.numPr if paragraph._p.pPr is not None else None
    style = paragraph.style
    while num_pr is None and style is not None:
        style_ppr = style.element.pPr
        num_pr = style_ppr.numPr if style_ppr is not None else None
        style = style.base_style
    if num_pr is None or num_pr.numId is None:
        return ""
    num_id = str(num_pr.numId.val)
    level = int(num_pr.ilvl.val) if num_pr.ilvl is not None else 0
    if num_id == "0":  # numbering switched off for this paragraph
        return ""
    if not 0 <= level <= _MAX_LIST_LEVEL:
        # Word has nine list levels. A file claiming level 1,000,000 would
        # otherwise have a counter list grown to that size.
        return ""
    fmt, start = formats.get((num_id, level), ("decimal", 1))
    seen = counters.setdefault(num_id, [])
    while len(seen) <= level:
        seen.append(0)
    seen[level] = seen[level] + 1 if seen[level] else start
    del seen[level + 1:]  # a deeper level restarts under each new item
    number = seen[level]
    if fmt == "decimal":
        return f"{number}. "
    if fmt in ("lowerLetter", "upperLetter"):
        letter = chr(ord("a") + (number - 1) % 26)
        return f"({letter if fmt == 'lowerLetter' else letter.upper()}) "
    if fmt in ("lowerRoman", "upperRoman"):
        numeral = _roman(number)
        return f"({numeral if fmt == 'lowerRoman' else numeral.upper()}) "
    if fmt == "bullet":
        return "- "
    return ""


def _roman(number: int) -> str:
    values = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for value, numeral in values:
        while number >= value:
            out += numeral
            number -= value
    return out


def read_uploaded_file(uploaded_file) -> ExtractionResult:
    """Convenience wrapper for a Streamlit UploadedFile object."""
    if uploaded_file is None:
        return ExtractionResult(success=False, message="No file was provided.")
    name: Optional[str] = getattr(uploaded_file, "name", None) or "upload"
    try:
        data = uploaded_file.getvalue()
    except Exception:  # noqa: BLE001
        uploaded_file.seek(0)
        data = uploaded_file.read()
    return extract_text(name, data)
