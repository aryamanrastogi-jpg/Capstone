"""Template-based practice question generator (prototype).

Phase 1 uses deterministic templates with numbers derived from a stable seed,
so the same selections always produce the same questions. No AI is involved.
Phase 2 replaces `generate_practice_questions` with a real LLM call.

Each template builds its numbers *backwards from a chosen answer* rather than
picking them at random. A generator that emits "36x + 36 = 21" is worse than
useless to a Grade 7 class, so every question here resolves to a clean value.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from math import gcd
from typing import Callable, Dict, List, Sequence, Tuple

from models import ErrorType

GENERATOR_LABEL = (
    "Prototype template generator - deterministic, no AI. This will be replaced "
    "by a real AI service in a later phase."
)

DIFFICULTIES: List[str] = ["Foundation", "Core", "Extension"]

TOPICS: List[str] = [
    "Linear Equations",
    "Fractions and Decimals",
    "Ratio and Proportion",
    "Area and Perimeter",
    "Percentages",
    "Data Handling",
]

# (small, large) bounds for the numbers each difficulty is allowed to use.
_DIFFICULTY_RANGE: Dict[str, Tuple[int, int]] = {
    "Foundation": (2, 9),
    "Core": (3, 15),
    "Extension": (5, 25),
}

# What each error category should be drilled on.
_ERROR_PROMPTS: Dict[ErrorType, str] = {
    ErrorType.ARITHMETIC_ERROR: "Check each calculation twice and write the running total on every line.",
    ErrorType.INCORRECT_METHOD: "Before calculating, write one sentence naming the method you will use.",
    ErrorType.CONCEPTUAL_ERROR: "Start by explaining in your own words what the question is asking for.",
    ErrorType.INCOMPLETE_ANSWER: "Underline every part of the question and tick each one as you answer it.",
    ErrorType.MISSING_WORKING: "Write at least three lines of working, even if you can do it mentally.",
    ErrorType.UNIT_ERROR: "Finish every answer with the correct unit, and state why that unit applies.",
}


@dataclass
class PracticeQuestion:
    number: int
    topic: str
    difficulty: str
    error_focus: str
    question_text: str
    method_hint: str
    skill_focus: str


# --------------------------------------------------------------------------
# Template builders
#
# Each builder takes an RNG plus the difficulty bounds and returns
# (question, method hint, skill focus). Values are chosen so the answer is a
# whole number or a tidy fraction.
# --------------------------------------------------------------------------
Builder = Callable[[random.Random, int, int], Tuple[str, str, str]]


def _solve_ax_plus_b(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    a = rng.randint(2, max(3, high // 2))
    x = rng.randint(2, high)          # the answer, chosen first
    b = rng.randint(1, high)
    c = a * x + b                     # so the equation resolves exactly
    return (
        f"Solve for x: {a}x + {b} = {c}. Show every step of your working.",
        f"Subtract {b} from both sides to get {a}x = {a * x}, then divide by {a} to get x = {x}.",
        "Isolating the variable one operation at a time.",
    )


def _word_equation(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    a = rng.randint(2, max(3, high // 2))
    n = rng.randint(2, high)
    b = rng.randint(1, high)
    c = a * n + b
    return (
        f"A number is multiplied by {a} and then {b} is added. The result is {c}. "
        "Write an equation and solve it.",
        f"Let the number be n. Then {a}n + {b} = {c}, so {a}n = {a * n} and n = {n}.",
        "Translating a word problem into an equation.",
    )


def _add_fractions(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    b = rng.randint(2, 9)
    d = rng.randint(2, 9)
    a = rng.randint(1, b - 1) if b > 1 else 1
    c = rng.randint(1, d - 1) if d > 1 else 1
    numerator = a * d + c * b
    denominator = b * d
    divisor = gcd(numerator, denominator)
    return (
        f"Work out {a}/{b} + {c}/{d}. Give your answer in its simplest form.",
        f"Use a common denominator of {denominator}: {a * d}/{denominator} + "
        f"{c * b}/{denominator} = {numerator}/{denominator}, which simplifies to "
        f"{numerator // divisor}/{denominator // divisor}.",
        "Common denominators and simplifying.",
    )


def _fraction_to_percentage(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    b = rng.choice([2, 4, 5, 8, 10, 20, 25])
    a = rng.randint(1, b - 1)
    decimal = a / b
    return (
        f"Convert {a}/{b} to a decimal and then to a percentage. Show your method.",
        f"Divide {a} by {b} to get {decimal:g}, then multiply by 100 to get {decimal * 100:g}%.",
        "Moving between fractions, decimals and percentages.",
    )


def _share_in_ratio(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    a = rng.randint(1, 5)
    b = rng.randint(1, 5)
    part = rng.randint(2, max(3, high))
    total = (a + b) * part            # divides exactly by the number of parts
    return (
        f"Share {total} counters in the ratio {a} : {b}. Show your working.",
        f"There are {a + b} parts, so one part is {total} / {a + b} = {part}. "
        f"The shares are {a * part} and {b * part}.",
        "Dividing a quantity in a given ratio.",
    )


def _unitary_method(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    a = rng.randint(2, 9)
    unit_cost = rng.randint(3, max(4, high))
    b = rng.randint(2, 12)
    total = a * unit_cost             # so the unit cost is a whole number
    return (
        f"If {a} pens cost {total} rupees, what is the cost of {b} pens? State your units.",
        f"One pen costs {total} / {a} = {unit_cost} rupees, so {b} pens cost "
        f"{b * unit_cost} rupees.",
        "Unitary method and correct units.",
    )


def _rectangle(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    a = rng.randint(low, high)
    b = rng.randint(low, high)
    return (
        f"A rectangle measures {a} cm by {b} cm. Calculate its area and its "
        "perimeter, with units.",
        f"Area = {a} x {b} = {a * b} cm^2. Perimeter = 2 x ({a} + {b}) = {2 * (a + b)} cm.",
        "Applying the correct formula and unit.",
    )


def _triangle(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    base = rng.randrange(2, max(4, high) + 1, 2)   # even, so half is whole
    height = rng.randint(low, high)
    return (
        f"A triangle has base {base} cm and height {height} cm. Find its area and "
        "explain the formula you used.",
        f"Area = 1/2 x base x height = 1/2 x {base} x {height} = "
        f"{base * height // 2} cm^2.",
        "Choosing the right area formula.",
    )


def _percentage_of(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    percent = rng.choice([5, 10, 20, 25, 50])
    amount = rng.randint(2, max(3, high)) * 20     # keeps the answer whole
    return (
        f"Find {percent}% of {amount}. Show your working.",
        f"Divide {amount} by 100 to get {amount / 100:g}, then multiply by {percent} "
        f"to get {amount * percent // 100}.",
        "Percentage of an amount.",
    )


def _percentage_decrease(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    percent = rng.choice([10, 20, 25, 50])
    price = rng.randint(2, max(3, high)) * 20
    reduction = price * percent // 100
    return (
        f"An item costing {price} rupees is reduced by {percent}%. Work out the new "
        "price, with units.",
        f"{percent}% of {price} is {reduction} rupees, so the new price is "
        f"{price - reduction} rupees.",
        "Percentage decrease in context.",
    )


def _mean_of_four(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    values = [rng.randint(low, high) for _ in range(4)]
    # Nudge the last value up so the total divides by 4 and the mean is whole.
    remainder = sum(values) % 4
    if remainder:
        values[3] += 4 - remainder
    total = sum(values)
    return (
        f"Find the mean of these values: {', '.join(str(v) for v in values)}. "
        "Show your working.",
        f"Add the values to get {total}, then divide by 4 to get {total // 4}.",
        "Calculating the mean.",
    )


def _range_and_median(rng: random.Random, low: int, high: int) -> Tuple[str, str, str]:
    values = sorted(rng.sample(range(low, max(low + 8, high + 4)), 4))
    rng.shuffle(values)
    ordered = sorted(values)
    median = (ordered[1] + ordered[2]) / 2
    return (
        f"For the values {', '.join(str(v) for v in values)}, find the range and the "
        "median. Explain each step.",
        f"Ordered, the values are {', '.join(str(v) for v in ordered)}. "
        f"Range = {ordered[-1]} - {ordered[0]} = {ordered[-1] - ordered[0]}. "
        f"Median = ({ordered[1]} + {ordered[2]}) / 2 = {median:g}.",
        "Range and median from an unordered list.",
    )


_TEMPLATES: Dict[str, List[Builder]] = {
    "Linear Equations": [_solve_ax_plus_b, _word_equation],
    "Fractions and Decimals": [_add_fractions, _fraction_to_percentage],
    "Ratio and Proportion": [_share_in_ratio, _unitary_method],
    "Area and Perimeter": [_rectangle, _triangle],
    "Percentages": [_percentage_of, _percentage_decrease],
    "Data Handling": [_mean_of_four, _range_and_median],
}


def _seed_for(topic: str, error_type: ErrorType, difficulty: str, index: int) -> random.Random:
    """A per-question RNG that is stable across runs for the same selections."""
    return random.Random(f"{topic}|{error_type.value}|{difficulty}|{index}")


def generate_practice_questions(
    topic: str,
    error_type: ErrorType,
    difficulty: str,
    count: int = 3,
) -> List[PracticeQuestion]:
    """Generate practice questions from deterministic templates."""
    count = max(1, min(int(count), 10))
    builders = _TEMPLATES.get(topic)
    if not builders:
        raise ValueError(f"No practice templates are available for topic '{topic}'.")

    low, high = _DIFFICULTY_RANGE.get(difficulty, _DIFFICULTY_RANGE["Core"])
    remediation = _ERROR_PROMPTS.get(error_type, "Work carefully and show your reasoning.")

    questions: List[PracticeQuestion] = []
    for index in range(count):
        rng = _seed_for(topic, error_type, difficulty, index)
        builder = builders[index % len(builders)]
        question_text, method_hint, focus = builder(rng, low, high)
        questions.append(
            PracticeQuestion(
                number=index + 1,
                topic=topic,
                difficulty=difficulty,
                error_focus=error_type.label,
                question_text=question_text,
                method_hint=method_hint,
                skill_focus=f"{focus} {remediation}",
            )
        )
    return questions


def available_topics(extra: Sequence[str] = ()) -> List[str]:
    """Template topics, plus any assessment topics that also have templates."""
    known = list(TOPICS)
    for topic in extra:
        if topic in _TEMPLATES and topic not in known:
            known.append(topic)
    return known
