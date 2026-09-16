"""Score a grader against the labelled dataset and print accuracy metrics.

Usage (from the repo root):

    .venv/Scripts/python scripts/evaluate_grading.py            # rule-based grader
    .venv/Scripts/python scripts/evaluate_grading.py --ai       # AI path, with fallback
    .venv/Scripts/python scripts/evaluate_grading.py --show-misses

`--ai` goes through `grade_with_ai`, so without a configured provider every item
falls back to the rule-based grader - the "Grading paths used" line makes that
visible instead of quietly reporting rule-based numbers as AI numbers.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import GradingResult, Question  # noqa: E402
from services import grading_service  # noqa: E402
from services.ai_grading_service import get_grading_model, grade_with_ai  # noqa: E402
from services.grading_evaluation import (  # noqa: E402
    DEFAULT_DATASET,
    compute_metrics,
    evaluate,
    format_report,
    load_dataset,
    sample_questions,
)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--ai", action="store_true", help="grade via grade_with_ai")
    parser.add_argument("--show-misses", action="store_true",
                        help="list items more than half a mark from the teacher")
    args = parser.parse_args(argv)

    items = load_dataset(args.dataset)
    questions = sample_questions()

    if args.ai:
        paths: Dict[str, str] = {}
        model = get_grading_model()

        def grader(question: Question, answer: str, submission_id: str) -> GradingResult:
            outcome = grade_with_ai(question, answer, submission_id, model=model)
            paths[submission_id.removeprefix("eval_")] = outcome.path
            return outcome.result

        records = evaluate(items, questions, grader, path_of=paths.get)
        name = f"AI ({model.name})" if model is not None else "AI (no provider - rule-based fallback)"
    else:
        records = evaluate(items, questions, grading_service.grade_answer)
        name = grading_service.MOCK_ENGINE_NAME

    print(format_report(compute_metrics(records), name))

    if args.show_misses:
        misses = [r for r in records if abs(r.predicted_score - r.teacher_score) > 0.5]
        print(f"\nMore than half a mark off ({len(misses)}):")
        for r in misses:
            print(f"  {r.item_id}: teacher {r.teacher_score:g}, grader {r.predicted_score:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
