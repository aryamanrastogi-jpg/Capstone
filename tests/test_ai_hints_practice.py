"""AI hints and AI practice questions, with a scripted model - no network.

What must hold whichever model is plugged in:
  * the model answer never goes into a hint prompt;
  * a hint or method pointer that contains the answer is thrown away;
  * anything the AI does not supply falls back to the templates;
  * a successful response is cached, so Streamlit reruns do not re-call it.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from models import ErrorType, Question, Subject
from services import ai_grading_service as ai
from services import hint_service, llm_service, practice_service
from services import targeted_practice_service as targeted

QUESTION = Question(
    id="q1",
    question_text="Solve for x: 3x + 7 = 22.",
    model_answer="Subtract 7 to get 3x = 15, then divide by 3: x = 5.",
    marking_criteria="1 mark per step.",
    max_marks=3,
)


@pytest.fixture
def use_model(monkeypatch):
    """Plug a FakeGradingModel in as the configured provider."""

    def install(*responses: str, responder=None):
        model = ai.FakeGradingModel(list(responses) or None, responder=responder)
        monkeypatch.setattr(llm_service, "get_model", lambda settings=None: model)
        return model

    return install


def _guidance_item(number=1, **overrides) -> dict:
    item = {
        "number": number,
        "shape": "Linear equation",
        "approach": ["Undo the addition on both sides.", "Undo the multiplication.", "Check it."],
        "include": ["Every line of working.", "The value of x."],
        "watch_out_for": ["Forgetting to change both sides."],
        "final_answer": "x = 5",
    }
    item.update(overrides)
    return item


# --------------------------------------------------------------------------
# Approach guidance
# --------------------------------------------------------------------------
class TestAIGuidance:
    def test_no_model_means_templates(self):
        guidance = hint_service.guidance_for(QUESTION)
        assert guidance == hint_service.rule_based_guidance(QUESTION)

    def test_ai_guidance_is_used(self, use_model):
        use_model(json.dumps({"questions": [_guidance_item()]}))
        guidance = hint_service.guidance_for(QUESTION)
        assert guidance.shape == "linear equation"
        assert guidance.approach[0] == "Undo the addition on both sides."
        assert guidance.question_id == "q1"

    def test_prompt_never_contains_the_model_answer(self, use_model):
        model = use_model(json.dumps({"questions": [_guidance_item()]}))
        hint_service.guidance_for(QUESTION)
        system, user = model.calls[0]
        assert QUESTION.question_text in user
        assert "x = 5" not in user and "3x = 15" not in system + user

    def test_leaking_guidance_falls_back_to_templates(self, use_model):
        leaky = _guidance_item(approach=["You should get 15 after the first step.", "Then 5."])
        use_model(json.dumps({"questions": [leaky]}))
        assert hint_service.guidance_for(QUESTION) == hint_service.rule_based_guidance(QUESTION)

    def test_values_from_the_question_are_allowed(self, use_model):
        fine = _guidance_item(approach=["Take 7 from both sides.", "Then deal with the 3."])
        use_model(json.dumps({"questions": [fine]}))
        assert hint_service.guidance_for(QUESTION).approach[0] == "Take 7 from both sides."

    def test_one_call_for_a_set_and_partial_fallback(self, use_model):
        second = QUESTION.model_copy(update={"id": "q2", "question_text": "Find 20% of 60."})
        model = use_model(json.dumps({"questions": [_guidance_item(1), {"number": 2}]}))
        result = hint_service.guidance_for_questions([QUESTION, second])
        assert len(model.calls) == 1
        assert result[0].shape == "linear equation"
        assert result[1] == hint_service.rule_based_guidance(second)

    def test_success_is_cached_failure_is_not(self, use_model):
        model = use_model("not json at all")
        hint_service.guidance_for(QUESTION)
        hint_service.guidance_for(QUESTION)
        assert len(model.calls) == 2  # failures retry

        model = use_model(json.dumps({"questions": [_guidance_item()]}))
        hint_service.guidance_for(QUESTION)
        hint_service.guidance_for(QUESTION)
        assert len(model.calls) == 1  # success is remembered

    def test_provider_error_falls_back(self, use_model):
        def boom(system, user):
            raise RuntimeError("429 rate limited")

        use_model(responder=boom)
        assert hint_service.guidance_for(QUESTION) == hint_service.rule_based_guidance(QUESTION)


# --------------------------------------------------------------------------
# Hint ladder
# --------------------------------------------------------------------------
class TestAIPointers:
    def test_ai_pointers_use_the_students_attempt(self, use_model):
        model = use_model(json.dumps({
            "pointers": ["Look again at how you undid the multiplication."],
            "final_answer": "5",
        }))
        pointers = hint_service.escalating_pointers(
            QUESTION, [ErrorType.ARITHMETIC_ERROR], Subject.MATHEMATICS, 2, "3x = 15 so x = 6"
        )
        assert pointers == ["Look again at how you undid the multiplication."]
        system, user = model.calls[0]
        assert "3x = 15 so x = 6" in user
        assert "hint level 2" in user
        assert "Arithmetic Error" in user
        assert QUESTION.model_answer not in user

    def test_numbers_the_student_wrote_are_allowed(self, use_model):
        use_model(json.dumps({"pointers": ["Check the step where you got 15."], "final_answer": "15 then 5"}))
        pointers = hint_service.escalating_pointers(QUESTION, level=1, student_answer="3x = 15")
        assert pointers == ["Check the step where you got 15."]

    def test_leaking_pointer_falls_back_to_the_ladder(self, use_model):
        use_model(json.dumps({"pointers": ["It should come out as 5."], "final_answer": "5"}))
        pointers = hint_service.escalating_pointers(QUESTION, level=1, student_answer="x = 6")
        assert all("5" not in p.replace("15", "") for p in pointers)
        assert pointers[0].startswith("This is an equation to solve")


# --------------------------------------------------------------------------
# Practice questions
# --------------------------------------------------------------------------
def _practice(count: int, hint: str = "Undo each operation in reverse order.") -> str:
    # Every question solves to x = 9, a value none of them contains.
    return json.dumps({"questions": [
        {"question_text": f"Solve {a}x + 1 = {a * 9 + 1}.", "method_hint": hint,
         "skill_focus": "Two-step equations", "answer": "x = 9"}
        for a in (2, 3, 4)[:count]
    ]})


class TestAIPractice:
    def test_ai_questions_are_used(self, use_model):
        use_model(_practice(3))
        questions = practice_service.generate_practice_questions(
            "Linear Equations", ErrorType.MISSING_WORKING, "Core", count=3
        )
        assert [q.number for q in questions] == [1, 2, 3]
        assert questions[0].question_text == "Solve 2x + 1 = 19."
        assert questions[0].skill_focus.startswith("Two-step equations.")

    def test_leaking_hint_is_dropped_and_templates_top_up(self, use_model):
        use_model(_practice(3, hint="Subtract 1 then divide - you get 9."))
        questions = practice_service.generate_practice_questions(
            "Linear Equations", ErrorType.MISSING_WORKING, "Core", count=3
        )
        assert len(questions) == 3
        assert all("you get 9" not in q.method_hint for q in questions)
        assert questions[0].question_text.startswith("Solve for x:")  # a template

    def test_any_topic_works_with_ai(self, use_model):
        use_model(_practice(2))
        questions = practice_service.generate_practice_questions(
            "Pythagoras", ErrorType.UNIT_ERROR, "Extension", count=2
        )
        assert len(questions) == 2 and questions[0].topic == "Pythagoras"

    def test_unknown_topic_without_ai_still_raises(self):
        with pytest.raises(ValueError):
            practice_service.generate_practice_questions(
                "Pythagoras", ErrorType.UNIT_ERROR, "Core", count=2
            )

    def test_examples_reach_the_prompt(self, use_model):
        model = use_model(_practice(1))
        practice_service.generate_practice_questions(
            "Linear Equations", ErrorType.ARITHMETIC_ERROR, "Core", count=1,
            examples=["Solve 5x - 4 = 21."],
        )
        assert "Solve 5x - 4 = 21." in model.calls[0][1]

    def test_extra_topics_offered_only_with_ai(self, use_model):
        assert "Pythagoras" not in practice_service.available_topics(["Pythagoras"])
        use_model(_practice(1))
        assert "Pythagoras" in practice_service.available_topics(["Pythagoras"])


class TestTargetedWithAI:
    @staticmethod
    def _frame() -> pd.DataFrame:
        return pd.DataFrame([
            {"topic": "Pythagoras", "percentage": 20.0, "error_types": ["unit_error"],
             "question_text": "Find the hypotenuse of a 3-4 triangle."},
            {"topic": "Pythagoras", "percentage": 60.0, "error_types": [],
             "question_text": "Find a missing short side."},
            {"topic": "Pythagoras", "percentage": 100.0, "error_types": [],
             "question_text": "A question answered perfectly."},
        ])

    def test_hardest_questions_are_worst_first_and_skip_perfect(self):
        assert targeted.hardest_questions(self._frame(), ["Pythagoras"]) == [
            "Find the hypotenuse of a 3-4 triangle.",
            "Find a missing short side.",
        ]

    def test_untemplated_topic_is_dropped_without_ai(self):
        plan = targeted.generate_targeted_practice(self._frame(), total=2)
        assert plan.is_empty and plan.unsupported_topics == ["Pythagoras"]

    def test_ai_practises_the_students_own_hard_questions(self, use_model):
        model = use_model(_practice(2))
        plan = targeted.generate_targeted_practice(self._frame(), total=2)
        assert len(plan.items) == 2
        assert plan.unsupported_topics == []
        assert "Find the hypotenuse of a 3-4 triangle." in model.calls[0][1]
        assert "A question answered perfectly." not in model.calls[0][1]
