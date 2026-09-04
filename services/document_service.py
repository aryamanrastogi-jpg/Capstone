"""Document text extraction.

Supports plain text files and *digital* PDFs (PDFs whose pages carry a real
text layer). Handwriting OCR and image-based answer interpretation are
explicitly out of scope for this phase - scanned or photographed pages are
detected and reported rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from utils.config import ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_BYTES
from utils.validation import file_extension, sanitize_filename, validate_upload

# A page with fewer characters than this is treated as having no usable text.
MIN_USABLE_CHARS = 15

NO_TEXT_MESSAGE = (
    "No readable text was found in this PDF. AssessAI reads digital PDFs only - "
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
            pages = [page.get_text("text") for page in document]
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
