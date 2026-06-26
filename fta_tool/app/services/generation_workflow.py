"""
LangGraph inspect-then-(maybe)-regenerate generation workflow (Step 2-1).

Scope (intentionally minimal):
  - Runs for ONE parent factor's worth of generation.
  - generate → evaluate → classify outcome → regenerate ONCE only when the
    outcome is ``all_excluded`` / ``no_candidates`` → finalize.
  - ``created`` / ``partial`` are finalized without regeneration.

What this module does NOT do (stays in main.py):
  - DB access (crud.node_title_exists / crud.create_node), display_order,
    cross-parent aggregation, and the final API response / quality_summary.

Quality judgement is NOT reimplemented here — it reuses the pure functions
extracted in Step 2-0 (``evaluate_candidates`` / ``classify_outcome``).

``langgraph`` is imported at module import time, but this module is itself
imported lazily by main.py only when ENABLE_LANGGRAPH_GENERATION_WORKFLOW is on,
so the default path never imports langgraph.
"""

import logging
from dataclasses import dataclass
from typing import Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from .factor_quality import classify_outcome, evaluate_candidates

logger = logging.getLogger(__name__)


class GenerationState(TypedDict, total=False):
    # --- input context (immutable during a run) ---
    analysis_title: str
    top_event: str
    target_level: int
    parent_factor: Optional[str]
    parent_description: str
    factor_count: int
    existing_titles: list           # same parent/level existing titles
    all_titles: list                # analysis-wide titles (warning detection)
    no_rated_titles: list
    ancestor_factors: list
    analysis_context: dict
    max_retries: int

    # --- working / output ---
    candidates: list                # raw GeneratedFactor candidates (current attempt)
    kept: list                      # quality-kept factor objects
    excluded_quality: int
    reasons: list                   # short exclusion-reason labels
    ai_returned: int
    outcome: str                    # created/partial/all_excluded/no_candidates
    retry_count: int
    regenerated: bool
    error: Optional[str]

    # --- internal: injected provider call (not serialized; in-process only) ---
    # signature: (extra_existing_titles: list[str]) -> list[GeneratedFactor]
    _generate_fn: Callable[[list], list]


# --- nodes ------------------------------------------------------------------

def generate_candidates(state: GenerationState) -> dict:
    """Initial generation: call the provider once (no extra excludes)."""
    fn = state["_generate_fn"]
    try:
        candidates = list(fn([]))
    except Exception as e:  # provider hard-failure (after its own internal retry)
        logger.warning("generation_workflow generate error: %s", e)
        return {"candidates": [], "error": str(e)}
    return {"candidates": candidates}


def evaluate_candidates_node(state: GenerationState) -> dict:
    """Quality-evaluate current candidates (pure, no DB). Reuses Step 2-0."""
    candidates = state.get("candidates", [])
    ev = evaluate_candidates(
        candidates,
        parent_factor=state.get("parent_factor"),
        parent_description=state.get("parent_description", ""),
        existing_titles=state.get("all_titles", []),
        no_rated_titles=state.get("no_rated_titles", []),
        ancestor_titles=state.get("ancestor_factors", []),
    )
    return {
        "kept": [ec.factor for ec in ev.kept],
        "excluded_quality": ev.excluded_quality,
        "reasons": ev.reasons,
        "ai_returned": len(candidates),
    }


def decide_outcome(state: GenerationState) -> dict:
    """Classify the outcome (quality-only; DB dedup is applied later in main.py)."""
    outcome = classify_outcome(
        ai_returned=state.get("ai_returned", 0),
        created=len(state.get("kept", [])),
        excluded=state.get("excluded_quality", 0),
    )
    return {"outcome": outcome}


def regenerate_candidates(state: GenerationState) -> dict:
    """Regenerate once, asking the provider to avoid the first round's titles."""
    fn = state["_generate_fn"]
    excluded_titles = [c.title for c in state.get("candidates", [])]
    next_retry = state.get("retry_count", 0) + 1
    try:
        candidates = list(fn(excluded_titles))
    except Exception as e:
        logger.warning("generation_workflow regenerate error: %s", e)
        return {"regenerated": True, "retry_count": next_retry, "error": str(e)}
    return {"candidates": candidates, "regenerated": True, "retry_count": next_retry}


def finalize_generation_result(state: GenerationState) -> dict:
    """Terminal node — state already holds the final candidates / outcome."""
    return {}


def route_after_decide(state: GenerationState) -> str:
    """created/partial → finalize; all_excluded/no_candidates → regenerate once."""
    if state.get("error"):
        return "finalize"
    if state.get("outcome") in ("created", "partial"):
        return "finalize"
    if state.get("retry_count", 0) < state.get("max_retries", 0):
        return "regenerate"
    return "finalize"


# --- graph build (compiled once) -------------------------------------------

_COMPILED = None


def _build_graph():
    g = StateGraph(GenerationState)
    g.add_node("generate_candidates", generate_candidates)
    g.add_node("evaluate_candidates_node", evaluate_candidates_node)
    g.add_node("decide_outcome", decide_outcome)
    g.add_node("regenerate_candidates", regenerate_candidates)
    g.add_node("finalize_generation_result", finalize_generation_result)

    g.add_edge(START, "generate_candidates")
    g.add_edge("generate_candidates", "evaluate_candidates_node")
    g.add_edge("evaluate_candidates_node", "decide_outcome")
    g.add_conditional_edges(
        "decide_outcome",
        route_after_decide,
        {
            "finalize": "finalize_generation_result",
            "regenerate": "regenerate_candidates",
        },
    )
    g.add_edge("regenerate_candidates", "evaluate_candidates_node")
    g.add_edge("finalize_generation_result", END)
    return g


def get_compiled_graph():
    """Return the compiled StateGraph (built once, reused)."""
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = _build_graph().compile()
    return _COMPILED


@dataclass
class WorkflowResult:
    """Per-parent workflow result handed back to main.py for persistence."""
    candidates: list           # final raw candidates → main.py does dedup + create
    outcome: str               # quality-only outcome (pre-dedup)
    regenerated: bool
    retry_count: int
    error: Optional[str] = None


def run_generation_workflow(
    *,
    generate_fn: Callable[[list], list],
    parent_factor: Optional[str],
    parent_description: str,
    existing_titles: list,
    all_titles: list,
    no_rated_titles: list,
    ancestor_factors: list,
    analysis_context: dict,
    factor_count: int,
    max_retries: int,
    analysis_title: str = "",
    top_event: str = "",
    target_level: int = 0,
) -> WorkflowResult:
    """Run the per-parent workflow and return the final candidates + metadata.

    ``generate_fn(extra_existing)`` is the injected provider call (the same
    closure main.py uses for the legacy path), so the workflow stays decoupled
    from the provider and is trivially mockable in tests.
    """
    graph = get_compiled_graph()
    initial: GenerationState = {
        "analysis_title": analysis_title,
        "top_event": top_event,
        "target_level": target_level,
        "parent_factor": parent_factor,
        "parent_description": parent_description,
        "factor_count": factor_count,
        "existing_titles": list(existing_titles or []),
        "all_titles": list(all_titles or []),
        "no_rated_titles": list(no_rated_titles or []),
        "ancestor_factors": list(ancestor_factors or []),
        "analysis_context": analysis_context or {},
        "max_retries": max_retries,
        "candidates": [],
        "kept": [],
        "excluded_quality": 0,
        "reasons": [],
        "ai_returned": 0,
        "outcome": "",
        "retry_count": 0,
        "regenerated": False,
        "error": None,
        "_generate_fn": generate_fn,
    }
    final = graph.invoke(initial)
    return WorkflowResult(
        candidates=final.get("candidates", []),
        outcome=final.get("outcome", ""),
        regenerated=bool(final.get("regenerated", False)),
        retry_count=int(final.get("retry_count", 0)),
        error=final.get("error"),
    )
