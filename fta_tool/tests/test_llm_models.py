"""Tests for the structured LLM output / metrics Pydantic models (Step 1)."""

import pytest
from pydantic import ValidationError

from app.services.llm_models import (
    GenerationMetrics,
    LLMFactor,
    LLMFactorList,
    ollama_format_schema_from_pydantic,
)


# --- LLMFactor / LLMFactorList validation -----------------------------------

def test_llm_factor_valid_minimal():
    f = LLMFactor(name="認証サーバの障害")
    assert f.name == "認証サーバの障害"
    assert f.description == ""
    assert f.confidence == "medium"
    assert f.confidence_label() == "可能性あり"


def test_llm_factor_strips_whitespace():
    f = LLMFactor(name="  設定ミス  ", description="  説明  ")
    assert f.name == "設定ミス"
    assert f.description == "説明"


def test_llm_factor_empty_name_raises():
    with pytest.raises(ValidationError):
        LLMFactor(name="   ")


def test_llm_factor_optional_fields():
    f = LLMFactor(
        name="DNSの不調", description="名前解決の失敗", confidence="high",
        reason="ログイン直前にDNS応答が遅延", factor_type="技術要因",
    )
    assert f.reason == "ログイン直前にDNS応答が遅延"
    assert f.factor_type == "技術要因"
    assert f.confidence_label() == "可能性高"


def test_llm_factor_unknown_confidence_kept_verbatim():
    f = LLMFactor(name="X", confidence="very_high")
    assert f.confidence_label() == "very_high"


def test_llm_factor_list_validate_compact():
    data = {"factors": [
        {"name": "A", "description": "aaa", "confidence": "high"},
        {"name": "B", "description": "bbb", "confidence": "low"},
    ]}
    parsed = LLMFactorList.model_validate(data)
    assert len(parsed.factors) == 2
    assert parsed.factors[0].name == "A"


def test_llm_factor_list_rejects_list_of_strings():
    """A list[str] payload must fail validation (caller falls back to legacy)."""
    with pytest.raises(ValidationError):
        LLMFactorList.model_validate({"factors": ["foo", "bar"]})


def test_llm_factor_list_rejects_missing_name():
    """Legacy {title,...} shape (no 'name') fails → legacy fallback path."""
    with pytest.raises(ValidationError):
        LLMFactorList.model_validate({"factors": [{"title": "x", "description": "y"}]})


# --- GenerationMetrics ------------------------------------------------------

def test_generation_metrics_from_ollama_response():
    data = {
        "model": "gemma3:4b",
        "total_duration": 1_500_000_000,
        "load_duration": 200_000_000,
        "prompt_eval_count": 123,
        "prompt_eval_duration": 300_000_000,
        "eval_count": 456,
        "eval_duration": 900_000_000,
    }
    m = GenerationMetrics.from_ollama_response(
        data, model_name="gemma3:4b", level=1, parent=None,
        start_time="2026-06-25T00:00:00", end_time="2026-06-25T00:00:02",
        elapsed_ms=2000, success=True, retries=0,
    )
    assert m.prompt_eval_count == 123
    assert m.eval_count == 456
    assert m.total_duration == 1_500_000_000
    assert m.success is True
    # JSON serializable for logging
    assert "prompt_eval_count" in m.model_dump_json()


# --- Ollama format schema (structured output) -------------------------------

def _item_schema(schema: dict) -> dict:
    return schema["properties"]["factors"]["items"]


def test_pydantic_format_schema_is_ref_free():
    """Derived schema must not contain $ref/$defs (older Ollama compatibility)."""
    import json
    schema = ollama_format_schema_from_pydantic()
    blob = json.dumps(schema)
    assert "$ref" not in blob
    assert "$defs" not in blob


def test_pydantic_format_schema_matches_inline_semantically():
    """Drift guard: Pydantic-derived schema and the inline _FORMAT_SCHEMA agree
    on object type, required fields, properties and the confidence enum."""
    from app.services.ai_provider import OllamaProvider

    derived = ollama_format_schema_from_pydantic()
    inline = OllamaProvider._FORMAT_SCHEMA

    assert derived["type"] == inline["type"] == "object"
    assert derived["required"] == inline["required"] == ["factors"]

    d_item, i_item = _item_schema(derived), _item_schema(inline)
    assert set(d_item["properties"]) == set(i_item["properties"]) == {
        "name", "description", "confidence",
    }
    assert sorted(d_item["required"]) == sorted(i_item["required"])
    assert d_item["properties"]["confidence"]["enum"] == \
        i_item["properties"]["confidence"]["enum"] == ["high", "medium", "low"]


def test_format_schema_default_is_inline(monkeypatch):
    from app.services.ai_provider import OllamaProvider
    monkeypatch.delenv("OLLAMA_FORMAT_FROM_PYDANTIC", raising=False)
    assert OllamaProvider._format_schema() is OllamaProvider._FORMAT_SCHEMA


def test_format_schema_pydantic_when_enabled(monkeypatch):
    from app.services.ai_provider import OllamaProvider
    monkeypatch.setenv("OLLAMA_FORMAT_FROM_PYDANTIC", "true")
    schema = OllamaProvider._format_schema()
    assert schema is not OllamaProvider._FORMAT_SCHEMA
    assert schema["required"] == ["factors"]


def test_format_schema_falls_back_on_error(monkeypatch):
    """If derivation raises, _format_schema falls back to the inline schema."""
    from app.services import ai_provider
    from app.services.ai_provider import OllamaProvider
    monkeypatch.setenv("OLLAMA_FORMAT_FROM_PYDANTIC", "true")
    monkeypatch.setattr(
        ai_provider.generation_config, "format_schema_from_pydantic", lambda: True
    )

    def _boom():
        raise RuntimeError("schema build failed")

    import app.services.llm_models as llm_models
    monkeypatch.setattr(llm_models, "ollama_format_schema_from_pydantic", _boom)
    assert OllamaProvider._format_schema() is OllamaProvider._FORMAT_SCHEMA


def test_generation_metrics_missing_fields_are_none():
    m = GenerationMetrics.from_ollama_response(
        None, model_name="gemma3:4b", level=2, parent="技術的要因",
        start_time="t0", end_time="t1", elapsed_ms=10,
        success=False, retries=1, error="timeout",
    )
    assert m.prompt_eval_count is None
    assert m.eval_count is None
    assert m.total_duration is None
    assert m.success is False
    assert m.retries == 1
    assert m.error == "timeout"
