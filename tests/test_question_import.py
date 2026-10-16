"""Starting a question set from a file instead of typing it.

Covers the reading (services/question_import.py), Word files
(services/document_service.py), and the panel on both pages putting what it
read into the question table.
"""

from __future__ import annotations

import io
import json

import pandas as pd
import pytest

from services import llm_service
from services import question_import as importer
from services.document_service import extract_text
from tests.test_form_page_fixes import _app_as, _button, _labels
from utils.validation import validate_upload

def _texts(result):
    return [q.question_text for q in result.questions]


# ---------------------------------------------------------------------------
# Reading the questions out of the text
# ---------------------------------------------------------------------------
def test_numbered_questions_are_split_with_their_marks():
    result = importer.import_questions(
        "Algebra worksheet 4\nAnswer all questions.\n\n"
        "1. Solve 2x + 3 = 11. [2]\n"
        "2) Solve 5 - x = 2.\n   Show your working. (3 marks)\n"
        "3. Expand 2(x + 3)."
    )

    assert result.method == importer.METHOD_NUMBERS
    assert _texts(result) == [
        "Solve 2x + 3 = 11.",
        "Solve 5 - x = 2.\nShow your working.",
        "Expand 2(x + 3).",
    ]
    assert [q.max_marks for q in result.questions] == [2, 3, 1]
    assert [q.marks_found for q in result.questions] == [True, True, False]
    assert "Marks were read for 2" in result.message


def test_parts_stay_in_their_question_and_their_marks_add_up():
    result = importer.import_questions(
        "1. A number is multiplied by 4 and then 6 is subtracted. The result is 26.\n"
        "(a) Form an equation. [1]\n"
        "(b) Solve it. [2]\n"
        "2(a) Write 0.25 as a fraction. [1]\n"
        "2(b) Write 3/4 as a percentage. [1]\n"
        "3. Simplify 18 : 21. [Total: 2]"
    )

    assert len(result.questions) == 3
    first, second, third = result.questions
    assert "(a) Form an equation. [1]" in first.question_text
    assert "(b) Solve it. [2]" in first.question_text
    assert first.max_marks == 3
    assert second.question_text.startswith("(a) Write 0.25")
    assert "2(b) Write 3/4" in second.question_text
    assert second.max_marks == 2
    assert third.max_marks == 2 and "Total" not in third.question_text


def test_a_numbered_list_inside_a_question_is_not_split():
    result = importer.import_questions(
        "1. Solve the equation 3x + 1 = 10 using these steps:\n"
        "1. subtract 1 from both sides\n"
        "2. divide both sides by 3\n"
        "2. Expand 2(x + 3). [2]"
    )

    assert len(result.questions) == 2
    assert "2. divide both sides by 3" in result.questions[0].question_text
    assert result.questions[1].question_text == "Expand 2(x + 3)."


def test_data_lines_are_not_mistaken_for_question_numbers():
    result = importer.import_questions(
        "1. Find the mean of these numbers:\n3 5 7 9\n2. Find their range."
    )

    assert _texts(result) == ["Find the mean of these numbers:\n3 5 7 9", "Find their range."]


def test_printed_papers_with_bare_numbers_and_answer_lines():
    result = importer.import_questions(
        "1 Work out 3.5 x 2. ............................................ [1]\n"
        "2 (a) Write 0.25 as a fraction. ..................... [1]\n"
        "(b) Write 3/4 as a percentage. ....................... [1]\n"
        "x = ...........................\n"
        "© UCLES 2024 0580/12/M/J/24 [Turn over\n"
    )

    assert _texts(result) == [
        "Work out 3.5 x 2.",
        "(a) Write 0.25 as a fraction. [1]\n(b) Write 3/4 as a percentage. [1]",
    ]
    assert [q.max_marks for q in result.questions] == [1, 2]


def test_answers_inline_and_in_an_answer_section():
    result = importer.import_questions(
        "Question 1\nWork out 3 + 4 x 2.\nAnswer: 11\n"
        "Question 2\nSimplify 18 : 21 [1]\n"
        "Question 3\nWrite 0.5 as a percentage.\n\n"
        "Answers\n1. 11\n2. 6 : 7\n3. 50%"
    )

    assert [q.model_answer for q in result.questions] == ["11", "6 : 7", "50%"]
    assert result.answers_found_count == 3


def test_unnumbered_text_falls_back_to_lines_or_paragraphs():
    lines = importer.import_questions("What is 7 x 8?\nWrite 0.5 as a percentage.")
    assert lines.method == importer.METHOD_LINES
    assert _texts(lines) == ["What is 7 x 8?", "Write 0.5 as a percentage."]
    assert "Delete any that are instructions" in lines.message

    paragraphs = importer.import_questions("Find x if\n2x = 8.\n\nFind y if\ny + 1 = 3.")
    assert paragraphs.method == importer.METHOD_PARAGRAPHS
    assert len(paragraphs.questions) == 2


def test_nothing_is_invented_and_empty_text_finds_nothing():
    result = importer.import_questions("1. Solve 2x = 8.\n2. Solve 3x = 9.")
    assert all(q.model_answer == "" for q in result.questions)
    assert all(q.max_marks == importer.DEFAULT_MARKS for q in result.questions)
    assert "starts at 1 mark" in result.message

    assert not importer.import_questions("   ").found


def test_editor_rows_and_suggested_title():
    result = importer.import_questions("1. Solve 2x = 8. [2]\n2. Solve 3x = 9.")
    assert result.editor_rows() == [
        {"question_text": "Solve 2x = 8.", "model_answer": "", "marking_criteria": "", "max_marks": 2.0},
        {"question_text": "Solve 3x = 9.", "model_answer": "", "marking_criteria": "", "max_marks": 1.0},
    ]
    assert importer.suggested_title("algebra_worksheet-4.pdf") == "Algebra worksheet 4"
    assert importer.suggested_title("") == ""


# ---------------------------------------------------------------------------
# The AI reading keeps only what is in the file
# ---------------------------------------------------------------------------
class _FakeModel:
    name = "fake"

    def __init__(self, reply: dict) -> None:
        self.reply = reply
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return json.dumps(self.reply)


@pytest.fixture(autouse=True)
def _empty_ai_cache():
    llm_service._CACHE.clear()
    yield
    llm_service._CACHE.clear()


def test_ai_reading_drops_questions_and_answers_not_in_the_file():
    source = (
        "Worksheet\nSolve 2x + 3 = 11 for x [2]\nWork out the area of a\n"
        "rectangle 3 cm by 4 cm.\nMark scheme: x = 4"
    )
    model = _FakeModel({"questions": [
        {"question": "Solve 2x + 3 = 11 for x [2]", "answer": "x = 4", "marks": 2},
        {"question": "Work out the area of a rectangle 3 cm by 4 cm.", "answer": "12 cm²", "marks": 5},
        {"question": "Prove that the square root of 2 is irrational.", "answer": "", "marks": 4},
    ]})

    result = importer.ai_import_questions(source, model=model)

    assert result.method == importer.METHOD_AI
    assert _texts(result) == [
        "Solve 2x + 3 = 11 for x",
        "Work out the area of a rectangle 3 cm by 4 cm.",
    ]
    first, second = result.questions
    assert (first.model_answer, first.max_marks) == ("x = 4", 2)
    # "12 cm²" was worked out, not copied; 5 marks is printed nowhere.
    assert (second.model_answer, second.max_marks, second.marks_found) == ("", 1, False)
    assert "1 suggestion was left out" in result.message


def test_ai_reading_is_cached_and_none_without_a_model(monkeypatch):
    model = _FakeModel({"questions": [{"question": "Solve 2x = 8.", "answer": "", "marks": None}]})
    importer.ai_import_questions("1. Solve 2x = 8.", model=model)
    importer.ai_import_questions("1. Solve 2x = 8.", model=model)
    assert model.calls == 1

    monkeypatch.setattr(llm_service, "get_model", lambda settings=None: None)
    assert importer.ai_import_questions("1. Solve 2x = 8.") is None


# ---------------------------------------------------------------------------
# Word files
# ---------------------------------------------------------------------------
def _docx(build) -> bytes:
    import docx

    document = docx.Document()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_a_word_numbered_list_keeps_its_numbers():
    def build(document):
        document.add_paragraph("Algebra worksheet")
        for text in ("Solve 2x + 3 = 11. [2]", "Solve 5 - x = 2. (3 marks)", "Expand 2(x + 3)."):
            document.add_paragraph(text, style="List Number")
        table = document.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "x"
        table.rows[0].cells[1].text = "y"

    extraction = extract_text("worksheet.docx", _docx(build))

    assert extraction.success, extraction.message
    assert "1. Solve 2x + 3 = 11. [2]" in extraction.text
    assert "3. Expand 2(x + 3)." in extraction.text
    assert "x | y" in extraction.text
    result = importer.import_questions(extraction.text)
    assert [q.max_marks for q in result.questions] == [2, 3, 1]


def test_a_file_named_docx_must_be_a_word_document():
    ok, message = validate_upload("paper.docx", b"%PDF-1.7 not a word file")
    assert not ok and "not a Word document" in message
    ok, message = validate_upload("paper.docx", b"PK\x03\x04 not really a zip")
    assert not ok and "not a Word document" in message
    empty = _docx(lambda document: None)
    assert not extract_text("empty.docx", empty).success


# ---------------------------------------------------------------------------
# The panel puts the questions in the table
# ---------------------------------------------------------------------------
PAPER = "1. Solve 2x + 3 = 11. [2]\n2. Solve 5 - x = 2.\nAnswers\n1. x = 4\n2. x = 3"


def test_my_questions_imports_a_paper_into_the_table():
    at = _app_as("student")
    at.switch_page("pages/my_questions.py")
    at.session_state["mq_import_text"] = PAPER
    at.session_state["mq_import_filename"] = "Linear_equations_sheet.pdf"
    at.run()
    assert not at.exception, at.exception

    _button(at, "Put these 2 questions in the table").click().run()

    assert not at.exception, at.exception
    rows = at.session_state["my_questions_rows"]
    assert isinstance(rows, pd.DataFrame)
    assert list(rows["question_text"]) == ["Solve 2x + 3 = 11.", "Solve 5 - x = 2."]
    assert list(rows["model_answer"]) == ["x = 4", "x = 3"]
    assert list(rows["max_marks"]) == [2.0, 1.0]
    assert at.text_input(key="mq_title").value == "Linear equations sheet"
    assert any("Put 2 questions in the table" in s.value for s in at.success)


def test_create_assessment_imports_a_paper_into_the_table():
    at = _app_as("teacher")
    at.switch_page("pages/create_assessment.py")
    at.session_state["ca_import_text"] = PAPER
    at.run()
    assert not at.exception, at.exception
    assert "Put these 2 questions in the table" in _labels(at)

    _button(at, "Put these 2 questions in the table").click().run()

    assert not at.exception, at.exception
    rows = at.session_state["create_assessment_rows"]
    assert list(rows.columns) == ["question_text", "model_answer", "marking_criteria", "max_marks"]
    assert len(rows) == 2
