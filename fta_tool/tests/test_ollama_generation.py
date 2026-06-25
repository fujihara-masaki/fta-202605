"""
Tests for the Step 1 Ollama generation pipeline:
structured-output validation, provider-internal retry, fallback, and metrics.

The actual HTTP call (OllamaProvider._post_chat) is mocked so no Ollama server
is needed.
"""

import json

import pytest

from app.services import generation_config
from app.services.ai_provider import GeneratedFactor, OllamaGenerationError, OllamaProvider


GOOD_CONTENT = json.dumps({
    "factors": [
        {"name": "認証サーバの障害", "description": "認証ログにエラーが記録されているか確認する", "confidence": "high"},
        {"name": "ネットワーク経路の問題", "description": "ping/tracerouteで疎通を確認する", "confidence": "medium"},
    ]
})


def _fake_response(content: str) -> dict:
    """Build a minimal Ollama /api/chat response dict."""
    return {
        "model": "gemma3:4b",
        "message": {"content": content},
        "total_duration": 1_000_000_000,
        "load_duration": 100_000_000,
        "prompt_eval_count": 100,
        "prompt_eval_duration": 200_000_000,
        "eval_count": 200,
        "eval_duration": 700_000_000,
    }


class _PostChatStub:
    """Replaces OllamaProvider._post_chat with a scripted sequence.

    Each item in *script* is either a string (returned as response content) or
    an OllamaGenerationError instance (raised).
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.last_payload = None

    def __call__(self, payload, *, level, parent):
        self.calls += 1
        self.last_payload = payload
        item = self.script.pop(0)
        if isinstance(item, OllamaGenerationError):
            raise item
        return _fake_response(item)


def _make_provider(monkeypatch):
    # Keep retries fast and deterministic.
    monkeypatch.setenv("OLLAMA_GENERATION_RETRY_DELAY_SECONDS", "0")
    return OllamaProvider()


def _generate(provider):
    return provider.generate_factors(
        analysis_title="テスト分析",
        top_event="ログイン障害が発生した",
        target_level=1,
        parent_path=[],
        parent_factor=None,
        context={"factor_count": 4},
    )


# --- structured validation --------------------------------------------------

def test_extract_validated_structured_success():
    factors = OllamaProvider._extract_factors_validated(GOOD_CONTENT, level=1, parent=None)
    assert len(factors) == 2
    assert factors[0].title == "認証サーバの障害"
    assert "可能性高" in factors[0].rationale


def test_extract_validated_includes_reason_and_type():
    content = json.dumps({"factors": [
        {"name": "DNSの不調", "description": "名前解決の失敗を確認する",
         "confidence": "high", "reason": "直前にDNS遅延", "factor_type": "技術要因"},
    ]})
    factors = OllamaProvider._extract_factors_validated(content, level=1, parent=None)
    assert factors[0].rationale.startswith("直前にDNS遅延")
    assert "技術要因" in factors[0].rationale


def test_extract_validated_falls_back_for_list_str():
    """list[str] fails Pydantic validation but is rescued by the legacy path."""
    content = json.dumps(["候補A", "候補B"])
    factors = OllamaProvider._extract_factors_validated(content, level=1, parent=None)
    assert [f.title for f in factors] == ["候補A", "候補B"]
    assert factors[0].description == OllamaProvider._STR_RESCUE_DESCRIPTION


def test_extract_validated_falls_back_when_structured_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_STRUCTURED_LLM_OUTPUT", "false")
    assert generation_config.structured_output_enabled() is False
    factors = OllamaProvider._extract_factors_validated(GOOD_CONTENT, level=1, parent=None)
    assert len(factors) == 2  # legacy normalizer handles the compact format too


def test_extract_validated_empty_content_raises():
    with pytest.raises(OllamaGenerationError) as exc:
        OllamaProvider._extract_factors_validated("   ", level=1, parent=None)
    assert exc.value.kind == "empty_response"


def test_extract_validated_invalid_json_raises():
    with pytest.raises(OllamaGenerationError) as exc:
        OllamaProvider._extract_factors_validated("not json", level=1, parent=None)
    assert exc.value.kind == "json_parse"


# --- retry behaviour --------------------------------------------------------

def test_retry_on_json_parse_then_success(monkeypatch):
    monkeypatch.setenv("ENABLE_GENERATION_RETRY", "true")
    monkeypatch.setenv("OLLAMA_GENERATION_MAX_RETRIES", "1")
    provider = _make_provider(monkeypatch)
    stub = _PostChatStub(["これはJSONではない", GOOD_CONTENT])
    monkeypatch.setattr(provider, "_post_chat", stub)

    factors = _generate(provider)
    assert stub.calls == 2
    assert len(factors) == 2


def test_retry_on_zero_factors_then_success(monkeypatch):
    monkeypatch.setenv("ENABLE_GENERATION_RETRY", "true")
    monkeypatch.setenv("OLLAMA_GENERATION_MAX_RETRIES", "1")
    provider = _make_provider(monkeypatch)
    empty = json.dumps({"factors": []})
    stub = _PostChatStub([empty, GOOD_CONTENT])
    monkeypatch.setattr(provider, "_post_chat", stub)

    factors = _generate(provider)
    assert stub.calls == 2
    assert len(factors) == 2


def test_retry_exhausted_raises(monkeypatch):
    monkeypatch.setenv("ENABLE_GENERATION_RETRY", "true")
    monkeypatch.setenv("OLLAMA_GENERATION_MAX_RETRIES", "1")
    provider = _make_provider(monkeypatch)
    stub = _PostChatStub(["bad json", "still bad"])
    monkeypatch.setattr(provider, "_post_chat", stub)

    with pytest.raises(RuntimeError):  # OllamaGenerationError is a RuntimeError
        _generate(provider)
    assert stub.calls == 2  # 1 initial + 1 retry, not more


def test_retry_count_does_not_exceed_setting(monkeypatch):
    monkeypatch.setenv("ENABLE_GENERATION_RETRY", "true")
    monkeypatch.setenv("OLLAMA_GENERATION_MAX_RETRIES", "2")
    provider = _make_provider(monkeypatch)
    stub = _PostChatStub(["bad", "bad", "bad", "bad"])
    monkeypatch.setattr(provider, "_post_chat", stub)

    with pytest.raises(RuntimeError):
        _generate(provider)
    assert stub.calls == 3  # 1 initial + 2 retries


def test_retry_disabled_no_retry(monkeypatch):
    monkeypatch.setenv("ENABLE_GENERATION_RETRY", "false")
    monkeypatch.setenv("OLLAMA_GENERATION_MAX_RETRIES", "5")
    provider = _make_provider(monkeypatch)
    stub = _PostChatStub(["bad", GOOD_CONTENT])
    monkeypatch.setattr(provider, "_post_chat", stub)

    with pytest.raises(RuntimeError):
        _generate(provider)
    assert stub.calls == 1  # no retry when disabled


def test_validation_error_triggers_retry_then_fallback_success(monkeypatch):
    """A validation failure is retryable; the retry succeeds with good data."""
    monkeypatch.setenv("ENABLE_GENERATION_RETRY", "true")
    monkeypatch.setenv("OLLAMA_GENERATION_MAX_RETRIES", "1")
    provider = _make_provider(monkeypatch)
    # First: object with no usable list → normalizer raises → retryable.
    bad = json.dumps({"message": "error", "code": 500})
    stub = _PostChatStub([bad, GOOD_CONTENT])
    monkeypatch.setattr(provider, "_post_chat", stub)

    factors = _generate(provider)
    assert stub.calls == 2
    assert all(isinstance(f, GeneratedFactor) for f in factors)


# --- format (JSON Schema) is sent to Ollama ---------------------------------

def test_payload_includes_json_schema_format(monkeypatch):
    """The request payload carries a JSON Schema in `format` (not format='json')."""
    provider = _make_provider(monkeypatch)
    stub = _PostChatStub([GOOD_CONTENT])
    monkeypatch.setattr(provider, "_post_chat", stub)

    _generate(provider)

    fmt = stub.last_payload["format"]
    assert isinstance(fmt, dict)  # a JSON Schema object, not the string "json"
    assert fmt["type"] == "object"
    assert fmt["required"] == ["factors"]
    item = fmt["properties"]["factors"]["items"]
    assert set(item["required"]) == {"name", "description", "confidence"}


def test_payload_format_from_pydantic_when_enabled(monkeypatch):
    monkeypatch.setenv("OLLAMA_FORMAT_FROM_PYDANTIC", "true")
    provider = _make_provider(monkeypatch)
    stub = _PostChatStub([GOOD_CONTENT])
    monkeypatch.setattr(provider, "_post_chat", stub)

    _generate(provider)

    fmt = stub.last_payload["format"]
    assert fmt is not OllamaProvider._FORMAT_SCHEMA
    assert fmt["required"] == ["factors"]


# --- metrics ----------------------------------------------------------------

def test_metrics_logged_on_success(monkeypatch, caplog):
    monkeypatch.setenv("ENABLE_GENERATION_METRICS", "true")
    provider = _make_provider(monkeypatch)
    stub = _PostChatStub([GOOD_CONTENT])
    monkeypatch.setattr(provider, "_post_chat", stub)

    with caplog.at_level("INFO"):
        _generate(provider)

    metrics_lines = [r.message for r in caplog.records if "generation_metrics" in r.message]
    assert metrics_lines, "expected a generation_metrics log line"
    assert "prompt_eval_count" in metrics_lines[0]
    assert "eval_count" in metrics_lines[0]
    success_lines = [r.message for r in caplog.records if "generation_success" in r.message]
    assert success_lines


def test_metrics_can_be_disabled(monkeypatch, caplog):
    monkeypatch.setenv("ENABLE_GENERATION_METRICS", "false")
    provider = _make_provider(monkeypatch)
    stub = _PostChatStub([GOOD_CONTENT])
    monkeypatch.setattr(provider, "_post_chat", stub)

    with caplog.at_level("INFO"):
        _generate(provider)

    assert not [r for r in caplog.records if "generation_metrics" in r.message]
