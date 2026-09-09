"""Guidance for a question a student has not attempted yet.

WHY THIS EXISTS
  A student can now bring their own questions, and they usually arrive without
  a mark scheme. `grading_service` refuses to mark those - correctly, since it
  would be inventing a score. This module is the useful thing to do instead:
  say how to approach the question.

THE ONE RULE
  Guidance is built from the question text and nothing else. `guidance_for` is
  only ever handed a `Question`, and it reads `question_text` alone - never
  `model_answer`, never `marking_criteria`. That is what makes it safe to show
  a student for a question they have not attempted: there is no answer in this
  module to leak.

  Concretely: hints say "substitute your values into the formula", never "put
  15 into the formula". The formula is method; the number is the answer.

HOW IT WORKS
  Deterministic pattern matching on the question text, in the same spirit as
  the mock grader: transparent, free, and identical every time. `_SHAPES` is
  an ordered list of (matcher, template) pairs - the first match wins, so more
  specific shapes are listed before broader ones.

  In Phase 2 this is where an LLM goes. Keep `guidance_for`'s signature and its
  `Guidance` return type and nothing else has to change - and keep the rule
  above, which for an LLM means never putting the model answer in the prompt.

TRY CHANGING THIS
  Add a shape for simultaneous equations. Write the matcher, write the
  template, and see which test catches you if a step gives the answer away.
"""

from __future__ import annotations

import re
from typing import Callable, List, Sequence, Tuple

from models import ErrorType, Question, Subject
from models.guidance import GENERIC_SHAPE, Guidance

HINT_ENGINE_NAME = "Rule-based guidance v1 (no LLM)"


class _Template:
    """The advice for one recognised kind of question."""

    def __init__(
        self,
        shape: str,
        approach: Sequence[str],
        include: Sequence[str],
        watch_out_for: Sequence[str],
    ) -> None:
        self.shape = shape
        self.approach = list(approach)
        self.include = list(include)
        self.watch_out_for = list(watch_out_for)


def _has(*words: str) -> Callable[[str], bool]:
    """Matcher: the question mentions any of these words."""
    patterns = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in words]
    return lambda text: any(p.search(text) for p in patterns)


def _solves_for_a_letter(text: str) -> bool:
    """Matcher: "solve for x", or an equation with a letter and an equals sign."""
    if re.search(r"\bsolve\b", text, re.IGNORECASE):
        return True
    return bool(re.search(r"[a-z]\s*[-+*/]?\s*\d*\s*=", text))


# ---------------------------------------------------------------------------
# The shapes, most specific first
# ---------------------------------------------------------------------------
_LINEAR_EQUATION = _Template(
    shape="equation to solve",
    approach=[
        "Write the equation out on its own line so you can see it clearly.",
        "Undo whatever is added to or subtracted from the letter, doing the "
        "same thing to both sides.",
        "Undo whatever the letter is multiplied or divided by, again on both sides.",
        "Put your value back into the original equation and check the two sides "
        "match. This is how you mark your own work.",
    ],
    include=[
        "Every line of your working, not just the final line.",
        "The value of the letter, written as an equation (for example 'x = ...').",
    ],
    watch_out_for=[
        "Doing something to one side and forgetting the other.",
        "Losing a minus sign when you move a term across.",
    ],
)

_WORD_EQUATION = _Template(
    shape="word problem to turn into an equation",
    approach=[
        "Name the unknown thing with a letter and write down what it stands for.",
        "Rewrite the sentence as an equation, one operation at a time, in the "
        "order the words give them.",
        "Solve the equation you have written.",
        "Read the question again and check you have answered what it actually "
        "asked for.",
    ],
    include=[
        "A sentence saying what your letter stands for.",
        "The equation you formed, before you solve it — this is worth marks on "
        "its own.",
        "Your working and the final value.",
    ],
    watch_out_for=[
        "Doing the operations in the wrong order.",
        "Answering with the letter's value when the question asked for something "
        "you still have to work out from it.",
    ],
)

_AREA_PERIMETER = _Template(
    shape="area, perimeter or volume",
    approach=[
        "Sketch the shape and label every measurement the question gives you.",
        "Decide which quantity is being asked for, then write down the formula "
        "for it before you put any numbers in.",
        "Substitute your measurements into the formula.",
        "Work it out, and write the unit that belongs to that quantity.",
    ],
    include=[
        "The formula you used, written out.",
        "Your substitution and working.",
        "The unit — squared for an area, cubed for a volume.",
    ],
    watch_out_for=[
        "Mixing units in one calculation (centimetres with metres).",
        "Giving an area a plain unit instead of a squared one.",
        "Using the slanted side where the question wants the perpendicular height.",
    ],
)

_RATIO = _Template(
    shape="ratio and proportion",
    approach=[
        "Add the parts of the ratio together to find how many parts there are "
        "in total.",
        "Divide the total amount by that number of parts to find what one part "
        "is worth.",
        "Multiply one part by each number in the ratio to get each share.",
        "Add your shares back together and check they come to the original total.",
    ],
    include=[
        "The total number of parts.",
        "The value of one part.",
        "Every share the question asked for, in the right order.",
    ],
    watch_out_for=[
        "Dividing by one of the ratio numbers instead of by the total parts.",
        "Giving the shares in the wrong order.",
    ],
)

_PERCENTAGE = _Template(
    shape="percentage",
    approach=[
        "Decide what the percentage is *of* — that amount is your starting whole.",
        "Write the percentage as a fraction or a decimal.",
        "Multiply the whole by it to find the part.",
        "Check whether the question wants that part on its own, or the whole "
        "after it has been added on or taken off.",
    ],
    include=[
        "What you took the percentage of.",
        "Your working.",
        "The final amount, with its unit or currency.",
    ],
    watch_out_for=[
        "Giving the size of the increase when the question asked for the new total.",
        "Taking the percentage of the wrong amount.",
    ],
)

_AVERAGES = _Template(
    shape="averages and spread",
    approach=[
        "Write out the list of values.",
        "Check which average is being asked for — they are worked out "
        "differently, so name it before you start.",
        "For the mean, total the values and divide by how many there are. For "
        "the median, put them in order first. For the range, use the largest "
        "and the smallest.",
        "Sense-check your result: an average has to sit inside the range of the "
        "data.",
    ],
    include=[
        "Which average you found.",
        "Your working, including the ordered list if you needed one.",
        "The value, with a unit if the data has one.",
    ],
    watch_out_for=[
        "Forgetting to order the values before taking a median.",
        "Dividing by the wrong count.",
    ],
)

_PROBABILITY = _Template(
    shape="probability",
    approach=[
        "Write down how many outcomes there are altogether.",
        "Write down how many of those count as the event you want.",
        "Put the second over the first as a fraction.",
        "Check your answer sits between 0 and 1.",
    ],
    include=[
        "The number of favourable outcomes and the total.",
        "The probability as a fraction, decimal or percentage — whichever the "
        "question asks for.",
    ],
    watch_out_for=[
        "Counting outcomes that the question has already ruled out.",
        "Giving a probability above 1.",
    ],
)

_EXPLAIN = _Template(
    shape="explain or describe",
    approach=[
        "Underline the command word — explain, describe, compare, evaluate — "
        "because it decides the shape of the answer.",
        "Note how many marks it carries. That is roughly how many separate "
        "points are wanted.",
        "Make each point, then say *why* it matters. A point without a reason "
        "usually scores half.",
        "Read it back against the question and cut anything that does not answer it.",
    ],
    include=[
        "One clear point per mark available.",
        "A reason attached to each point.",
        "The subject's own vocabulary rather than everyday wording.",
        "Your own example or reasoning — the points above are a starting frame, "
        "not the whole answer.",
    ],
    watch_out_for=[
        "Describing when the question asked you to explain.",
        "Writing one long point instead of several separate ones.",
    ],
)

_GENERIC = _Template(
    shape=GENERIC_SHAPE,
    approach=[
        "Read the question twice and underline exactly what it asks you to find.",
        "Write down everything it gives you, and what it is asking for.",
        "Decide which method connects the two, and write it down before you "
        "start calculating.",
        "Work through it, then check your result against what the question asked.",
    ],
    include=[
        "Your working, line by line — marks are given for the method.",
        "A clear final answer, with its unit if it has one.",
    ],
    watch_out_for=[
        "Answering a different question from the one asked.",
        "Giving a bare answer with no working behind it.",
    ],
)

# Order matters: the first matcher that fires wins, so the narrow shapes come
# before the broad ones. "Explain" sits last of the specific shapes so that a
# maths question saying "explain your working" is still read as maths.
_SHAPES: List[Tuple[Callable[[str], bool], _Template]] = [
    (_has("ratio", "proportion", "share"), _RATIO),
    (_has("percent", "percentage", "discount", "interest", "vat"), _PERCENTAGE),
    (_has("probability", "chance", "likelihood"), _PROBABILITY),
    (_has("mean", "median", "mode", "average", "range"), _AVERAGES),
    (
        _has(
            "area", "perimeter", "volume", "rectangle", "triangle", "circle",
            "circumference", "cuboid", "radius", "diameter",
        ),
        _AREA_PERIMETER,
    ),
    (_has("form an equation", "forms an equation"), _WORD_EQUATION),
    (_solves_for_a_letter, _LINEAR_EQUATION),
    (_has("explain", "describe", "compare", "evaluate", "discuss", "suggest"), _EXPLAIN),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def guidance_for(question: Question, subject: Subject = Subject.MATHEMATICS) -> Guidance:
    """How to approach one question, without answering it.

    Only `question.question_text` is read. The model answer and the marking
    criteria are deliberately not consulted, so nothing this returns can give
    the answer away - see the module docstring.
    """
    text = question.question_text or ""

    # Outside mathematics, a written-answer question is the common case, so a
    # non-maths question that matches nothing specific gets the explain frame
    # rather than the calculation frame.
    template = _match(text)
    if template is _GENERIC and subject is not Subject.MATHEMATICS:
        template = _EXPLAIN

    return Guidance(
        question_id=question.id,
        question_text=text,
        shape=template.shape,
        approach=list(template.approach),
        include=list(template.include),
        watch_out_for=list(template.watch_out_for),
    )


def guidance_for_questions(
    questions: Sequence[Question],
    subject: Subject = Subject.MATHEMATICS,
) -> List[Guidance]:
    """Guidance for a whole set, in the order the questions are given."""
    return [guidance_for(q, subject) for q in questions]


def _match(text: str) -> _Template:
    for matches, template in _SHAPES:
        if matches(text):
            return template
    return _GENERIC


# ---------------------------------------------------------------------------
# The hint ladder
#
# A student who has missed a question three times needs something more pointed
# than the one who has just missed it once - but never the answer. So hints
# escalate in *specificity*, not in how much of the answer they give away.
#
# Straight from the brief:
#   maths      - "just providing them with the formula should be enough as a
#                 hint. Or if they need more, tell them where to put the
#                 numbers as well" - so: name the method, then where values go,
#                 then how to check. The values themselves are never given.
#   everything - "giving a few points to include in your answer, and you
#     else       include your own as well".
# ---------------------------------------------------------------------------
MAX_HINT_LEVEL = 3

_MATHS_LADDER = [
    "Write down the rule or formula this kind of question uses, before you put "
    "a single number into it.",
    "Now place each value the question gives you into the spot it belongs in "
    "that formula. Get everything in position before you calculate anything.",
    "Work the substituted line through one operation at a time, writing every "
    "line out, then check the result answers what was actually asked - "
    "including its unit.",
]

_WRITTEN_LADDER = [
    "List the points you would make - roughly one per mark available - before "
    "you write anything out in full.",
    "Give each point its reason. A point with no reason behind it usually "
    "takes half the mark.",
    "Add an example or a piece of reasoning of your own, in the subject's own "
    "vocabulary, then cut anything that does not answer the question.",
]

ERROR_TIPS = {
    ErrorType.ARITHMETIC_ERROR: (
        "Re-do each calculation line by line and compare the two attempts."
    ),
    ErrorType.INCORRECT_METHOD: (
        "Ask yourself which method this type of question calls for before you start."
    ),
    ErrorType.CONCEPTUAL_ERROR: (
        "Go back to the idea being tested and put it in your own words first."
    ),
    ErrorType.INCOMPLETE_ANSWER: (
        "Re-read the question and check every part of it has been answered."
    ),
    ErrorType.MISSING_WORKING: (
        "Write out your working - marks are given for the method, not just the answer."
    ),
    ErrorType.UNIT_ERROR: (
        "Check what quantity you have found and finish with its unit."
    ),
}


def hint_level_for(attempts_used: int) -> int:
    """Which rung of the ladder a student has earned.

    Level 1 after the first miss, rising with each further attempt and capped
    so it cannot climb past the last rung.
    """
    return max(1, min(MAX_HINT_LEVEL, attempts_used))


def escalating_pointers(
    question: Question,
    error_types: Sequence[ErrorType] = (),
    subject: Subject = Subject.MATHEMATICS,
    level: int = 1,
) -> List[str]:
    """Pointers for one missed question, sharpened by how many goes have gone.

    Like `guidance_for`, this reads the question text only. Nothing here can
    contain a value from the model answer because it never sees one.
    """
    level = max(1, min(MAX_HINT_LEVEL, int(level)))
    pointers: List[str] = []

    template = _match(question.question_text or "")
    is_written = template is _EXPLAIN or (
        template is _GENERIC and subject is not Subject.MATHEMATICS
    )

    # 1. Where in the method to look. The step named climbs with the level, so
    #    a repeated miss moves the student along rather than repeating itself.
    if template is not _GENERIC:
        article = "an" if template.shape[0] in "aeiou" else "a"
        pointers.append(f"This is {article} {template.shape} question.")
    step_index = min(level, len(template.approach)) - 1
    pointers.append(template.approach[step_index])

    # 2. The subject's own framing of that rung.
    ladder = _WRITTEN_LADDER if is_written else _MATHS_LADDER
    pointers.append(ladder[level - 1])

    # 3. Anything the grader actually spotted.
    for error_type in error_types:
        tip = ERROR_TIPS.get(error_type)
        if tip:
            pointers.append(tip)

    # 4. On the last rung, name the marks most often thrown away here.
    if level >= MAX_HINT_LEVEL and template.watch_out_for:
        pointers.append(f"Commonly lost here: {template.watch_out_for[0]}")

    return list(dict.fromkeys(pointers))
