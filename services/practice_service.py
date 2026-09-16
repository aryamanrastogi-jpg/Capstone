"""Template-based practice question generator (prototype).

Phase 1 uses deterministic templates with numbers derived from a stable seed,
so the same selections always produce the same questions. No AI is involved.
Phase 2 replaces `generate_practice_questions` with a real LLM call.

Each template builds its numbers *backwards from a chosen answer* rather than
picking them at random. A generator that emits "36x + 36 = 21" is worse than
useless to a Grade 7 class, so every question here resolves to a clean value.

Pointers, not answers. Students see `method_hint`, so it names the method and
what to check - never the worked solution or the final value. The answer each
template chose is kept on the internal `_Built` record so tests can prove the
hint does not give it away; it is never put on a `PracticeQuestion`.

Choosing *which* topic, error category and difficulty to practise from a
student's own results lives in `services/targeted_practice_service.py`.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from math import gcd
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

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

# Words that tie a free-text topic (e.g. from a student's own question set) to
# a template topic. Matched on whole words, case-insensitively.
_TOPIC_KEYWORDS: List[Tuple[str, Tuple[str, ...]]] = [
    ("Linear Equations", ("linear", "equation", "equations", "algebra")),
    ("Fractions and Decimals", ("fraction", "fractions", "decimal", "decimals")),
    ("Ratio and Proportion", ("ratio", "ratios", "proportion", "proportions", "unitary")),
    ("Area and Perimeter", ("area", "areas", "perimeter", "perimeters", "mensuration")),
    ("Percentages", ("percentage", "percentages", "percent")),
    ("Data Handling", ("data", "statistics", "mean", "median", "averages")),
]


@dataclass
class PracticeQuestion:
    number: int
    topic: str
    difficulty: str
    error_focus: str
    question_text: str
    method_hint: str
    skill_focus: str


class _Built(NamedTuple):
    """What a template produces. `answers` is for tests only - never shown."""

    question: str
    pointer: str
    focus: str
    answers: Tuple[str, ...]


# --------------------------------------------------------------------------
# Template builders
#
# Each builder takes an RNG plus the difficulty bounds and returns a _Built.
# Values are chosen so the answer is a whole number or a tidy fraction.
# --------------------------------------------------------------------------
Builder = Callable[[random.Random, int, int], _Built]


def _solve_ax_plus_b(rng: random.Random, low: int, high: int) -> _Built:
    a = rng.randint(2, max(3, high // 2))
    x = rng.randint(2, high)          # the answer, chosen first
    b = rng.randint(1, high)
    c = a * x + b                     # so the equation resolves exactly
    return _Built(
        f"Solve for x: {a}x + {b} = {c}. Show every step of your working.",
        f"Undo the operations in reverse order: deal with the + {b} first, then the "
        f"{a}x. Do the same thing to both sides each time, and check your value by "
        "substituting it back into the original equation.",
        "Isolating the variable one operation at a time.",
        (str(x), str(a * x)),
    )


def _word_equation(rng: random.Random, low: int, high: int) -> _Built:
    a = rng.randint(2, max(3, high // 2))
    n = rng.randint(2, high)
    b = rng.randint(1, high)
    c = a * n + b
    return _Built(
        f"A number is multiplied by {a} and then {b} is added. The result is {c}. "
        "Write an equation and solve it.",
        "Call the number n and turn the sentence into an equation one phrase at a "
        "time. Solve it like any two-step equation, then check your n against the "
        "original sentence, not just your equation.",
        "Translating a word problem into an equation.",
        (str(n), str(a * n)),
    )


def _equation_with_brackets(rng: random.Random, low: int, high: int) -> _Built:
    a = rng.randint(2, max(3, high // 3))
    x = rng.randint(1, high)
    b = rng.randint(1, max(2, high // 2))
    c = a * (x + b)
    return _Built(
        f"Solve for x: {a}(x + {b}) = {c}. Show every step of your working.",
        f"You can either divide both sides by {a} first or expand the bracket first. "
        "Say which you chose and why, then isolate x one step at a time.",
        "Equations with brackets.",
        (str(x), str(x + b)),
    )


def _equation_with_division(rng: random.Random, low: int, high: int) -> _Built:
    d = rng.randint(2, max(3, high // 3))
    x = d * rng.randint(1, max(2, high // 2))   # a multiple of d, so x / d is whole
    b = rng.randint(1, high)
    c = x // d + b
    return _Built(
        f"Solve for x: x/{d} + {b} = {c}. Show every step of your working.",
        f"Undo the + {b} first. What is the opposite of dividing by {d}? Do that to "
        "both sides next, then check by substituting back.",
        "Undoing division in an equation.",
        (str(x), str(x // d)),
    )


def _add_fractions(rng: random.Random, low: int, high: int) -> _Built:
    b = rng.randint(2, 9)
    d = rng.randint(2, 9)
    a = rng.randint(1, b - 1) if b > 1 else 1
    c = rng.randint(1, d - 1) if d > 1 else 1
    numerator = a * d + c * b
    denominator = b * d
    divisor = gcd(numerator, denominator)
    return _Built(
        f"Work out {a}/{b} + {c}/{d}. Give your answer in its simplest form.",
        f"Find a denominator that both {b} and {d} divide into, rewrite each fraction "
        "over it, then add the numerators only. Finish by checking whether the top "
        "and bottom share a factor.",
        "Common denominators and simplifying.",
        (
            f"{numerator}/{denominator}",
            f"{numerator // divisor}/{denominator // divisor}",
        ),
    )


def _fraction_to_percentage(rng: random.Random, low: int, high: int) -> _Built:
    b = rng.choice([2, 4, 5, 8, 10, 20, 25])
    a = rng.randint(1, b - 1)
    decimal = a / b
    return _Built(
        f"Convert {a}/{b} to a decimal and then to a percentage. Show your method.",
        "A fraction is a division: the top divided by the bottom gives the decimal. "
        "'Per cent' means 'out of 100' - use that to move from the decimal to the "
        "percentage.",
        "Moving between fractions, decimals and percentages.",
        (f"{decimal:g}", f"{decimal * 100:g}%"),
    )


def _multiply_fractions(rng: random.Random, low: int, high: int) -> _Built:
    b = rng.randint(2, 9)
    d = rng.randint(2, 9)
    a = rng.randint(1, b - 1)
    c = rng.randint(1, d - 1)
    numerator, denominator = a * c, b * d
    divisor = gcd(numerator, denominator)
    return _Built(
        f"Work out {a}/{b} x {c}/{d}. Give your answer in its simplest form.",
        "Multiplying fractions does not need a common denominator. Decide what to do "
        "with the numerators and the denominators, and look for factors you can "
        "cancel before or after multiplying.",
        "Multiplying fractions.",
        (
            f"{numerator}/{denominator}",
            f"{numerator // divisor}/{denominator // divisor}",
        ),
    )


def _share_in_ratio(rng: random.Random, low: int, high: int) -> _Built:
    a = rng.randint(1, 5)
    b = rng.randint(1, 5)
    part = rng.randint(2, max(3, high))
    total = (a + b) * part            # divides exactly by the number of parts
    return _Built(
        f"Share {total} counters in the ratio {a} : {b}. Show your working.",
        "Add the ratio numbers to find how many equal parts there are, find the size "
        "of one part, then build each share from it. Check that your shares add back "
        "up to the total.",
        "Dividing a quantity in a given ratio.",
        (str(part), str(a * part), str(b * part)),
    )


def _unitary_method(rng: random.Random, low: int, high: int) -> _Built:
    a = rng.randint(2, 9)
    unit_cost = rng.randint(3, max(4, high))
    b = rng.randint(2, 12)
    total = a * unit_cost             # so the unit cost is a whole number
    return _Built(
        f"If {a} pens cost {total} rupees, what is the cost of {b} pens? State your units.",
        "Find the cost of one pen first, then scale up to the number you need. Keep "
        "the unit on every line of working.",
        "Unitary method and correct units.",
        (str(unit_cost), str(b * unit_cost)),
    )


def _simplify_ratio(rng: random.Random, low: int, high: int) -> _Built:
    a = rng.randint(1, 7)
    b = rng.choice([n for n in range(1, 9) if gcd(a, n) == 1 and n != a])
    k = rng.randint(2, max(3, high // 2))
    return _Built(
        f"Write the ratio {a * k} : {b * k} in its simplest form. Explain how you "
        "know it cannot be simplified further.",
        "Look for a number that divides into both sides exactly, and divide both "
        "sides by it. Keep going until the only number that divides both is 1.",
        "Simplifying ratios using common factors.",
        (f"{a} : {b}", f"{a}:{b}"),
    )


def _scale_a_recipe(rng: random.Random, low: int, high: int) -> _Built:
    people = rng.choice([2, 4, 5, 6])
    per_person = rng.randint(2, max(3, high)) * 10
    wanted = rng.choice([n for n in range(2, 13) if n != people])
    return _Built(
        f"A recipe for {people} people uses {people * per_person} g of flour. How "
        f"much flour is needed for {wanted} people? Include the unit.",
        "Work out how much one person needs, then scale to the number of people "
        "asked for. Ask yourself whether the answer should be more or less than the "
        "original amount before you calculate.",
        "Direct proportion in context.",
        (str(per_person), str(per_person * wanted)),
    )


def _rectangle(rng: random.Random, low: int, high: int) -> _Built:
    a = rng.randint(low, high)
    b = rng.randint(low, high)
    return _Built(
        f"A rectangle measures {a} cm by {b} cm. Calculate its area and its "
        "perimeter, with units.",
        "Area counts the squares inside the shape; perimeter is the distance around "
        "its edge. Write each formula before substituting, and notice that the two "
        "answers need different units.",
        "Applying the correct formula and unit.",
        (str(a * b), str(2 * (a + b))),
    )


def _triangle(rng: random.Random, low: int, high: int) -> _Built:
    base = rng.randrange(2, max(4, high) + 1, 2)   # even, so half is whole
    height = rng.randint(low, high)
    return _Built(
        f"A triangle has base {base} cm and height {height} cm. Find its area and "
        "explain the formula you used.",
        "A triangle is half of a rectangle with the same base and height. Use that "
        "to choose the formula, write it out, then substitute.",
        "Choosing the right area formula.",
        (str(base * height // 2), str(base * height)),
    )


def _missing_side(rng: random.Random, low: int, high: int) -> _Built:
    width = rng.randint(low, high)
    length = rng.randint(low, high)
    return _Built(
        f"A rectangle has an area of {width * length} cm^2 and a width of {width} cm. "
        "Find its length, then its perimeter, with units.",
        "Start from the area formula and rearrange it to find the missing side. You "
        "need both sides before you can work out the perimeter.",
        "Working backwards from an area.",
        (str(length), str(2 * (width + length))),
    )


def _compound_shape(rng: random.Random, low: int, high: int) -> _Built:
    a, b = rng.randint(low, high), rng.randint(low, high)
    c, d = rng.randint(low, high), rng.randint(low, high)
    return _Built(
        f"An L-shaped floor is made from a {a} m by {b} m rectangle joined to a "
        f"{c} m by {d} m rectangle. Find the total floor area, with units.",
        "Split the shape into the two rectangles, find each area on its own line, "
        "then combine them. Say which unit an area takes and why.",
        "Area of compound shapes.",
        (str(a * b + c * d),),
    )


def _percentage_of(rng: random.Random, low: int, high: int) -> _Built:
    percent = rng.choice([5, 10, 20, 25, 50])
    amount = rng.randint(2, max(3, high)) * 20     # keeps the answer whole
    return _Built(
        f"Find {percent}% of {amount}. Show your working.",
        "Find one per cent or ten per cent of the amount first, then build up to the "
        "percentage you need. Check the size of your answer: is it sensible?",
        "Percentage of an amount.",
        (str(amount * percent // 100),),
    )


def _percentage_decrease(rng: random.Random, low: int, high: int) -> _Built:
    percent = rng.choice([10, 20, 25, 50])
    price = rng.randint(2, max(3, high)) * 20
    reduction = price * percent // 100
    return _Built(
        f"An item costing {price} rupees is reduced by {percent}%. Work out the new "
        "price, with units.",
        "Work out the size of the reduction first, then decide what to do with it. "
        "Alternatively, ask what percentage of the original price is left and use "
        "that directly.",
        "Percentage decrease in context.",
        (str(reduction), str(price - reduction)),
    )


def _percentage_increase(rng: random.Random, low: int, high: int) -> _Built:
    percent = rng.choice([5, 10, 20, 25, 50])
    salary = rng.randint(2, max(3, high)) * 100
    rise = salary * percent // 100
    return _Built(
        f"A monthly wage of {salary} rupees rises by {percent}%. Work out the new "
        "wage, with units.",
        "Find the size of the rise as a percentage of the original wage, then decide "
        "whether it is added or taken away. The new wage should be more than the old one.",
        "Percentage increase in context.",
        (str(rise), str(salary + rise)),
    )


def _express_as_percentage(rng: random.Random, low: int, high: int) -> _Built:
    total = rng.choice([20, 25, 50])
    part = rng.randint(1, total - 1)
    return _Built(
        f"In a class survey, {part} out of {total} students walk to school. What "
        "percentage of the students walk? Show your method.",
        "Write the amount as a fraction of the total first. Then turn that fraction "
        "into a percentage - an equivalent fraction out of 100 is one way.",
        "Expressing one quantity as a percentage of another.",
        (f"{part * 100 / total:g}%",),
    )


def _mean_of_four(rng: random.Random, low: int, high: int) -> _Built:
    values = [rng.randint(low, high) for _ in range(4)]
    # Nudge the last value up so the total divides by 4 and the mean is whole.
    remainder = sum(values) % 4
    if remainder:
        values[3] += 4 - remainder
    total = sum(values)
    return _Built(
        f"Find the mean of these values: {', '.join(str(v) for v in values)}. "
        "Show your working.",
        "The mean shares the total out equally. Find the total, then share it by how "
        "many values there are. Your mean should sit between the smallest and largest value.",
        "Calculating the mean.",
        (str(total), str(total // 4)),
    )


def _missing_value_from_mean(rng: random.Random, low: int, high: int) -> _Built:
    known = [rng.randint(low, high) for _ in range(4)]
    missing = rng.randint(low, high)
    count = len(known) + 1
    # Nudge the missing value so the total divides by 5 and the mean is whole.
    missing += (-(sum(known) + missing)) % count
    mean = (sum(known) + missing) // count
    return _Built(
        f"The mean of five test scores is {mean}. Four of the scores are "
        f"{', '.join(str(v) for v in known)}. Find the fifth score, showing your working.",
        "Knowing the mean and how many values there are tells you what they must "
        "add up to. Compare that with the total of the scores you already know.",
        "Working backwards from a mean.",
        (str(missing), str(mean * count)),
    )


def _range_and_median(rng: random.Random, low: int, high: int) -> _Built:
    values = sorted(rng.sample(range(low, max(low + 8, high + 4)), 4))
    rng.shuffle(values)
    ordered = sorted(values)
    median = (ordered[1] + ordered[2]) / 2
    return _Built(
        f"For the values {', '.join(str(v) for v in values)}, find the range and the "
        "median. Explain each step.",
        "Put the values in order first. The range is a difference between two values, "
        "not a value from the list; with an even number of values the median sits "
        "halfway between the middle two.",
        "Range and median from an unordered list.",
        (str(ordered[-1] - ordered[0]), f"{median:g}"),
    )


_TEMPLATES: Dict[str, List[Builder]] = {
    "Linear Equations": [
        _solve_ax_plus_b, _word_equation, _equation_with_brackets, _equation_with_division,
    ],
    "Fractions and Decimals": [_add_fractions, _fraction_to_percentage, _multiply_fractions],
    "Ratio and Proportion": [
        _share_in_ratio, _unitary_method, _simplify_ratio, _scale_a_recipe,
    ],
    "Area and Perimeter": [_rectangle, _triangle, _missing_side, _compound_shape],
    "Percentages": [
        _percentage_of, _percentage_decrease, _percentage_increase, _express_as_percentage,
    ],
    "Data Handling": [_mean_of_four, _range_and_median, _missing_value_from_mean],
}


def template_topic_for(topic: str) -> Optional[str]:
    """The template topic a free-text topic name belongs to, or None.

    Exact names match first; otherwise a keyword such as "percent" or "ratio"
    maps e.g. "Percentage change" to "Percentages".
    """
    cleaned = (topic or "").strip()
    if not cleaned:
        return None
    for known in _TEMPLATES:
        if known.casefold() == cleaned.casefold():
            return known
    words = set(re.findall(r"[a-z]+", cleaned.casefold()))
    for known, keywords in _TOPIC_KEYWORDS:
        if words.intersection(keywords):
            return known
    return None


def _seed_for(topic: str, error_type: ErrorType, difficulty: str, index: int) -> random.Random:
    """A per-question RNG that is stable across runs for the same selections."""
    return random.Random(f"{topic}|{error_type.value}|{difficulty}|{index}")


def generate_practice_questions(
    topic: str,
    error_type: ErrorType,
    difficulty: str,
    count: int = 3,
    start: int = 0,
) -> List[PracticeQuestion]:
    """Generate practice questions from deterministic templates.

    `start` continues a sequence: questions `start`..`start + count - 1`, so two
    calls for the same topic can rotate through different templates rather than
    both beginning with the first one.
    """
    count = max(1, min(int(count), 10))
    start = max(0, int(start))
    resolved = template_topic_for(topic)
    builders = _TEMPLATES.get(resolved) if resolved else None
    if not builders:
        raise ValueError(f"No practice templates are available for topic '{topic}'.")

    low, high = _DIFFICULTY_RANGE.get(difficulty, _DIFFICULTY_RANGE["Core"])
    remediation = _ERROR_PROMPTS.get(error_type, "Work carefully and show your reasoning.")

    questions: List[PracticeQuestion] = []
    for offset in range(count):
        index = start + offset
        rng = _seed_for(resolved, error_type, difficulty, index)
        built = builders[index % len(builders)](rng, low, high)
        questions.append(
            PracticeQuestion(
                number=offset + 1,
                topic=resolved,
                difficulty=difficulty,
                error_focus=error_type.label,
                question_text=built.question,
                method_hint=built.pointer,
                skill_focus=f"{built.focus} {remediation}",
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
