"""Turn a question paper into question rows.

WHY THIS EXISTS
  Someone with a worksheet, a past paper or a Google Doc already has the
  questions. Typing thirty of them into a table one cell at a time is the wrong
  job. This reads the text `document_service` pulled out of the file and cuts
  it into questions, which then land in the usual table to be checked and
  saved. Nothing is saved here.

WHAT IT READS
  * Question starts: "1.", "1)", "(1)", "1", "Q1" or "Question 1" at the start
    of a line, taken in order (1, 2, 3...). A number that breaks the run - a
    numbered working step, a "2." inside question 7 - stays as text.
  * Sub-parts such as "(a)", "b)" or "1(b)" stay inside their question.
  * Marks: an allocation at the end of a line - "[3]", "[3 marks]",
    "(3 marks)", "3 marks" - or "[Total: 6]". One per part adds up.
  * Answers: an "Answer: ..." line inside a question, or an answer section
    after the questions (a line saying "Answers", "Answer key", "Mark scheme"
    or "Solutions"), matched to the questions by number.
  With no numbering at all, each paragraph (or each line) becomes a question,
  and the message says so.

WHAT IT NEVER DOES
  Invent anything. A question with no marks in the file starts at 1 mark; one
  with no answer in the file has none. The optional AI reading
  (`ai_import_questions`) is held to the same rule: every question and answer
  it returns must be found in the file's own text, or it is dropped.

Pure functions, no Streamlit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_MARKS = 1.0
MAX_QUESTIONS = 100
# Sent to the AI at most; a longer file is read in part, and the page says so.
AI_TEXT_LIMIT = 30_000
AI_PROMPT_VERSION = "question-import-1"

METHOD_NUMBERS = "numbers"
METHOD_PARAGRAPHS = "paragraphs"
METHOD_LINES = "lines"
METHOD_AI = "ai"
METHOD_NONE = "none"


@dataclass
class ImportedQuestion:
    question_text: str
    model_answer: str = ""
    max_marks: float = DEFAULT_MARKS
    marks_found: bool = False


@dataclass
class QuestionImport:
    """What was found in a file, ready for the question table."""

    questions: List[ImportedQuestion] = field(default_factory=list)
    message: str = ""
    method: str = METHOD_NONE

    @property
    def found(self) -> bool:
        return bool(self.questions)

    @property
    def marks_found_count(self) -> int:
        return sum(1 for q in self.questions if q.marks_found)

    @property
    def answers_found_count(self) -> int:
        return sum(1 for q in self.questions if q.model_answer)

    def editor_rows(self) -> List[Dict[str, Any]]:
        return [
            {
                "question_text": q.question_text,
                "model_answer": q.model_answer,
                "marking_criteria": "",
                "max_marks": q.max_marks,
            }
            for q in self.questions
        ]


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
def _start_pattern(words: str, bare: bool) -> re.Pattern:
    """A question number at the start of a line.

    Always: "Q1", "Question 1", "(1)", "1.", "1)", "1:", "1(a)", "1a)". With
    `bare`, also a number followed only by a space ("1 Work out..."), as some
    printed papers have it. That is only tried when nothing better is found,
    because a line of data ("3 5 7 9") reads the same way. The lookahead keeps
    decimals ("1.5 m") and times ("2:30") from counting.
    """
    end = "[.):]?" if bare else "[.):]"
    return re.compile(
        r"^[ \t]*(?:"
        r"(?:" + words + r")[ \t]*\.?[ \t]*(?P<q>\d{1,3})"
        r"(?P<qsub>[ \t]*\([a-z]\)|[a-z](?![a-z]))?[ \t]*[.):\-]?"
        r"|\((?P<p>\d{1,3})\)"
        r"|(?P<n>\d{1,3})(?:(?P<nsub>[ \t]*\([a-z]\)[.):]?|[a-z][.)])|" + end + r")"
        r")(?=[ \t]|$)",
        re.IGNORECASE | re.MULTILINE,
    )


# An answer section may also say "Answer 1" / "Ans 1".
_QUESTION_START = _start_pattern("Q|Question", bare=False)
_QUESTION_START_BARE = _start_pattern("Q|Question", bare=True)
_ANSWER_START = _start_pattern("Q|Question|Ans|Answer", bare=False)
_ANSWER_START_BARE = _start_pattern("Q|Question|Ans|Answer", bare=True)
_ANSWER_SECTION = re.compile(
    r"^[ \t]*(?:answers?|answer key|answer sheet|mark ?scheme|marking scheme|"
    r"solutions?|worked solutions|memo(?:randum)?)[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_ANSWER_LINE = re.compile(r"^[ \t]*(?:answer|ans|solution)[ \t]*[:\-][ \t]*", re.IGNORECASE | re.MULTILINE)
_MARK_VALUE = r"(\d{1,3}(?:\.5)?)"
_MARKS_AT_LINE_END = re.compile(
    r"(?:\[[ \t]*" + _MARK_VALUE + r"[ \t]*(?:marks?)?[ \t]*\]"
    r"|\([ \t]*" + _MARK_VALUE + r"[ \t]*marks?[ \t]*\)"
    r"|\b" + _MARK_VALUE + r"[ \t]*marks?)[ \t]*\.?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_TOTAL_MARKS = re.compile(r"\[[ \t]*total[ \t]*:?[ \t]*" + _MARK_VALUE + r"[ \t]*(?:marks?)?[ \t]*\]", re.IGNORECASE)
# Dotted or ruled answer lines on a printed paper: "x = .............". A
# sentence's own full stop before them is kept.
_LEADERS = re.compile(r"\.{4,}|(?:\.[ \t]){4,}|_{3,}|…{2,}")
# Page furniture a PDF repeats on every page.
_FURNITURE = re.compile(
    r"^[ \t]*(?:page[ \t]+\d+(?:[ \t]+of[ \t]+\d+)?|©.*|\(c\)[ \t]+ucles.*|\[?turn over\]?|"
    r"blank page|this document (?:consists|has) of .*|\*+)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Reading a file's text
# ---------------------------------------------------------------------------
def import_questions(text: str) -> QuestionImport:
    """Find the questions in a question paper's text."""
    text = _clean(text)
    if not text:
        return QuestionImport(message="The file has no text to read questions from.")

    questions_part, answers_part = _split_off_answers(text)
    segments = _numbered_segments(questions_part, _QUESTION_START) or _numbered_segments(
        questions_part, _QUESTION_START_BARE
    )
    method = METHOD_NUMBERS
    if not segments:
        segments, method = _unnumbered_segments(questions_part)
    if not segments:
        return QuestionImport(message="No questions could be found in the file's text.")

    questions = [_question_from(segment) for segment in segments]
    questions = [q for q in questions if q.question_text]

    matched = 0
    if answers_part and method == METHOD_NUMBERS:
        answers = dict(
            _numbered_segments(answers_part, _ANSWER_START, numbered=True)
            or _numbered_segments(answers_part, _ANSWER_START_BARE, numbered=True)
        )
        for number, question in enumerate(questions, start=1):
            answer = _tidy(answers.get(number, ""))
            if answer and not question.model_answer:
                question.model_answer = _strip_marks(answer)[0]
                matched += 1

    trimmed = len(questions) > MAX_QUESTIONS
    questions = questions[:MAX_QUESTIONS]
    result = QuestionImport(questions=questions, method=method)
    result.message = _summary(result, trimmed, answers_part, matched)
    return result


def _clean(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = _FURNITURE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _split_off_answers(text: str) -> Tuple[str, str]:
    """Questions first, then (if the file has one) the answer section."""
    heading = _ANSWER_SECTION.search(text)
    if heading is None or heading.start() == 0:
        return text, ""
    return text[: heading.start()], text[heading.end():]


def _numbered_segments(text: str, pattern: re.Pattern, numbered: bool = False):
    """Cut `text` at the run 1, 2, 3... of numbers that start lines.

    Returns the text after each number (or (number, text) pairs when
    `numbered`). Only a number that continues the run counts, so a stray "4)"
    inside question 2 is left as text. A list that restarts at 1 inside a
    question (numbered working steps) is followed too, so its "2." is not
    taken for question 2. A run of one is not a numbered paper.

    "1(a)" starts question 1 with its part (a), which stays in the text; a
    later "1(b)" is just the next part.
    """
    starts: List[Tuple[int, int, int]] = []
    expected = 1
    inner_next: Optional[int] = None
    for match in pattern.finditer(text):
        number = int(match.group("q") or match.group("p") or match.group("n"))
        sub = match.group("qsub") or match.group("nsub")
        if inner_next is not None and number == inner_next and not sub:
            inner_next += 1
            continue
        if number == expected:
            body = match.start("qsub" if match.group("qsub") else "nsub") if sub else match.end()
            starts.append((match.start(), body, number))
            expected += 1
            inner_next = None
        elif number == 1 and starts and not sub:
            inner_next = 2
    if len(starts) < 2 and not numbered:
        return []
    out = []
    for index, (_, end, number) in enumerate(starts):
        stop = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        body = text[end:stop].strip()
        out.append((number, body) if numbered else body)
    return out


def _unnumbered_segments(text: str) -> Tuple[List[str], str]:
    paragraphs = [p.strip() for p in re.split(r"\n[ \t]*\n", text) if p.strip()]
    if len(paragraphs) >= 2:
        return paragraphs, METHOD_PARAGRAPHS
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) >= 2:
        return lines, METHOD_LINES
    return ([text] if text else []), METHOD_PARAGRAPHS


def _question_from(segment: str) -> ImportedQuestion:
    answer = ""
    answer_line = _ANSWER_LINE.search(segment)
    if answer_line is not None:
        answer = segment[answer_line.end():]
        segment = segment[: answer_line.start()]
    text, marks = _strip_marks(_tidy(segment))
    answer, answer_marks = _strip_marks(_tidy(answer))
    if marks is None:
        marks = answer_marks
    found = marks is not None and 0 < marks <= 100
    return ImportedQuestion(
        question_text=text,
        model_answer=answer,
        max_marks=marks if found else DEFAULT_MARKS,
        marks_found=found,
    )


def _tidy(text: str) -> str:
    lines = []
    for raw in (text or "").split("\n"):
        line = re.sub(r"[ \t]{2,}", " ", _LEADERS.sub(" ", raw)).strip()
        # The "x =" or "Answer" a dotted answer line leaves behind.
        stub = re.fullmatch(r"[A-Za-z]{0,3}[ \t]*=?|answer:?", line, re.IGNORECASE)
        if line and not (stub and _LEADERS.search(raw)):
            lines.append(line)
    return "\n".join(lines).strip()


def _strip_marks(text: str) -> Tuple[str, Optional[float]]:
    """The question's total marks, and its text without a lone trailing total.

    "[2]" after part (a) and "[3]" after part (b) make a 5-mark question; a
    "[Total: 5]" wins over the parts. The allocations stay in a multi-part
    question's text, where they say which part is worth what, but a single
    allocation at the very end is the whole question's and is taken off.
    """
    if not text:
        return "", None
    total = _TOTAL_MARKS.search(text)
    tokens = list(_MARKS_AT_LINE_END.finditer(text))
    values = [float(next(g for g in m.groups() if g)) for m in tokens]
    if total is not None:
        marks: Optional[float] = float(total.group(1))
        text = (text[: total.start()] + text[total.end():]).strip()
    else:
        marks = sum(values) if values else None
    if len(tokens) == 1 and total is None and text[tokens[0].end():].strip() == "":
        text = text[: tokens[0].start()].rstrip(" \t:-")
    return text.strip(), marks


def _summary(result: QuestionImport, trimmed: bool, answers_part: str, matched: int) -> str:
    count = len(result.questions)
    noun = "question" if count == 1 else "questions"
    if result.method == METHOD_NUMBERS:
        message = f"Found {count} numbered {noun}."
    elif result.method == METHOD_LINES:
        message = (
            f"No question numbers were found, so each of the {count} lines became a "
            "question. Delete any that are instructions or headings."
        )
    else:
        message = (
            f"No question numbers were found, so each of the {count} paragraphs became "
            "a question. Delete any that are instructions or headings."
        )
    marks = result.marks_found_count
    if marks == count:
        message += " Marks were read for every question."
    elif marks:
        message += f" Marks were read for {marks}; the rest start at 1 mark."
    else:
        message += " No marks were found, so each starts at 1 mark - change them in the table."
    if result.answers_found_count:
        message += f" Answers were found for {result.answers_found_count}."
    if answers_part and not matched:
        message += (
            " The answer section could not be matched to the questions by number, "
            "so add the answers in the table."
        )
    if trimmed:
        message += f" Only the first {MAX_QUESTIONS} are included."
    return message


# ---------------------------------------------------------------------------
# AI reading (optional)
# ---------------------------------------------------------------------------
_AI_SYSTEM = """You find the exam questions in text pulled out of a document (a
worksheet, past paper or question list). The text may be messy: broken lines,
page headers, two columns run together.

Rules:
- Copy each question's wording exactly as it appears in the text. Do not fix,
  reword, shorten, solve or add anything. Keep sub-parts such as (a) and (b)
  inside their question.
- Include an answer ONLY when the document itself gives it (an answer key, a
  mark scheme, or an "Answer:" line). Copy it exactly. Never work an answer out.
- "marks" is the mark allocation printed in the document for that question, or
  null when none is printed.
- Leave out instructions, headings, page numbers and copyright lines.

Reply with JSON only:
{"questions": [{"question": "...", "answer": "", "marks": null}]}"""


def ai_import_questions(text: str, model: Any = None) -> Optional[QuestionImport]:
    """Ask the AI to find the questions, keeping only what the file contains.

    Returns None when no AI is available or the call fails, so the caller can
    say so and keep the plain reading.
    """
    from services import llm_service

    source = _clean(text)
    if not source:
        return None
    model = model if model is not None else llm_service.get_model()
    if model is None:
        return None
    sent = source[:AI_TEXT_LIMIT]
    key = llm_service.cache_key(AI_PROMPT_VERSION, sent)
    data = llm_service.cache_get(key)
    if data is None:
        data = llm_service.ask_json(model, _AI_SYSTEM, sent)
        if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
            return None
        llm_service.cache_put(key, data)

    source_squashed = _squash(source)
    source_words = set(_words(source))
    printed_marks = {float(next(g for g in m.groups() if g)) for m in _MARKS_AT_LINE_END.finditer(source)}
    printed_marks |= {float(m.group(1)) for m in _TOTAL_MARKS.finditer(source)}

    questions: List[ImportedQuestion] = []
    dropped = 0
    for item in data["questions"][: MAX_QUESTIONS + 1]:
        if not isinstance(item, dict):
            continue
        wording = _tidy(str(item.get("question") or ""))
        if not _grounded_question(wording, source_squashed, source_words):
            dropped += 1
            continue
        answer = _tidy(str(item.get("answer") or ""))
        if answer and _squash(answer) not in source_squashed:
            answer = ""  # not in the file, so it was worked out: never use it
        wording, marks = _strip_marks(wording)
        if marks is None:
            marks = _as_marks(item.get("marks"), printed_marks)
        found = marks is not None and 0 < marks <= 100
        questions.append(
            ImportedQuestion(
                question_text=wording,
                model_answer=answer,
                max_marks=marks if found else DEFAULT_MARKS,
                marks_found=found,
            )
        )

    trimmed = len(questions) > MAX_QUESTIONS
    result = QuestionImport(questions=questions[:MAX_QUESTIONS], method=METHOD_AI)
    if not result.questions:
        result.message = "The AI did not find any questions it could match to the file's text."
        return result
    count = len(result.questions)
    result.message = (
        f"The AI found {count} question{'s' if count != 1 else ''}, each checked "
        "against the file's own text."
    )
    marks = result.marks_found_count
    if marks < count:
        result.message += (
            f" Marks were read for {marks}; the rest start at 1 mark."
            if marks
            else " No marks were found, so each starts at 1 mark."
        )
    if result.answers_found_count:
        result.message += f" Answers were found for {result.answers_found_count}."
    if dropped:
        result.message += (
            f" {dropped} suggestion{'s were' if dropped != 1 else ' was'} left out "
            "because the wording was not in the file."
        )
    if len(source) > AI_TEXT_LIMIT:
        result.message += " The file is long, so only its first part was read."
    if trimmed:
        result.message += f" Only the first {MAX_QUESTIONS} are included."
    return result


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _grounded_question(wording: str, source_squashed: str, source_words: set) -> bool:
    """Is this the file's own question, rather than something the AI wrote?"""
    if not wording:
        return False
    if _squash(wording) in source_squashed:
        return True
    words = _words(wording)
    if len(words) < 3:
        return False
    # PDFs hyphenate and break lines, so allow a little drift - but nearly
    # every word must be the file's.
    return sum(1 for w in words if w in source_words) / len(words) >= 0.9


def _as_marks(value: Any, printed: set) -> Optional[float]:
    try:
        marks = float(value)
    except (TypeError, ValueError):
        return None
    # Only a number the file actually prints as a mark allocation.
    return marks if marks in printed else None


def suggested_title(filename: str) -> str:
    """A set name from a file name: "algebra_worksheet-4.pdf" -> "Algebra worksheet 4"."""
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", filename or "").strip()
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s{2,}", " ", stem).strip()
    if not stem:
        return ""
    return (stem[0].upper() + stem[1:])[:80]


def summarise(questions: Sequence[ImportedQuestion]) -> str:
    """One line per question for a preview."""
    lines = []
    for number, question in enumerate(questions, start=1):
        first = question.question_text.split("\n", 1)[0]
        if len(first) > 90:
            first = first[:87].rstrip() + "..."
        marks = f"{question.max_marks:g} mark{'s' if question.max_marks != 1 else ''}"
        answer = " · answer included" if question.model_answer else ""
        lines.append(f"{number}. {first} ({marks}{answer})")
    return "\n".join(lines)
