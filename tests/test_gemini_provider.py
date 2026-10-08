"""Tests for the Gemini provider, with a stand-in client - no key, no network."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from models import Question
from services import ai_grading_service as ai
from services import gemini_provider
from services.gemini_provider import DEFAULT_MODEL, GeminiGradingModel
from utils.config import Settings

pytest.importorskip("google.genai")

STUDENT_ANSWER = "3x = 22 - 7 = 15, then x = 15 / 3 = 6"


@pytest.fixture
def question() -> Question:
    return Question(
        id="q_lin_1",
        question_text="Solve for x: 3x + 7 = 22. Show each step of your working.",
        model_answer="Subtract 7 from both sides to get 3x = 15. Divide by 3 to get x = 5.",
        marking_criteria="1 mark per step; 1 mark for x = 5.",
        max_marks=3,
    )


class FakeModels:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text, error, []

    def generate_content(self, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.text)


def _model(text=None, error=None, model_id=DEFAULT_MODEL) -> GeminiGradingModel:
    fake = SimpleNamespace(models=FakeModels(text, error))
    return GeminiGradingModel("test-key", model_id, client=fake)


def _good_json(**overrides) -> str:
    payload = {
        "suggested_score": 2,
        "confidence": 0.8,
        "correct_elements": ["Subtracts 7 from both sides."],
        "errors": [{"error_type": "arithmetic_error", "explanation": "Division step is off."}],
        "student_feedback": "Good start. Check your final division step again.",
        "teacher_note": "Student wrote 6.",
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestGeminiModel:
    def test_sends_system_prompt_user_prompt_and_json_mode(self):
        model = _model(text="{}")
        assert model.complete("SYSTEM", "USER") == "{}"
        call = model._client.models.calls[0]
        assert call.model == DEFAULT_MODEL
        assert call.contents == "USER"
        assert call.config.system_instruction == "SYSTEM"
        assert call.config.response_mime_type == "application/json"
        assert call.config.temperature == 0.0

    def test_blocked_response_becomes_empty_text(self):
        assert _model(text=None).complete("s", "u") == ""

    def test_name_records_the_model_id(self):
        assert _model(model_id="gemini-2.5-flash-lite").name == "gemini:gemini-2.5-flash-lite"

    def test_key_is_required(self):
        with pytest.raises(ValueError):
            GeminiGradingModel("", client=object())

    def test_from_settings_reads_model_id_and_defaults(self, monkeypatch):
        monkeypatch.setattr(gemini_provider, "_client", lambda key: object())
        chosen = GeminiGradingModel.from_settings(
            Settings(llm_api_key="k", llm_model="gemini:gemini-2.5-flash-lite")
        )
        assert chosen.model_id == "gemini-2.5-flash-lite"
        bare = GeminiGradingModel.from_settings(Settings(llm_api_key="k", llm_model="gemini"))
        assert bare.model_id == DEFAULT_MODEL

    def test_real_client_builds_without_network(self):
        gemini_provider._client.cache_clear()
        assert GeminiGradingModel("not-a-real-key").model_id == DEFAULT_MODEL


class TestGeminiThroughPipeline:
    def test_registry_selects_gemini(self, monkeypatch):
        from services import auth_service

        monkeypatch.setattr(auth_service, "is_signed_in", lambda: True)
        monkeypatch.setattr(gemini_provider, "_client", lambda key: object())
        model = ai.get_grading_model(Settings(llm_api_key="k", llm_model="gemini:gemini-2.5-flash"))
        assert isinstance(model, GeminiGradingModel)

    def test_valid_output_is_an_ai_grade(self, question):
        outcome = ai.grade_with_ai(question, STUDENT_ANSWER, "sub_1", model=_model(_good_json()))
        assert outcome.used_ai
        assert outcome.engine == f"gemini:{DEFAULT_MODEL}"
        assert outcome.result.suggested_score == 2

    def test_rate_limit_error_falls_back(self, question):
        outcome = ai.grade_with_ai(
            question, STUDENT_ANSWER, "sub_1", model=_model(error=RuntimeError("429"))
        )
        assert not outcome.used_ai
        assert "RuntimeError" in outcome.fallback_reason

    def test_leaking_feedback_falls_back(self, question):
        leaky = _good_json(student_feedback="Nearly - the answer is x = 5.")
        outcome = ai.grade_with_ai(question, STUDENT_ANSWER, "sub_1", model=_model(leaky))
        assert not outcome.used_ai

    def test_provider_setup_failure_falls_back(self, question, monkeypatch):
        from services import auth_service

        monkeypatch.setattr(auth_service, "is_signed_in", lambda: True)
        def broken(settings):
            raise ImportError("no sdk")

        monkeypatch.setitem(ai._PROVIDERS, "gemini", broken)
        outcome = ai.grade_with_ai(
            question, STUDENT_ANSWER, "sub_1",
            settings=Settings(llm_api_key="k", llm_model="gemini:x"),
        )
        assert not outcome.used_ai
        assert "ImportError" in outcome.fallback_reason
