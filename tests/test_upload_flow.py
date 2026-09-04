"""Headless tests for the Upload Responses page, driven through the real UI.

These exercise the whole upload path as a teacher experiences it: pick the
input mode, hand a file to `st.file_uploader`, read the extracted preview, then
confirm the submission and check that grading recommendations were produced.

The service-level extraction tests live in test_grading.py; this file is about
the page wiring - that a rejected file produces a visible error and no
submission, and that an accepted one flows through to a graded result.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pymupdf = pytest.importorskip("pymupdf")

APP = str(Path(__file__).resolve().parent.parent / "app.py")
UPLOAD_PAGE = "pages/upload_responses.py"

ANSWER_TEXT = "Q1: Subtract 7 from both sides so 3x = 15. Divide by 3, so x = 5."


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------
def _digital_pdf(text: str = ANSWER_TEXT) -> bytes:
    """A PDF with a real text layer, as produced by a word processor."""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 100), text)
    payload = document.tobytes()
    document.close()
    return payload


def _image_only_pdf() -> bytes:
    """A PDF with no text layer - what a scan or photo of handwriting looks like."""
    document = pymupdf.open()
    document.new_page()
    payload = document.tobytes()
    document.close()
    return payload


@pytest.fixture
def page() -> AppTest:
    """The Upload Responses page, signed in as a teacher, in file-upload mode.

    Upload Responses is a teacher page, and the app starts as a student, so the
    identity has to be switched before the page exists in navigation.
    """
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()

    teacher = next(u for u in at.session_state["users"] if u.is_teacher)
    at.session_state["current_user_id"] = teacher.id
    at.run()

    at.switch_page(UPLOAD_PAGE)
    at.run()
    assert not at.exception, at.exception

    at.radio[0].set_value("Upload a file")
    at.run()
    assert at.file_uploader, "the file uploader should be visible in upload mode"
    return at


def _upload(at: AppTest, filename: str, content: bytes, mime: str) -> AppTest:
    at.file_uploader[0].set_value((filename, content, mime))
    at.run()
    return at


def _messages(elements) -> str:
    return " ".join(element.value for element in elements)


def _counts(at: AppTest) -> tuple[int, int]:
    return (
        len(at.session_state["submissions"]),
        len(at.session_state["grading_results"]),
    )


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------
def test_digital_pdf_upload_previews_its_extracted_text(page):
    at = _upload(page, "typed_answers.pdf", _digital_pdf(), "application/pdf")

    assert not at.exception
    assert "Extracted" in _messages(at.success)
    assert not at.error

    preview = [t for t in at.text_area if t.label == "Extracted text *"]
    assert preview, "the extracted text should be shown for the teacher to check"
    assert "3x = 15" in preview[0].value


def _pick_student(at: AppTest, code: str) -> AppTest:
    """Choose a student from the teacher's roster."""
    picker = [s for s in at.selectbox if s.label == "Student *"]
    assert picker, "the roster picker should be shown when the teacher has students"
    picker[0].set_value(code)
    at.run()
    return at


def test_digital_pdf_upload_creates_a_graded_submission(page):
    at = _upload(page, "typed_answers.pdf", _digital_pdf(), "application/pdf")
    submissions_before, results_before = _counts(at)

    code = at.session_state["users"][1].display_name
    _pick_student(at, code)
    [b for b in at.button if b.label == "Confirm submission"][0].click()
    at.run()

    assert not at.exception
    submissions_after, results_after = _counts(at)
    assert submissions_after == submissions_before + 1
    assert results_after > results_before, "mock grading should have run"

    submission = at.session_state["submissions"][-1]
    assert submission.student_identifier == code
    assert submission.uploaded_filename == "typed_answers.pdf"
    assert "3x = 15" in submission.submission_text


def test_a_teacher_upload_is_linked_to_the_student_account(page):
    """Linking means the work also shows up in that student's own progress."""
    at = _upload(page, "typed_answers.pdf", _digital_pdf(), "application/pdf")

    student = at.session_state["users"][1]
    _pick_student(at, student.display_name)
    [b for b in at.button if b.label == "Confirm submission"][0].click()
    at.run()

    assert not at.exception
    submission = at.session_state["submissions"][-1]
    assert submission.student_id == student.id
    assert submission.is_self_study is False

    # Nothing the AI produced may be finalised without a teacher.
    new_results = [
        r for r in at.session_state["grading_results"]
        if r.submission_id == submission.id
    ]
    assert new_results
    assert all(r.review_status.value == "awaiting_review" for r in new_results)
    assert all(r.final_score is None for r in new_results)


def test_txt_upload_is_accepted(page):
    at = _upload(page, "answers.txt", ANSWER_TEXT.encode("utf-8"), "text/plain")

    assert not at.exception
    assert not at.error
    preview = [t for t in at.text_area if t.label == "Extracted text *"]
    assert preview and "x = 5" in preview[0].value


# ---------------------------------------------------------------------------
# Rejections - each must show a readable message and create nothing
# ---------------------------------------------------------------------------
def test_image_only_pdf_is_rejected_with_a_handwriting_explanation(page):
    before = _counts(page)
    at = _upload(page, "scanned_page.pdf", _image_only_pdf(), "application/pdf")

    assert not at.exception, "a scanned PDF must not raise"
    message = _messages(at.error)
    assert "handwritten or image-only" in message.lower()
    assert "not supported" in message.lower()

    assert not [t for t in at.text_area if t.label == "Extracted text *"]
    assert _counts(at) == before, "a rejected file must not create a submission"


def test_a_pdf_that_is_not_really_a_pdf_is_rejected(page):
    """The extension alone is never treated as proof of file type."""
    before = _counts(page)
    at = _upload(page, "fake.pdf", b"this is plain text pretending to be a PDF", "application/pdf")

    assert not at.exception
    assert "not a valid PDF" in _messages(at.error)
    assert _counts(at) == before


def test_an_oversized_pdf_is_rejected(page):
    """Padding after the header keeps it a valid PDF signature but over the cap."""
    from utils.config import MAX_UPLOAD_BYTES

    before = _counts(page)
    oversized = _digital_pdf() + b"\n%" + b"0" * (MAX_UPLOAD_BYTES + 1)
    at = _upload(page, "huge.pdf", oversized, "application/pdf")

    assert not at.exception
    assert "exceeds" in _messages(at.error)
    assert _counts(at) == before


def test_an_empty_pdf_upload_is_rejected(page):
    before = _counts(page)
    at = _upload(page, "empty.pdf", b"", "application/pdf")

    assert not at.exception
    assert "empty" in _messages(at.error).lower()
    assert _counts(at) == before


def test_a_password_protected_pdf_is_reported(page):
    document = pymupdf.open()
    document.new_page().insert_text((72, 100), ANSWER_TEXT)
    encrypted = document.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret"
    )
    document.close()

    before = _counts(page)
    at = _upload(page, "locked.pdf", encrypted, "application/pdf")

    assert not at.exception
    assert "password" in _messages(at.error).lower()
    assert _counts(at) == before


# ---------------------------------------------------------------------------
# Filename handling
# ---------------------------------------------------------------------------
def test_uploaded_filenames_are_sanitised_before_being_stored(page):
    at = _upload(page, "../../etc/my answers.pdf", _digital_pdf(), "application/pdf")

    _pick_student(at, at.session_state["users"][1].display_name)
    [b for b in at.button if b.label == "Confirm submission"][0].click()
    at.run()

    assert not at.exception
    stored = at.session_state["submissions"][-1].uploaded_filename
    assert stored == "my_answers.pdf"
    assert "/" not in stored and ".." not in stored


# ---------------------------------------------------------------------------
# Guard rails on the confirm step
# ---------------------------------------------------------------------------
def test_confirming_with_no_response_text_is_blocked(page):
    """The uploader was never used, so there is nothing to grade."""
    at = page
    before = _counts(at)

    _pick_student(at, at.session_state["users"][1].display_name)
    [b for b in at.button if b.label == "Confirm submission"][0].click()
    at.run()

    assert not at.exception
    # The page shows a heading via st.error and the specific problems as bullets.
    assert "Please fix the following" in _messages(at.error)
    assert "response text is empty" in _messages(at.markdown)
    assert _counts(at) == before
