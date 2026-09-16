"""Split one block of extracted text into per-question answers.

Text pulled from a PDF or a .txt file arrives as a single block. Grading every
question against all of it lets an answer to Q3 earn marks on Q1, so this
module looks for the markers students actually write - "1.", "1)", "(1)",
"Q1", "Question 1", "Answer 1", "1(a)", or "(a)" / "b)" on their own - and cuts
the text at them.

It is deliberately cautious. A split is only reported as *confident* when the
markers read as a clean, in-order run that fits the assessment. Anything odd -
numbers out of order, a question number the assessment does not have, numbered
working steps that restart at 1, too few markers to trust - and the caller is
told to fall back to grading the whole block, with the reason in plain words.

Pure functions, no Streamlit, so the rules are unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from models import Question

# "Q1", "Q.1", "Question 1", "Answer 1", "Ans 1", optionally "1a" / "1(a)",
# at the start of a line. The separator is optional here.
_STRONG_LINE = re.compile(
    r"^[ \t]*(?:(?:Q|Question)[ \t]*\.?[ \t]*(\d{1,2})(?:[ \t]*\(([a-z])\)|([a-z])(?![a-z]))?[ \t]*[.):\-]?"
    r"|(?:Ans|Answer)[ \t]*\.?[ \t]*(\d{1,2})(?:[ \t]*\(([a-z])\)|([a-z])(?![a-z]))?[ \t]*[.):\-])(?=\s|$)",
    re.IGNORECASE | re.MULTILINE,
)
# The same mid-line, e.g. when a PDF has run two answers together. A separator
# is required so prose such as "as in question 2 we saw" is not a marker.
_STRONG_INLINE = re.compile(
    r"(?<=[\s.;])(?:Q|Question)[ \t]*\.?[ \t]*(\d{1,2})"
    r"(?:[ \t]*\(?([a-z])\))?[ \t]*[.):\-](?=\s)",
    re.IGNORECASE,
)
# "1.", "1)", "1:", "(1)", "1(a)", "1a)" at the start of a line. The lookahead
# keeps decimals such as "1.5 x 4" from counting.
_NUMERIC_LINE = re.compile(
    r"^[ \t]*(?:\((\d{1,2})\)|(\d{1,2})(?:[ \t]*\(([a-z])\)|([a-z])[.)]|[.):]))(?=\s|$)",
    re.IGNORECASE | re.MULTILINE,
)
# "(a)", "a)", "a." at the start of a line.
_LETTER_LINE = re.compile(r"^[ \t]*(?:\(([a-h])\)|([a-h])[.)])(?=\s)", re.MULTILINE)

FALLBACK_SUFFIX = (
    " Every question will be graded against the whole text, as before. You can "
    "add markers such as 'Q1', 'Q2' to the text above to split it."
)


@dataclass
class _Marker:
    start: int
    end: int
    number: int
    sub: Optional[str] = None


@dataclass
class AnswerSplit:
    """Outcome of a split attempt. `answers` is only meaningful when confident."""

    confident: bool
    message: str
    answers: Dict[str, str] = field(default_factory=dict)
    preamble: str = ""
    detected_numbers: List[int] = field(default_factory=list)

    @property
    def missing_count(self) -> int:
        return sum(1 for text in self.answers.values() if not text.strip())


def _strong_markers(text: str) -> List[_Marker]:
    found: Dict[int, _Marker] = {}
    for pattern in (_STRONG_LINE, _STRONG_INLINE):
        for match in pattern.finditer(text):
            # Skip leading whitespace so marker positions from both patterns agree.
            start = match.start() + (len(match.group(0)) - len(match.group(0).lstrip()))
            if start in found:
                continue
            groups = [g for g in match.groups()]
            number = next(g for g in groups if g and g.isdigit())
            sub = next((g for g in groups if g and g.isalpha()), None)
            found[start] = _Marker(start, match.end(), int(number), sub.lower() if sub else None)
    return [found[key] for key in sorted(found)]


def _numeric_markers(text: str) -> List[_Marker]:
    markers = []
    for match in _NUMERIC_LINE.finditer(text):
        number = match.group(1) or match.group(2)
        sub = match.group(3) or match.group(4)
        markers.append(_Marker(match.start(), match.end(), int(number),
                               sub.lower() if sub else None))
    return markers


def _letter_markers(text: str) -> List[_Marker]:
    return [
        _Marker(m.start(), m.end(), ord((m.group(1) or m.group(2)).lower()) - ord("a") + 1)
        for m in _LETTER_LINE.finditer(text)
    ]


def _segments(text: str, markers: Sequence[_Marker]) -> Tuple[str, List[Tuple[int, str]]]:
    preamble = text[: markers[0].start].strip() if markers else text.strip()
    parts = []
    for index, marker in enumerate(markers):
        stop = markers[index + 1].start if index + 1 < len(markers) else len(text)
        parts.append((marker.number, text[marker.end:stop].strip()))
    return preamble, parts


def _not_confident(reason: str, numbers: Sequence[int] = ()) -> AnswerSplit:
    return AnswerSplit(
        confident=False,
        message=reason + FALLBACK_SUFFIX,
        detected_numbers=list(numbers),
    )


def split_answers(text: str, questions: Sequence[Question]) -> AnswerSplit:
    """Split `text` into one answer per question in `questions` (in order).

    Question numbers in the text are positions in `questions`, 1-based.
    """
    text = (text or "").replace("\r\n", "\n")
    total = len(questions)
    if total == 0 or not text.strip():
        return _not_confident("There is no text or no questions to split.")

    if total == 1:
        markers = _strong_markers(text) or _numeric_markers(text)
        body = text
        if markers and markers[0].number == 1 and all(m.number == 1 for m in markers):
            _, parts = _segments(text, markers[:1])
            body = text[: markers[0].start] + parts[0][1]
        return AnswerSplit(
            confident=True,
            message="This assessment has one question, so all of the text is its answer.",
            answers={questions[0].id: body.strip()},
            detected_numbers=[1],
        )

    markers = _strong_markers(text)
    kind = "question"
    if not markers:
        markers = _numeric_markers(text)
    if not markers:
        markers = _letter_markers(text)
        kind = "letter"
    if not markers:
        return _not_confident("No question markers (such as 'Q1' or '1.') were found in the text.")

    # A sub-part of the question already open ("1(b)" after "1(a)") stays inside it.
    starts: List[_Marker] = []
    for marker in markers:
        if starts and marker.sub and marker.number == starts[-1].number:
            continue
        starts.append(marker)
    numbers = [m.number for m in starts]

    out_of_range = sorted({n for n in numbers if n < 1 or n > total})
    if out_of_range:
        first = out_of_range[0]
        named = f"part ({chr(96 + first)})" if kind == "letter" else f"question {first}"
        return _not_confident(
            f"The text mentions {named}, but this assessment only has {total} questions.",
            numbers,
        )
    if any(later <= earlier for earlier, later in zip(numbers, numbers[1:])):
        return _not_confident(
            "The question numbers in the text repeat or go out of order "
            f"({', '.join(str(n) for n in numbers)}) - they may be numbered working "
            "steps rather than questions.",
            numbers,
        )
    if kind == "letter" and len(numbers) != total:
        # Lettered parts are only read as whole questions when there is exactly
        # one per question. Otherwise "(a)" and "(b)" are more likely parts of a
        # single answer than answers to Q1 and Q2.
        return _not_confident(
            f"The text is lettered (a), (b), ... with {len(numbers)} part(s), but this "
            f"assessment has {total} questions, so the letters cannot be matched to "
            "questions safely.",
            numbers,
        )
    needed = max(2, (total + 1) // 2)
    if len(numbers) < needed:
        return _not_confident(
            f"Only {len(numbers)} question marker(s) were found for {total} questions, "
            "which is too few to split reliably.",
            numbers,
        )

    preamble, parts = _segments(text, starts)
    by_number = dict(parts)
    answers = {q.id: by_number.get(i, "") for i, q in enumerate(questions, start=1)}
    missing = [i for i in range(1, total + 1) if not by_number.get(i, "").strip()]

    message = f"Split the text into answers for {total - len(missing)} of {total} questions"
    if kind == "letter":
        message += " (parts (a), (b), ... read as questions 1, 2, ... in order)"
    message += "."
    if missing:
        message += (
            " No answer was found for "
            + ", ".join(f"Q{n}" for n in missing)
            + " - it will be graded as blank unless you add one below."
        )
    if preamble:
        message += " Text before the first marker is not given to any question."
    return AnswerSplit(
        confident=True,
        message=message,
        answers=answers,
        preamble=preamble,
        detected_numbers=numbers,
    )
