"""
LangGraph inspect-then-(maybe)-regenerate generation workflow (Step 2-1 → 3).

Scope:
  - Runs for ONE parent factor's worth of generation.
  - Node pipeline (Step 3):
        generate_candidates → validate_structure → evaluate_quality
            → decide_next_action →(accept / fail_soft)→ finalize_result
            → decide_next_action →(regenerate)→ regenerate_candidates
                → validate_structure → …  (loop, bounded by max_retries)
  - decide_next_action semantics:
      * quality gate OFF (default): Step 2-1 behaviour — accept when the
        outcome is created/partial, regenerate only for all_excluded /
        no_candidates, fail_soft when the retry budget is spent.
      * quality gate ON: additionally regenerate when the average quality
        score of the kept candidates is below the threshold or a critical
        warning is present; fail_soft returns the BEST attempt so far.

What this module does NOT do (stays in main.py):
  - DB access (crud.node_title_exists / crud.create_node), display_order,
    cross-parent aggregation, and the final API response / quality_summary.

Quality judgement is NOT reimplemented here — it reuses the pure functions
extracted in Step 2-0 (``evaluate_candidates`` / ``classify_outcome``), and
structure validation reuses the Pydantic contract in ``llm_models``.

Regeneration currently replaces the WHOLE candidate list (the provider is
asked to avoid the previous attempt's titles).  The per-attempt records in
``state["attempts"]`` keep each attempt's kept/excluded split, so a future
step can regenerate only the low-quality part without changing the graph
shape (see ``regenerate_candidates``).

``langgraph`` is imported at module import time, but this module is itself
imported lazily by main.py only when ENABLE_LANGGRAPH_GENERATION_WORKFLOW is on,
so the default path never imports langgraph.

Log lines (grep-friendly, for PowerShell-side comparison):
  ``langgraph run start | …``     one per workflow run (flags, thresholds)
  ``langgraph node start | …``    per node execution
  ``langgraph node end | …``      per node execution (elapsed_ms)
  ``langgraph decide | …``        one per decide_next_action pass
  ``langgraph run summary | …``   one per workflow run (final decision etc.)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from . import generation_config
from .factor_quality import classify_outcome, evaluate_candidates
from .llm_models import validate_candidate_structure

logger = logging.getLogger(__name__)

# Terminal decisions produced by decide_next_action.
DECISION_ACCEPT = "accept"
DECISION_REGENERATE = "regenerate"
DECISION_FAIL_SOFT = "fail_soft"


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
    quality_gate: bool              # ENABLE_LANGGRAPH_QUALITY_GATE
    quality_threshold: float        # LANGGRAPH_QUALITY_THRESHOLD (0–1)

    # --- working / output ---
    candidates: list                # raw GeneratedFactor candidates (current attempt)
    kept: list                      # quality-kept factor objects
    excluded_quality: int
    reasons: list                   # short exclusion-reason labels
    ai_returned: int                # provider-returned count (pre structure filter)
    outcome: str                    # created/partial/all_excluded/no_candidates
    retry_count: int
    regenerated: bool
    error: Optional[str]

    # --- Step 3: structure validation result ---
    structure_valid_count: int
    structure_invalid_count: int
    structure_errors: list          # one message per structurally-invalid candidate

    # --- Step 3: quality evaluation / gate ---
    quality_score: float            # avg kept overall_score normalized to 0–1
    warnings: list                  # warning messages (kept candidates + structure)
    warning_count: int
    has_critical_warning: bool      # nothing usable in this attempt
    decision: str                   # accept / regenerate / fail_soft
    attempts: list                  # per-attempt records (for fail_soft best pick)
    node_timings: list              # [(node_name, elapsed_ms), …] in execution order

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


def validate_structure(state: GenerationState) -> dict:
    """Pydantic structure check on the current candidates (never raises).

    Structurally-invalid candidates (empty title, wrong field types, …) are
    dropped before quality evaluation; each rejection becomes a warning
    message.  ``ai_returned`` records the pre-filter count so an
    all-invalid attempt classifies as ``all_excluded`` (not ``no_candidates``).
    """
    candidates = state.get("candidates", [])
    valid, errors = validate_candidate_structure(candidates)
    if errors:
        logger.warning(
            "langgraph structure invalid | invalid=%d/%d errors=%s",
            len(errors), len(candidates), "; ".join(errors),
        )
    return {
        "candidates": valid,
        "ai_returned": len(candidates),
        "structure_valid_count": len(valid),
        "structure_invalid_count": len(errors),
        "structure_errors": errors,
    }


def evaluate_quality(state: GenerationState) -> dict:
    """Quality-evaluate current candidates (pure, no DB). Reuses Step 2-0.

    Computes the kept/excluded split, the normalized average quality score,
    the warning list (kept-candidate warnings + structure errors), the
    outcome classification and the critical-warning flag, and appends a
    per-attempt record used by fail_soft to pick the best attempt.
    """
    candidates = state.get("candidates", [])
    ev = evaluate_candidates(
        candidates,
        parent_factor=state.get("parent_factor"),
        parent_description=state.get("parent_description", ""),
        existing_titles=state.get("all_titles", []),
        no_rated_titles=state.get("no_rated_titles", []),
        ancestor_titles=state.get("ancestor_factors", []),
    )
    kept = [ec.factor for ec in ev.kept]
    scores = ev.scores  # per-kept overall_score, 0–100
    quality_score = (sum(scores) / len(scores) / 100.0) if scores else 0.0

    warnings: list = list(state.get("structure_errors") or [])
    for ec in ev.kept:
        warnings.extend(ec.warnings)

    ai_returned = state.get("ai_returned", len(candidates))
    outcome = classify_outcome(
        ai_returned=ai_returned,
        created=len(kept),
        excluded=ev.excluded_quality,
    )
    # Critical = nothing usable came out of this attempt (all rejected by the
    # structure/quality checks, or the provider returned no candidates).
    has_critical = outcome in ("all_excluded", "no_candidates")

    attempt_record = {
        "attempt": state.get("retry_count", 0),
        "candidates": candidates,
        "kept_count": len(kept),
        "quality_score": quality_score,
        "warnings": warnings,
        "outcome": outcome,
    }
    return {
        "kept": kept,
        "excluded_quality": ev.excluded_quality,
        "reasons": ev.reasons,
        "quality_score": quality_score,
        "warnings": warnings,
        "warning_count": len(warnings),
        "has_critical_warning": has_critical,
        "outcome": outcome,
        "attempts": list(state.get("attempts") or []) + [attempt_record],
    }


def decide_next_action(state: GenerationState) -> dict:
    """Decide accept / regenerate / fail_soft from the current attempt.

    Gate OFF (default): Step 2-1 semantics — created/partial is accepted
    as-is; only all_excluded/no_candidates spends the retry budget.
    Gate ON: a below-threshold average score or a critical warning also
    triggers regeneration; when the budget is spent the run fail_softs.
    """
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 0)
    gate = bool(state.get("quality_gate", False))
    threshold = float(state.get("quality_threshold", 0.7))
    quality_score = float(state.get("quality_score", 0.0))
    has_critical = bool(state.get("has_critical_warning", False))
    outcome = state.get("outcome", "")

    if state.get("error"):
        decision = DECISION_FAIL_SOFT
    elif gate:
        if not has_critical and quality_score >= threshold:
            decision = DECISION_ACCEPT
        elif retry_count < max_retries:
            decision = DECISION_REGENERATE
        else:
            decision = DECISION_FAIL_SOFT
    else:
        if outcome in ("created", "partial"):
            decision = DECISION_ACCEPT
        elif retry_count < max_retries:
            decision = DECISION_REGENERATE
        else:
            decision = DECISION_FAIL_SOFT

    logger.info(
        "langgraph decide | decision=%s outcome=%s quality_gate=%s "
        "quality_score=%.2f threshold=%.2f warnings=%d critical=%s "
        "retry_count=%d max_retries=%d",
        decision, outcome, gate, quality_score, threshold,
        state.get("warning_count", 0), has_critical, retry_count, max_retries,
    )
    return {"decision": decision}


def regenerate_candidates(state: GenerationState) -> dict:
    """Regenerate, asking the provider to avoid this attempt's titles.

    Currently regenerates the whole candidate list.  Partial regeneration
    (keep the high-scoring kept candidates, regenerate only the shortfall) can
    be added here later by seeding ``candidates`` with the kept subset and
    shrinking the requested count — the graph shape does not change.
    """
    fn = state["_generate_fn"]
    excluded_titles = [c.title for c in state.get("candidates", [])]
    next_retry = state.get("retry_count", 0) + 1
    try:
        candidates = list(fn(excluded_titles))
    except Exception as e:
        logger.warning("generation_workflow regenerate error: %s", e)
        return {"regenerated": True, "retry_count": next_retry, "error": str(e)}
    return {"candidates": candidates, "regenerated": True, "retry_count": next_retry}


def finalize_result(state: GenerationState) -> dict:
    """Fix the final decision and, on fail_soft, restore the best attempt.

    ``fail_soft`` never raises: it hands back the attempt with the most kept
    candidates (score as tie-break, later attempts win ties) so main.py can
    persist it as a normal warning-carrying result.
    """
    decision = state.get("decision") or (
        DECISION_FAIL_SOFT if state.get("error") else DECISION_ACCEPT
    )
    updates: dict = {"decision": decision}
    attempts = state.get("attempts") or []
    if decision == DECISION_FAIL_SOFT and attempts:
        best = max(
            attempts,
            key=lambda a: (a["kept_count"], a["quality_score"], a["attempt"]),
        )
        if best["attempt"] != state.get("retry_count", 0):
            logger.info(
                "langgraph fail_soft best attempt | using attempt=%d "
                "kept=%d quality_score=%.2f (current attempt=%d)",
                best["attempt"], best["kept_count"], best["quality_score"],
                state.get("retry_count", 0),
            )
            updates.update({
                "candidates": best["candidates"],
                "quality_score": best["quality_score"],
                "warnings": best["warnings"],
                "warning_count": len(best["warnings"]),
                "outcome": best["outcome"],
                "has_critical_warning": best["outcome"]
                in ("all_excluded", "no_candidates"),
            })
    return updates


def route_after_decide(state: GenerationState) -> str:
    """regenerate → regenerate_candidates; accept / fail_soft → finalize."""
    if state.get("decision") == DECISION_REGENERATE and not state.get("error"):
        return "regenerate"
    return "finalize"


# --- node wrapper: start/end logging + per-node timing + exception guard ----

def _instrumented(name: str, fn: Callable[[GenerationState], dict]):
    """Wrap a node with start/end logs, timing, and an exception guard.

    A node bug must not kill the whole generation request: any unexpected
    exception is converted into ``error`` state (routed to finalize →
    fail_soft) instead of propagating out of ``graph.invoke``.
    """
    def wrapped(state: GenerationState) -> dict:
        attempt = state.get("retry_count", 0)
        logger.info("langgraph node start | node=%s attempt=%d", name, attempt)
        t0 = time.perf_counter()
        try:
            updates = fn(state)
        except Exception as e:
            logger.warning("langgraph node error | node=%s: %s", name, e)
            updates = {"error": str(e)}
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "langgraph node end | node=%s attempt=%d elapsed_ms=%d",
            name, attempt, elapsed_ms,
        )
        timings = list(state.get("node_timings") or [])
        timings.append((name, elapsed_ms))
        updates["node_timings"] = timings
        return updates

    return wrapped


# --- graph build (compiled once) -------------------------------------------

_COMPILED = None


def _build_graph():
    g = StateGraph(GenerationState)
    g.add_node("generate_candidates", _instrumented("generate_candidates", generate_candidates))
    g.add_node("validate_structure", _instrumented("validate_structure", validate_structure))
    g.add_node("evaluate_quality", _instrumented("evaluate_quality", evaluate_quality))
    g.add_node("decide_next_action", _instrumented("decide_next_action", decide_next_action))
    g.add_node("regenerate_candidates", _instrumented("regenerate_candidates", regenerate_candidates))
    g.add_node("finalize_result", _instrumented("finalize_result", finalize_result))

    g.add_edge(START, "generate_candidates")
    g.add_edge("generate_candidates", "validate_structure")
    g.add_edge("validate_structure", "evaluate_quality")
    g.add_edge("evaluate_quality", "decide_next_action")
    g.add_conditional_edges(
        "decide_next_action",
        route_after_decide,
        {
            "finalize": "finalize_result",
            "regenerate": "regenerate_candidates",
        },
    )
    g.add_edge("regenerate_candidates", "validate_structure")
    g.add_edge("finalize_result", END)
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
    # Step 3 fields (additive)
    decision: str = ""                      # accept / regenerate / fail_soft
    quality_score: float = 0.0              # 0–1 (avg kept overall_score / 100)
    warning_count: int = 0
    has_critical_warning: bool = False
    node_timings: list = field(default_factory=list)   # [(node, ms), …]


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
    quality_gate: Optional[bool] = None,
    quality_threshold: Optional[float] = None,
) -> WorkflowResult:
    """Run the per-parent workflow and return the final candidates + metadata.

    ``generate_fn(extra_existing)`` is the injected provider call (the same
    closure main.py uses for the legacy path), so the workflow stays decoupled
    from the provider and is trivially mockable in tests.

    ``quality_gate`` / ``quality_threshold`` default to the environment
    configuration (ENABLE_LANGGRAPH_QUALITY_GATE / LANGGRAPH_QUALITY_THRESHOLD)
    when not passed explicitly.
    """
    if quality_gate is None:
        quality_gate = generation_config.langgraph_quality_gate_enabled()
    if quality_threshold is None:
        quality_threshold = generation_config.langgraph_quality_threshold()

    logger.info(
        "langgraph run start | quality_gate=%s threshold=%.2f max_retries=%d "
        "level=%d parent=%r",
        quality_gate, quality_threshold, max_retries,
        target_level, parent_factor or "(top event)",
    )
    t_run = time.perf_counter()

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
        "quality_gate": bool(quality_gate),
        "quality_threshold": float(quality_threshold),
        "candidates": [],
        "kept": [],
        "excluded_quality": 0,
        "reasons": [],
        "ai_returned": 0,
        "outcome": "",
        "retry_count": 0,
        "regenerated": False,
        "error": None,
        "structure_valid_count": 0,
        "structure_invalid_count": 0,
        "structure_errors": [],
        "quality_score": 0.0,
        "warnings": [],
        "warning_count": 0,
        "has_critical_warning": False,
        "decision": "",
        "attempts": [],
        "node_timings": [],
        "_generate_fn": generate_fn,
    }
    final = graph.invoke(initial)

    elapsed_ms = int((time.perf_counter() - t_run) * 1000)
    node_timings = list(final.get("node_timings") or [])
    logger.info(
        "langgraph run summary | decision=%s outcome=%s quality_gate=%s "
        "quality_score=%.2f warnings=%d critical=%s regenerated=%s "
        "retry_count=%d elapsed_ms=%d node_ms=%s",
        final.get("decision", ""), final.get("outcome", ""), quality_gate,
        final.get("quality_score", 0.0), final.get("warning_count", 0),
        final.get("has_critical_warning", False),
        bool(final.get("regenerated", False)), int(final.get("retry_count", 0)),
        elapsed_ms, ",".join(f"{n}:{ms}" for n, ms in node_timings),
    )
    return WorkflowResult(
        candidates=final.get("candidates", []),
        outcome=final.get("outcome", ""),
        regenerated=bool(final.get("regenerated", False)),
        retry_count=int(final.get("retry_count", 0)),
        error=final.get("error"),
        decision=final.get("decision", ""),
        quality_score=float(final.get("quality_score", 0.0)),
        warning_count=int(final.get("warning_count", 0)),
        has_critical_warning=bool(final.get("has_critical_warning", False)),
        node_timings=node_timings,
    )
