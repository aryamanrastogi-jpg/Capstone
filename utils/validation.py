"""Input validation helpers.

Two jobs live here:
  1. Validating teacher-entered assessment drafts before they reach Pydantic.
  2. Validating uploaded files - extension, size, and actual content signature.
     An extension alone is never treated as sufficient proof of file type.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

from utils.config import ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_BYTES

_PDF_MAGIC = b"%PDF-"
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class ValidationError(Exception):
    """Raised for user-facing validation problems (never shown as a traceback)."""


@dataclass
class ValidationResult:
    ok: bool = True
    errors: List[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.ok = False
        self.errors.append(message)

    def __bool__(self) -> bool:  # pragma: no cover - convenience only
        return self.ok


# --------------------------------------------------------------------------
# Filenames and uploads
# --------------------------------------------------------------------------
def sanitize_filename(filename: str, fallback: str = "upload") -> str:
    """Reduce an arbitrary filename to a safe, flat basename.

    Strips directory components (including Windows separators), collapses
    unsafe characters, and caps the length.
    """
    if not filename:
        return fallback
    name = str(filename).replace("\\", "/")
    name = os.path.basename(name)
    name = name.replace("\x00", "")
    root, ext = os.path.splitext(name)
    root = _UNSAFE_FILENAME_CHARS.sub("_", root).strip("._-")
    ext = _UNSAFE_FILENAME_CHARS.sub("", ext).lower()
    if not root:
        root = fallback
    return f"{root[:80]}{ext[:10]}"


def file_extension(filename: str) -> str:
    return os.path.splitext(sanitize_filename(filename))[1].lower()


def validate_upload(
    filename: str,
    content: bytes,
    allowed_extensions: Sequence[str] | None = None,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> Tuple[bool, str]:
    """Validate an uploaded file. Returns (ok, message)."""
    allowed = set(allowed_extensions or ALLOWED_UPLOAD_EXTENSIONS)
    safe_name = sanitize_filename(filename)
    ext = file_extension(safe_name)

    if ext not in allowed:
        pretty = ", ".join(sorted(allowed))
        return False, f"Unsupported file type '{ext or 'unknown'}'. Allowed types: {pretty}."

    if content is None or len(content) == 0:
        return False, "The uploaded file is empty."

    if len(content) > max_bytes:
        limit_mb = max_bytes / (1024 * 1024)
        actual_mb = len(content) / (1024 * 1024)
        return False, f"File is {actual_mb:.1f} MB, which exceeds the {limit_mb:.0f} MB limit."

    # Content signature check - the extension is not trusted on its own.
    if ext == ".pdf" and not content.startswith(_PDF_MAGIC):
        return False, "This file is named .pdf but its contents are not a valid PDF."

    if ext == ".txt":
        if content.startswith(_PDF_MAGIC):
            return False, "This file is named .txt but its contents are a PDF."
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content.decode("latin-1")
            except UnicodeDecodeError:
                return False, "The text file could not be decoded. Please save it as UTF-8."

    return True, f"'{safe_name}' accepted."


# --------------------------------------------------------------------------
# Assessment drafts
# --------------------------------------------------------------------------
def validate_assessment_draft(
    title: str,
    topic: str,
    curriculum: str,
    questions: List[Dict[str, Any]],
) -> ValidationResult:
    """Validate the Create Assessment form before building Pydantic models."""
    result = ValidationResult()

    if not str(title or "").strip():
        result.add("Assessment title is required.")
    if not str(topic or "").strip():
        result.add("Topic is required.")
    if not str(curriculum or "").strip():
        result.add("Curriculum is required.")

    usable = [q for q in questions if _row_has_content(q)]
    if not usable:
        result.add("Add at least one question with text, a model answer and marks.")
        return result

    for index, row in enumerate(usable, start=1):
        if not str(row.get("question_text") or "").strip():
            result.add(f"Question {index}: question text is required.")
        if not str(row.get("model_answer") or "").strip():
            result.add(f"Question {index}: a model answer is required.")
        marks = row.get("max_marks")
        try:
            marks_value = float(marks)
        except (TypeError, ValueError):
            result.add(f"Question {index}: marks must be a number.")
            continue
        if marks_value <= 0:
            result.add(f"Question {index}: marks must be greater than zero.")
        elif marks_value > 100:
            result.add(f"Question {index}: marks must be 100 or fewer.")

    return result


def _row_has_content(row: Dict[str, Any]) -> bool:
    return any(
        str(row.get(key) or "").strip()
        for key in ("question_text", "model_answer", "marking_criteria")
    ) or bool(row.get("max_marks"))


def usable_question_rows(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [q for q in questions if _row_has_content(q)]


def total_marks(questions: List[Dict[str, Any]]) -> float:
    running = 0.0
    for row in usable_question_rows(questions):
        try:
            running += float(row.get("max_marks") or 0)
        except (TypeError, ValueError):
            continue
    return round(running, 2)


def clamp_score(score: float, max_marks: float) -> float:
    """Clamp a score into [0, max_marks] instead of raising."""
    return round(max(0.0, min(float(score), float(max_marks))), 2)
