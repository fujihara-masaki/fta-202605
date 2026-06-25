"""
Pydantic models for structured LLM output and generation metrics (Step 1).

These models make the raw Ollama response a *validated* structure instead of
something handled purely by ad-hoc string/dict processing.  They are the
foundation for the planned LangGraph "inspect-then-generate" workflow, but no
LangGraph / agent code is introduced here.

  - ``LLMFactor`` / ``LLMFactorList`` validate the factor payload returned by
    the model (Ollama structured output: ``{"factors": [...]}``).
  - ``GenerationMetrics`` captures timing and token information for a single
    generation call so it can be logged and, later, fed into a quality gate.
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Confidence values the model is constrained to (Ollama format schema).
# Unknown values are accepted (kept verbatim) so a slightly off-spec model
# response does not fail validation outright.
CONFIDENCE_LABELS = {
    "high": "可能性高",
    "medium": "可能性あり",
    "low": "念のため確認",
}


class LLMFactor(BaseModel):
    """A single factor as returned by the LLM (pre-conversion).

    Only ``name`` is strictly required.  ``description`` / ``confidence`` are
    given safe defaults so a partially-filled element still validates and can
    be rescued, mirroring the tolerance of the legacy normalizer.
    """

    name: str
    description: str = ""
    confidence: str = "medium"
    # Optional richer fields (forward-looking; not required by current prompts)
    reason: Optional[str] = None
    factor_type: Optional[str] = None

    model_config = {"extra": "ignore"}

    @field_validator("name")
    @classmethod
    def _name_must_be_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must be a non-empty string")
        return v.strip()

    @field_validator("description")
    @classmethod
    def _strip_description(cls, v: str) -> str:
        return (v or "").strip()

    def confidence_label(self) -> str:
        return CONFIDENCE_LABELS.get(self.confidence, self.confidence)


class LLMFactorList(BaseModel):
    """The top-level structured payload: ``{"factors": [LLMFactor, ...]}``."""

    factors: list[LLMFactor] = Field(default_factory=list)
    # Optional fields the model is allowed to return; ignored if absent.
    raw_text: Optional[str] = None
    model_name: Optional[str] = None

    model_config = {"extra": "ignore", "protected_namespaces": ()}


class GenerationMetrics(BaseModel):
    """Timing / token metrics for one Ollama generation call.

    Duration fields hold the raw Ollama nanosecond values when available
    (``None`` when the response does not include them — never an estimate).
    ``elapsed_ms`` is the wall-clock time measured by the client.
    """

    model_config = {"protected_namespaces": ()}

    model_name: str
    level: int
    parent: Optional[str] = None
    start_time: str
    end_time: str
    elapsed_ms: int
    success: bool
    retries: int = 0
    error: Optional[str] = None

    # Raw Ollama metrics (nanoseconds / counts); None when not reported.
    total_duration: Optional[int] = None
    load_duration: Optional[int] = None
    prompt_eval_count: Optional[int] = None
    prompt_eval_duration: Optional[int] = None
    eval_count: Optional[int] = None
    eval_duration: Optional[int] = None

    @classmethod
    def from_ollama_response(
        cls,
        data: Optional[dict],
        *,
        model_name: str,
        level: int,
        parent: Optional[str],
        start_time: str,
        end_time: str,
        elapsed_ms: int,
        success: bool,
        retries: int,
        error: Optional[str] = None,
    ) -> "GenerationMetrics":
        data = data or {}
        return cls(
            model_name=model_name,
            level=level,
            parent=parent,
            start_time=start_time,
            end_time=end_time,
            elapsed_ms=elapsed_ms,
            success=success,
            retries=retries,
            error=error,
            total_duration=data.get("total_duration"),
            load_duration=data.get("load_duration"),
            prompt_eval_count=data.get("prompt_eval_count"),
            prompt_eval_duration=data.get("prompt_eval_duration"),
            eval_count=data.get("eval_count"),
            eval_duration=data.get("eval_duration"),
        )
