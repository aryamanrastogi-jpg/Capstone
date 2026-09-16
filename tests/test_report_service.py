"""Report export: only teacher-settled marks may appear as scores."""

from __future__ import annotations

import csv
import io

import pytest

from models import (
    Assessment,
    ErrorItem,
    ErrorType,
    GradingResult,
    Question,
    ReviewStatus,
    Submission,
)
from services import report_service as reports


def _assessment() -> Assessment:
    return Assessment(
        id="as_1", title="Linear Equations", grade_level=10, topic="Algebra",
        questions=[
            Question(id="q1", question_text="Solve 2x = 8", model_answer="x = 4", max_marks=2),
            Question(id="q2", question_text="Solve x + 1 = 4", model_answer="x = 3", max_marks=3),
            Question(id="q3", question_text="Solve 5x = 10", model_answer="x = 2", max_marks=5),
        ],
    )


def _submission(sid: str, code: str) -> Submission:
    return Submission(id=sid, assessment_id="as_1", student_identifier=code,
                      submission_text="answers")


def _result(sid: str, qid: str, max_marks: float, **kwargs) -> GradingResult:
    return GradingResult(submission_id=sid, question_id=qid, max_marks=max_marks,
                         suggested_score=1, confidence=0.7,
                         student_feedback="AI feedback", **kwargs)


@pytest.fixture()
def report() -> reports.Report:
    results = [
        _result("sub_a", "q1", 2, review_status=ReviewStatus.APPROVED,
                teacher_approved_score=1, teacher_approved_feedback="AI feedback",
                errors=[ErrorItem(error_type=ErrorType.ARITHMETIC_ERROR, explanation="8/2")]),
        _result("sub_a", "q2", 3, review_status=ReviewStatus.EDITED,
                teacher_approved_score=2.5, teacher_approved_feedback="Good method"),
        _result("sub_a", "q3", 5),  # awaiting review
        _result("sub_b", "q1", 2, review_status=ReviewStatus.FLAGGED),
        _result("sub_b", "q2", 3, review_status=ReviewStatus.APPROVED,
                teacher_approved_score=3, teacher_approved_feedback="Perfect"),
    ]
    return reports.build_report(
        results, [_assessment()], [_submission("sub_a", "S-1"), _submission("sub_b", "S-2")]
    )


def test_only_approved_and_edited_results_are_rows(report) -> None:
    assert [(r.student, r.question, r.score, r.review_state) for r in report.rows] == [
        ("S-1", "Solve 2x = 8", 1.0, "Approved"),
        ("S-1", "Solve x + 1 = 4", 2.5, "Edited"),
        ("S-2", "Solve x + 1 = 4", 3.0, "Approved"),
    ]
    assert report.awaiting_excluded == 1
    assert report.flagged_excluded == 1


def test_rows_carry_teacher_feedback_and_error_categories(report) -> None:
    first, second, _ = report.rows
    assert first.error_categories == "Arithmetic Error"
    assert second.teacher_feedback == "Good method"
    assert first.max_marks == 2


def test_class_summary_totals_official_marks_only(report) -> None:
    *per_assessment, overall = report.summary
    assert [s.assessment for s in per_assessment] == ["Linear Equations"]
    assert overall.assessment == "All assessments"
    assert (overall.students, overall.results, overall.awarded, overall.available) == (2, 3, 6.5, 8)
    assert overall.percentage == 81.2


def test_results_outside_the_visible_lists_are_dropped() -> None:
    stray = _result("sub_unknown", "q1", 2, review_status=ReviewStatus.APPROVED)
    report = reports.build_report([stray], [_assessment()], [])
    assert report.is_empty
    assert report.summary == []


def test_csv_has_header_rows_summary_and_exclusion_note(report) -> None:
    text = reports.to_csv(report).decode("utf-8-sig")
    table = list(csv.reader(io.StringIO(text)))

    assert "not official" in table[0][0]
    assert table[1] == ["Excluded: 1 awaiting review, 1 flagged"]
    header = table.index(reports.REPORT_COLUMNS)
    body = table[header + 1: header + 4]
    assert [row[0] for row in body] == ["S-1", "S-1", "S-2"]
    assert body[1][3:5] == ["2.5", "3.0"]
    assert "Solve 5x = 10" not in text, "an awaiting-review question must not be exported"
    summary_at = table.index(["Class summary"])
    assert table[summary_at + 1] == reports.SUMMARY_COLUMNS
    assert table[-1][0] == "All assessments"


def test_pdf_contains_the_rows_and_the_note(report) -> None:
    pymupdf = pytest.importorskip("pymupdf")
    payload = reports.to_pdf(report)
    assert payload is not None and payload.startswith(b"%PDF")

    document = pymupdf.open(stream=payload, filetype="pdf")
    text = " ".join(page.get_text() for page in document)
    document.close()
    assert "Student S-1" in text and "Student S-2" in text
    assert "Good method" in text
    assert "not official" in text
    assert "Solve 5x = 10" not in text
    assert "Class summary" in text


def test_long_feedback_paginates_instead_of_clipping() -> None:
    pymupdf = pytest.importorskip("pymupdf")
    results = [
        _result(f"sub_{i}", "q1", 2, review_status=ReviewStatus.EDITED,
                teacher_approved_score=2, teacher_approved_feedback="word " * 120)
        for i in range(12)
    ]
    subs = [_submission(f"sub_{i}", f"S-{i:02d}") for i in range(12)]
    payload = reports.to_pdf(reports.build_report(results, [_assessment()], subs))

    document = pymupdf.open(stream=payload, filetype="pdf")
    assert document.page_count > 1
    assert "Student S-11" in document[-1].get_text()
    document.close()


def test_empty_report_still_exports() -> None:
    empty = reports.build_report([], [], [])
    assert empty.is_empty
    assert reports.to_csv(empty)
    if reports.pdf_available():
        assert reports.to_pdf(empty).startswith(b"%PDF")
