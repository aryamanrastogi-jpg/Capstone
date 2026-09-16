"""Downloadable result reports (CSV and PDF).

WHAT GOES IN A REPORT
  Only teacher-finalised results - APPROVED or EDITED. A report is something a
  teacher hands on (to a parent, a head of department, a student record), so
  anything in it reads as an official mark. Results still awaiting review are
  AI recommendations, and flagged results are ones the teacher explicitly
  declined to approve; neither may appear as a score. They are counted instead,
  and the count is printed on the report so nobody mistakes a partial report
  for a complete one.

WHY THIS IS A SERVICE AND NOT PAGE CODE
  Both Review Grading and Class Analytics offer the download, and the
  exclusion rule above is the kind of thing that must not drift between two
  copies. Pure functions over models also make it testable without Streamlit.

WHY PyMuPDF FOR THE PDF
  It is already a dependency (document_service reads PDFs with it), so writing
  one adds nothing to install. If it is missing the PDF is simply unavailable;
  CSV never depends on it.
"""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence

from models import Assessment, GradingResult, Submission

REPORT_COLUMNS = [
    "student",
    "assessment",
    "question",
    "score",
    "max_marks",
    "error_categories",
    "teacher_feedback",
    "review_state",
]

SUMMARY_COLUMNS = ["assessment", "students", "results", "awarded", "available", "percentage"]

OFFICIAL_NOTE = (
    "Contains teacher-approved and teacher-edited results only. Results awaiting "
    "review and flagged results are excluded and are not official marks."
)


@dataclass(frozen=True)
class ReportRow:
    student: str
    assessment: str
    question: str
    score: float
    max_marks: float
    error_categories: str
    teacher_feedback: str
    review_state: str


@dataclass(frozen=True)
class SummaryRow:
    assessment: str
    students: int
    results: int
    awarded: float
    available: float
    percentage: float


@dataclass(frozen=True)
class Report:
    rows: List[ReportRow]
    summary: List[SummaryRow]
    awaiting_excluded: int
    flagged_excluded: int

    @property
    def is_empty(self) -> bool:
        return not self.rows


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------
def build_report(
    results: Sequence[GradingResult],
    assessments: Sequence[Assessment],
    submissions: Sequence[Submission],
) -> Report:
    """Collect official rows plus a per-assessment class summary.

    Results whose submission or assessment is not in the given lists are left
    out: the caller passes only what the viewer may see, and a row with no
    student or assessment attached would be an anonymous mark.
    """
    subs = {s.id: s for s in submissions}
    by_id = {a.id: a for a in assessments}

    rows: List[ReportRow] = []
    awaiting = flagged = 0
    for result in results:
        submission = subs.get(result.submission_id)
        assessment = by_id.get(submission.assessment_id) if submission else None
        if submission is None or assessment is None:
            continue
        if not result.is_finalised:
            if result.is_reviewed:
                flagged += 1
            else:
                awaiting += 1
            continue
        question = assessment.get_question(result.question_id)
        rows.append(
            ReportRow(
                student=submission.student_identifier,
                assessment=assessment.title,
                question=question.question_text if question else result.question_id,
                score=float(result.final_score or 0.0),
                max_marks=float(result.max_marks),
                error_categories="; ".join(e.error_type.label for e in result.errors),
                teacher_feedback=result.final_feedback,
                review_state=result.review_status.label,
            )
        )

    rows.sort(key=lambda r: (r.student, r.assessment))
    return Report(rows, _summarise(rows), awaiting, flagged)


def _summarise(rows: Sequence[ReportRow]) -> List[SummaryRow]:
    """One line per assessment and a final "All assessments" line."""
    groups: Dict[str, List[ReportRow]] = {}
    for row in rows:
        groups.setdefault(row.assessment, []).append(row)

    summary = [_summary_line(title, group) for title, group in sorted(groups.items())]
    if rows:
        summary.append(_summary_line("All assessments", rows))
    return summary


def _summary_line(title: str, rows: Sequence[ReportRow]) -> SummaryRow:
    awarded = round(sum(r.score for r in rows), 2)
    available = round(sum(r.max_marks for r in rows), 2)
    return SummaryRow(
        assessment=title,
        students=len({r.student for r in rows}),
        results=len(rows),
        awarded=awarded,
        available=available,
        percentage=round(100 * awarded / available, 1) if available else 0.0,
    )


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------
def to_csv(report: Report) -> bytes:
    """Results table, a blank line, then the class summary.

    UTF-8 with a BOM so Excel opens accented feedback correctly.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([OFFICIAL_NOTE])
    writer.writerow(
        [f"Excluded: {report.awaiting_excluded} awaiting review, "
         f"{report.flagged_excluded} flagged"]
    )
    writer.writerow([])
    writer.writerow(REPORT_COLUMNS)
    for row in report.rows:
        values = asdict(row)
        writer.writerow([values[c] for c in REPORT_COLUMNS])
    writer.writerow([])
    writer.writerow(["Class summary"])
    writer.writerow(SUMMARY_COLUMNS)
    for line in report.summary:
        values = asdict(line)
        writer.writerow([values[c] for c in SUMMARY_COLUMNS])
    return buffer.getvalue().encode("utf-8-sig")


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
_PAGE_W, _PAGE_H, _MARGIN, _LINE = 595, 842, 50, 14


def _load_pymupdf():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            import fitz
            return fitz
        except ImportError:
            return None


def pdf_available() -> bool:
    return _load_pymupdf() is not None


def to_pdf(report: Report, title: str = "AssessAI results report") -> Optional[bytes]:
    """A plain, paginated text PDF grouped by student. None if PyMuPDF is absent.

    Built from wrapped lines rather than a table layout: feedback is free text
    of any length, and a line writer paginates it without clipping.
    """
    pymupdf = _load_pymupdf()
    if pymupdf is None:
        return None

    lines: List[tuple[str, int]] = [(title, 15), (OFFICIAL_NOTE, 9)]
    lines.append((
        f"Excluded: {report.awaiting_excluded} awaiting review, "
        f"{report.flagged_excluded} flagged.", 9))
    lines.append(("", 10))

    current_student = None
    for row in report.rows:
        if row.student != current_student:
            current_student = row.student
            lines += [("", 10), (f"Student {row.student}", 12)]
        lines.append((
            f"{row.assessment} | {row.question} | {row.score:g} / {row.max_marks:g} "
            f"| {row.review_state}", 10))
        if row.error_categories:
            lines.append((f"    Errors: {row.error_categories}", 9))
        if row.teacher_feedback:
            lines.append((f"    Feedback: {row.teacher_feedback}", 9))

    lines += [("", 10), ("Class summary", 12)]
    for line in report.summary:
        lines.append((
            f"{line.assessment}: {line.students} students, {line.results} results, "
            f"{line.awarded:g} / {line.available:g} ({line.percentage}%)", 10))

    document = pymupdf.open()
    page, y = None, _PAGE_H
    for text, size in lines:
        for chunk in _wrap(text, size):
            if page is None or y > _PAGE_H - _MARGIN:
                page, y = document.new_page(width=_PAGE_W, height=_PAGE_H), _MARGIN
            page.insert_text((_MARGIN, y), chunk, fontsize=size)
            y += max(_LINE, size + 4)
    payload = document.tobytes()
    document.close()
    return payload


def _wrap(text: str, size: int) -> List[str]:
    """Word-wrap to the page width, estimating Helvetica at ~0.5em per char."""
    width = int((_PAGE_W - 2 * _MARGIN) / (size * 0.5))
    if not text:
        return [""]
    out: List[str] = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}".strip() if line else word
            if len(candidate) > width and line:
                out.append(line)
                line = word
            else:
                line = candidate
        out.append(line)
    return out
