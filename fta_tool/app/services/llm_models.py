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

from typing import Literal, Optional

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


# ---------------------------------------------------------------------------
# Ollama structured-output (format) schema
# ---------------------------------------------------------------------------
#
# These STRICT models describe exactly what Ollama is *constrained to emit*
# (sent in the request's ``format`` field).  They are intentionally separate
# from the lenient ``LLMFactor`` above, which is used to *parse* responses and
# tolerates missing/extra fields.  Keeping a strict Pydantic source of truth
# lets a unit test assert the hand-written inline schema has not drifted.


class OllamaStructuredFactor(BaseModel):
    """One factor as the model is constrained to produce it."""

    name: str
    description: str
    confidence: Literal["high", "medium", "low"]


class OllamaStructuredOutput(BaseModel):
    """Top-level structured-output contract: ``{"factors": [...]}``."""

    factors: list[OllamaStructuredFactor]


def _strip_titles(node):
    """Recursively drop Pydantic-added ``title`` keys (noise for Ollama)."""
    if isinstance(node, dict):
        return {k: _strip_titles(v) for k, v in node.items() if k != "title"}
    if isinstance(node, list):
        return [_strip_titles(x) for x in node]
    return node


def ollama_format_schema_from_pydantic() -> dict:
    """Build an Ollama ``format`` JSON Schema from the strict Pydantic model.

    Pydantic emits ``$defs`` + ``$ref`` and ``title`` keys.  Some older Ollama
    builds do not resolve ``$ref``, so the refs are inlined and titles removed,
    producing a flat schema equivalent to the hand-written inline one.
    """
    schema = OllamaStructuredOutput.model_json_schema()
    defs = schema.pop("$defs", {})

    def _resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                ref_name = node["$ref"].split("/")[-1]
                return _resolve(dict(defs[ref_name]))
            return {k: _resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_resolve(x) for x in node]
        return node

    return _strip_titles(_resolve(schema))


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
