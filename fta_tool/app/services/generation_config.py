"""
Feature flags and retry settings for the Ollama generation pipeline (Step 1).

All values are read from environment variables (loaded from fta_tool/.env via
python-dotenv in main.py).  Defaults are chosen so that existing behaviour is
preserved:

  - Structured validation falls back to the legacy normalizer on any error,
    so enabling it cannot break a previously-working response.
  - Metrics logging is purely additive (info-level log lines).
  - Provider-internal retry only triggers on hard failures that previously
    raised an exception, so the success path is unchanged.

Environment variables
---------------------
  ENABLE_STRUCTURED_LLM_OUTPUT          (default: true)
  ENABLE_GENERATION_METRICS             (default: true)
  ENABLE_GENERATION_RETRY               (default: true)
  OLLAMA_GENERATION_MAX_RETRIES         (default: 1)
  OLLAMA_GENERATION_RETRY_DELAY_SECONDS (default: 1)
  OLLAMA_FORMAT_FROM_PYDANTIC           (default: false)
  ENABLE_LANGGRAPH_GENERATION_WORKFLOW  (default: false)
  ENABLE_LANGGRAPH_QUALITY_GATE         (default: false)
  LANGGRAPH_GENERATION_MAX_RETRIES      (default: 1)
  LANGGRAPH_QUALITY_THRESHOLD           (default: 0.7)
"""

import logging
import os

logger = logging.getLogger(__name__)

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _bool_env(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in _TRUTHY


def structured_output_enabled() -> bool:
    """Validate Ollama responses with Pydantic before normalizing (default on)."""
    return _bool_env("ENABLE_STRUCTURED_LLM_OUTPUT", "true")


def metrics_enabled() -> bool:
    """Emit structured generation metrics log lines (default on)."""
    return _bool_env("ENABLE_GENERATION_METRICS", "true")


def retry_enabled() -> bool:
    """Retry Ollama generation on transient/hard failures (default on)."""
    return _bool_env("ENABLE_GENERATION_RETRY", "true")


def langgraph_workflow_enabled() -> bool:
    """Run per-parent generation through the LangGraph workflow (default off).

    Default off so the existing generation path is used unchanged and
    ``langgraph`` is not imported at all.  When on, main.py runs the
    inspect-then-(maybe)-regenerate StateGraph for each parent.
    """
    return _bool_env("ENABLE_LANGGRAPH_GENERATION_WORKFLOW", "false")


def langgraph_quality_gate_enabled() -> bool:
    """Score-based quality gate inside the LangGraph workflow (default off).

    Off: the workflow keeps Step 2-1 behaviour (regenerate only when the
    outcome is all_excluded / no_candidates).  On: candidates whose average
    quality score falls below LANGGRAPH_QUALITY_THRESHOLD also trigger
    regeneration, up to LANGGRAPH_GENERATION_MAX_RETRIES attempts, then
    fail_soft (best attempt is returned with warnings).
    Only meaningful when ENABLE_LANGGRAPH_GENERATION_WORKFLOW is also on.
    """
    return _bool_env("ENABLE_LANGGRAPH_QUALITY_GATE", "false")


def langgraph_quality_threshold() -> float:
    """Quality-gate accept threshold in [0, 1] (default 0.7).

    Compared against the average per-candidate overall_score normalized to
    0–1 (i.e. 0.7 means an average FactorScore of 70/100).
    """
    raw = os.environ.get("LANGGRAPH_QUALITY_THRESHOLD", "0.7")
    try:
        return min(1.0, max(0.0, float(raw)))
    except ValueError:
        logger.warning(
            "LANGGRAPH_QUALITY_THRESHOLD=%r is not a number; using 0.7", raw
        )
        return 0.7


def langgraph_max_retries() -> int:
    """Max quality-gate regenerations in the LangGraph workflow (default 1)."""
    raw = os.environ.get("LANGGRAPH_GENERATION_MAX_RETRIES", "1")
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning(
            "LANGGRAPH_GENERATION_MAX_RETRIES=%r is not an integer; using 1", raw
        )
        return 1


def format_schema_from_pydantic() -> bool:
    """Build the Ollama ``format`` JSON Schema from the Pydantic model.

    Default off so the exact, proven inline schema is sent (safe for older
    Ollama builds).  When on, the Pydantic-derived (ref-free) schema is used,
    with a fallback to the inline schema if derivation fails.
    """
    return _bool_env("OLLAMA_FORMAT_FROM_PYDANTIC", "false")


def get_max_retries() -> int:
    """Max number of *additional* attempts after the first call (default 1)."""
    raw = os.environ.get("OLLAMA_GENERATION_MAX_RETRIES", "1")
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning(
            "OLLAMA_GENERATION_MAX_RETRIES=%r is not an integer; using 1", raw
        )
        return 1


def get_retry_delay_seconds() -> float:
    """Delay between retry attempts in seconds (default 1.0)."""
    raw = os.environ.get("OLLAMA_GENERATION_RETRY_DELAY_SECONDS", "1")
    try:
        return max(0.0, float(raw))
    except ValueError:
        logger.warning(
            "OLLAMA_GENERATION_RETRY_DELAY_SECONDS=%r is not a number; using 1.0", raw
        )
        return 1.0
