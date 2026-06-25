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
