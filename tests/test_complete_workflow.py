"""The whole teacher loop, end to end, through the real pages in demo mode.

create assessment -> upload a response -> AI recommendation -> teacher approves
-> Class Analytics counts it -> the downloaded report contains it.

Each step is driven through the page a teacher would use, so a break in the
hand-off between two pages (a key renamed, a status not refreshed, a result not
saved) fails here even when every page renders and every service passes.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Dict

import pandas as pd
import pytest
from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")

TITLE = "Workflow Check - Simultaneous Equations"
QUESTION = "Solve 4x - 3 = 13"
ANSWER = "Add 3 to both sides so 4x = 16. Divide by 4, so x = 4."


def _button(at: AppTest, label: str):
    matches = [b for b in at.button if b.label == label]
    assert matches, f"no button labelled {label!r}"
    return matches[0]


def _choose(at: AppTest, label: str, starts_with: str) -> None:
    """Pick an option by its visible label.

    These selectboxes hold ids and show a formatted label; AppTest sees only the
    labels, so the option is chosen by position rather than by id.
    """
    box = next(s for s in at.selectbox if s.label == label)
    index = next(i for i, o in enumerate(box.options) if o.startswith(starts_with))
    box.select_index(index).run()


def _downloaded(at: AppTest, downloads: Dict[str, bytes], label: str) -> bytes:
    """The bytes behind a download button, matched on the file id in its URL."""
    button = next(b for b in at.download_button if b.label == label)
    file_id = button.proto.url.rsplit("/", 1)[-1].split(".")[0]
    return downloads[file_id]


@pytest.fixture()
def downloads(monkeypatch: pytest.MonkeyPatch) -> Dict[str, bytes]:
    """Capture every file handed to Streamlit's media storage, by id.

    AppTest builds a fresh in-memory storage per run and discards it afterwards,
    so the bytes behind a download button are recorded as they are stored.
    """
    captured: Dict[str, bytes] = {}
    original = MemoryMediaFileStorage.load_and_get_id

    def recording(self, path_or_data, mimetype, kind, filename=None):
        file_id = original(self, path_or_data, mimetype, kind, filename)
        captured[file_id] = self._files_by_id[file_id].content
        return file_id

    monkeypatch.setattr(MemoryMediaFileStorage, "load_and_get_id", recording)
    return captured


@pytest.fixture()
def teacher_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    teacher = next(u for u in at.session_state["users"] if u.is_teacher)
    at.session_state["current_user_id"] = teacher.id
    at.session_state["entered_demo"] = True
    at.run()
    assert not at.exception, at.exception
    return at


def test_teacher_workflow_from_assessment_to_report(
    teacher_app: AppTest, downloads: Dict[str, bytes]
) -> None:
    at = teacher_app

    # 1. Create the assessment.
    at.switch_page("pages/create_assessment.py").run()
    at.session_state["create_assessment_rows"] = pd.DataFrame(
        [{"question_text": QUESTION, "model_answer": "4x = 16, so x = 4",
          "marking_criteria": "1 mark for 4x = 16, 1 mark for x = 4", "max_marks": 2.0}]
    )
    at.text_input(key="ca_title").set_value(TITLE)
    at.text_input(key="ca_topic").set_value("Algebra")
    at.run()
    _button(at, "Save assessment").click().run()
    assert not at.exception, at.exception
    assessment = next(a for a in at.session_state["assessments"] if a.title == TITLE)
    assert [q.question_text for q in assessment.questions] == [QUESTION]

    # 2. Upload a response for a student on the roster.
    at.switch_page("pages/upload_responses.py").run()
    _choose(at, "Assessment *", TITLE)
    student = next(s for s in at.selectbox if s.label == "Student *")
    code = student.options[0]
    student.set_value(code).run()
    next(t for t in at.text_area if t.label == "Student response *").set_value(ANSWER).run()
    _button(at, "Confirm submission").click().run()
    assert not at.exception, at.exception

    submission = next(
        s for s in at.session_state["submissions"] if s.assessment_id == assessment.id
    )
    assert submission.student_identifier == code

    # 3. A recommendation exists, and it is not a mark yet.
    results = [r for r in at.session_state["grading_results"]
               if r.submission_id == submission.id]
    assert len(results) == 1
    assert results[0].review_status.value == "awaiting_review"
    assert results[0].final_score is None
    suggested = results[0].suggested_score

    # 4. The teacher approves it on Review Grading.
    at.switch_page("pages/review_grading.py").run()
    _choose(at, "Submission", f"{code} · {TITLE}")
    assert not at.exception, at.exception
    _button(at, "Accept as-is").click().run()
    assert not at.exception, at.exception

    approved = next(r for r in at.session_state["grading_results"]
                    if r.submission_id == submission.id)
    assert approved.review_status.value == "approved"
    assert approved.final_score == suggested
    assert submission.status.value == "reviewed"

    # 5. Class Analytics counts it.
    at.switch_page("pages/analytics.py").run()
    assert not at.exception, at.exception
    counted = next(m for m in at.metric if m.label == "Approved results")
    all_results = at.session_state["grading_results"]
    assert int(counted.value) == sum(1 for r in all_results if r.is_finalised)
    assert int(counted.value) >= 1

    # 6. The downloads contain it, and nothing unreviewed.
    table = list(csv.reader(io.StringIO(
        _downloaded(at, downloads, "Download CSV").decode("utf-8-sig")
    )))
    ours = [row for row in table if len(row) > 2 and row[1] == TITLE]
    assert ours == [[code, TITLE, QUESTION, str(float(suggested)), "2.0",
                     ours[0][5], approved.final_feedback, "Approved"]]
    assert any(row and row[0] == "All assessments" for row in table)
    exported = {(row[0], row[2]) for row in table if len(row) == 8}
    for result in all_results:
        if not result.is_finalised:
            sub = next(s for s in at.session_state["submissions"]
                       if s.id == result.submission_id)
            a = next((x for x in at.session_state["assessments"]
                      if x.id == sub.assessment_id), None)
            q = a.get_question(result.question_id) if a else None
            if q is not None:
                assert (sub.student_identifier, q.question_text) not in exported

    pymupdf = pytest.importorskip("pymupdf")
    document = pymupdf.open(stream=_downloaded(at, downloads, "Download PDF"), filetype="pdf")
    text = " ".join(page.get_text() for page in document)
    document.close()
    assert f"Student {code}" in text
    assert QUESTION in text
