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
      * quality gate ON (Step 3.5 graded decisions):
          accept              — no critical candidate, score >= threshold,
                                no warnings
          accept_with_warning — minor warnings only, OR the retry budget is
                                spent and usable (non-critical) candidates
                                remain; critical candidates are dropped
                                (reported in ``rejected``)
          regenerate (retry)  — a critical candidate exists (parent
                                paraphrase, ancestor reversion, near-duplicate,
                                No-rated similar) or the average score is
                                below the threshold, and budget remains;
                                only the problematic part is regenerated
          reject              — budget spent and no usable candidate remains
        Critical = per-candidate severity from factor_quality (paraphrase /
        ancestor reversion / near-duplicate / No-rated similar).  Generic
        token overlap (DNS, VPN, …) is never critical — warning only.

What this module does NOT do (stays in main.py):
  - DB access (crud.node_title_exists / crud.create_node), display_order,
    cross-parent aggregation, and the final API response / quality_summary.

Quality judgement is NOT reimplemented here — it reuses the pure functions
extracted in Step 2-0 (``evaluate_candidates`` / ``classify_outcome``), and
structure validation reuses the Pydantic contract in ``llm_models``.

Regeneration (Step 3.5): with the quality gate ON, only the problematic part
is regenerated — usable candidates (``regen_keep``) are carried over and the
shortfall is filled from the provider's answer.  With the gate OFF the whole
candidate list is regenerated (Step 2-1 behaviour, unchanged).  The
per-attempt records in ``state["attempts"]`` keep each attempt's
kept/excluded split so finalize can adopt the usable part of the best
attempt (see ``regenerate_candidates`` / ``finalize_result``).

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
from .factor_quality import (
    SEVERITY_CRITICAL,
    SEVERITY_OK,
    SEVERITY_WARNING,
    classify_outcome,
    evaluate_candidates,
)
from .llm_models import validate_candidate_structure

logger = logging.getLogger(__name__)

# Decisions produced by decide_next_action.
# ``regenerate`` is the transient "retry" decision (routes back into the
# loop); the others are terminal.  ``fail_soft`` remains the terminal state
# for provider/node errors (gate ON and OFF) and for the gate-OFF budget-spent
# case, unchanged from Step 3.
DECISION_ACCEPT = "accept"
DECISION_ACCEPT_WITH_WARNING = "accept_with_warning"
DECISION_REGENERATE = "regenerate"
DECISION_REJECT = "reject"
DECISION_FAIL_SOFT = "fail_soft"


class GenerationState(TypedDict, total=False):
    # --- input context (immutable during a run) ---
    analysis_title: str
    top_event: str
    target_level: int
    parent_id: Optional[int]        # DB id of the parent node (log correlation)
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
    decision: str                   # accept / accept_with_warning / regenerate / reject / fail_soft
    attempts: list                  # per-attempt records (for fail_soft best pick)
    node_timings: list              # [(node_name, elapsed_ms), …] in execution order

    # --- Step 3.5: graded gate / partial regeneration ---
    severity: str                   # attempt severity: ok / warning / critical
    critical_count: int             # per-candidate critical findings (this attempt)
    critical_items: list            # [{"title":…, "reasons":[…]}, …] (this attempt)
    regen_keep: list                # factor objects kept as-is on partial regen
    regen_added_titles: list        # titles introduced by any regeneration
    decision_basis: str             # "pass" / "budget_spent" / "" (why decided)
    rejected: list                  # final rejected candidates (critical, budget spent)
    regenerated_titles: list        # final candidates that came from a regeneration

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

    structure_errors: list = list(state.get("structure_errors") or [])
    warnings: list = list(structure_errors)
    for ec in ev.kept:
        warnings.extend(ec.warnings)

    # --- Step 3.5: per-candidate severity split (quality gate) -------------
    # critical = excluded (paraphrase / same description / No-rated similar)
    # or kept-with-critical-warning (ancestor reversion / near-duplicate of an
    # existing factor).  These are the gate's regeneration targets; generic
    # token overlap and other minor findings stay "warning".
    threshold = float(state.get("quality_threshold", 0.7))
    kept_noncritical = [ec for ec in ev.kept if ec.severity != SEVERITY_CRITICAL]
    kept_critical = [ec for ec in ev.kept if ec.severity == SEVERITY_CRITICAL]
    critical_items = [
        {
            "title": ec.factor.title,
            "reasons": list(ec.critical_reasons)
            or [ec.reason_label or "品質チェックにより除外"],
        }
        for ec in kept_critical + list(ev.excluded)
    ]
    critical_count = len(critical_items)
    if critical_count:
        severity = SEVERITY_CRITICAL
    elif warnings:
        severity = SEVERITY_WARNING
    else:
        severity = SEVERITY_OK
    # Candidates kept as-is when a partial regeneration is triggered:
    # non-critical AND individually at/above the score threshold.
    regen_keep = [
        ec.factor for ec in kept_noncritical
        if ec.score.overall_score >= threshold * 100.0
    ]
    noncritical_warnings = list(structure_errors)
    for ec in kept_noncritical:
        noncritical_warnings.extend(ec.warnings)

    # One grep-friendly line per candidate (PowerShell-side comparison).
    attempt = state.get("retry_count", 0)
    for ec in list(ev.kept) + list(ev.excluded):
        logger.info(
            "langgraph candidate | parent_id=%s level=%d parent=%r attempt=%d "
            "title=%r score=%d severity=%s excluded=%s warnings=%r "
            "critical_reasons=%r",
            state.get("parent_id"), state.get("target_level", 0),
            state.get("parent_factor") or "(top event)", attempt,
            ec.factor.title, ec.score.overall_score, ec.severity, ec.excluded,
            "; ".join(ec.warnings), "; ".join(ec.critical_reasons),
        )

    ai_returned = state.get("ai_returned", len(candidates))
    outcome = classify_outcome(
        ai_returned=ai_returned,
        created=len(kept),
        excluded=ev.excluded_quality,
    )
    # Critical = nothing usable came out of this attempt (all rejected by the
    # structure/quality checks, or the provider returned no candidates).
    has_critical = outcome in ("all_excluded", "no_candidates")

    # Per-attempt record. Besides what fail_soft needs to pick the best
    # attempt, it keeps the kept/excluded split (titles + exclusion-reason
    # labels) and the non-critical subset, so finalize_result can adopt only
    # the usable part of the best attempt.
    attempt_record = {
        "attempt": state.get("retry_count", 0),
        "candidates": candidates,
        "ai_returned": ai_returned,
        "kept_count": len(kept),
        "kept_titles": [ec.factor.title for ec in ev.kept],
        "excluded_titles": [ec.factor.title for ec in ev.excluded],
        "reasons": list(ev.reasons),
        "quality_score": quality_score,
        "warnings": warnings,
        "warning_count": len(warnings),
        "outcome": outcome,
        # Step 3.5 fields
        "severity": severity,
        "critical_items": critical_items,
        "kept_noncritical": [ec.factor for ec in kept_noncritical],
        "kept_noncritical_count": len(kept_noncritical),
        "noncritical_warnings": noncritical_warnings,
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
        "severity": severity,
        "critical_count": critical_count,
        "critical_items": critical_items,
        "regen_keep": regen_keep,
        "attempts": list(state.get("attempts") or []) + [attempt_record],
    }


def decide_next_action(state: GenerationState) -> dict:
    """Decide the next action from the current attempt.

    Gate OFF (default): Step 2-1 semantics — created/partial is accepted
    as-is; only all_excluded/no_candidates spends the retry budget; the
    budget-spent terminal stays ``fail_soft``.

    Gate ON (graded, Step 3.5):
      - no critical candidate and score >= threshold
            → ``accept`` (or ``accept_with_warning`` when minor warnings exist)
      - a critical candidate exists (parent paraphrase / ancestor reversion /
        near-duplicate / No-rated similar) or the score is below the
        threshold, and budget remains
            → ``regenerate`` (retry; only the problematic part is replaced)
      - budget spent
            → ``accept_with_warning`` when a usable (non-critical) candidate
              exists in any attempt (criticals are dropped in finalize),
              otherwise ``reject``
    """
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 0)
    gate = bool(state.get("quality_gate", False))
    threshold = float(state.get("quality_threshold", 0.7))
    quality_score = float(state.get("quality_score", 0.0))
    has_critical = bool(state.get("has_critical_warning", False))
    critical_count = int(state.get("critical_count", 0))
    severity = state.get("severity", "")
    warning_count = int(state.get("warning_count", 0))
    outcome = state.get("outcome", "")
    basis = ""

    if state.get("error"):
        decision = DECISION_FAIL_SOFT
    elif gate:
        if critical_count == 0 and quality_score >= threshold:
            basis = "pass"
            decision = (
                DECISION_ACCEPT_WITH_WARNING if warning_count
                else DECISION_ACCEPT
            )
        elif retry_count < max_retries:
            decision = DECISION_REGENERATE
        else:
            basis = "budget_spent"
            usable = any(
                a.get("kept_noncritical_count", 0) > 0
                for a in (state.get("attempts") or [])
            )
            decision = (
                DECISION_ACCEPT_WITH_WARNING if usable else DECISION_REJECT
            )
    else:
        if outcome in ("created", "partial"):
            decision = DECISION_ACCEPT
        elif retry_count < max_retries:
            decision = DECISION_REGENERATE
        else:
            decision = DECISION_FAIL_SOFT

    logger.info(
        "langgraph decide | decision=%s basis=%s severity=%s outcome=%s "
        "quality_gate=%s quality_score=%.2f threshold=%.2f warnings=%d "
        "critical_count=%d critical=%s retry_count=%d max_retries=%d",
        decision, basis or "-", severity or "-", outcome, gate,
        quality_score, threshold, warning_count,
        critical_count, has_critical, retry_count, max_retries,
    )
    return {"decision": decision, "decision_basis": basis}


def regenerate_candidates(state: GenerationState) -> dict:
    """Regenerate, asking the provider to avoid this attempt's titles.

    Gate OFF: whole-list regeneration (Step 2-1 behaviour, unchanged).

    Gate ON (partial regeneration): the current attempt's usable candidates
    (``regen_keep``: non-critical AND individually at/above the threshold)
    are carried over as-is; the provider is asked to avoid ALL current titles
    and only the shortfall is taken from its answer, so a single bad candidate
    does not cost a full re-generation of the good ones.
    """
    fn = state["_generate_fn"]
    avoid_titles = [c.title for c in state.get("candidates", [])]
    next_retry = state.get("retry_count", 0) + 1
    gate = bool(state.get("quality_gate", False))

    if not gate:
        try:
            candidates = list(fn(avoid_titles))
        except Exception as e:
            logger.warning("generation_workflow regenerate error: %s", e)
            return {"regenerated": True, "retry_count": next_retry, "error": str(e)}
        return {"candidates": candidates, "regenerated": True, "retry_count": next_retry}

    # --- gate ON: partial regeneration ---
    keep = list(state.get("regen_keep") or [])
    keep_titles = {c.title for c in keep}
    problem_titles = [t for t in avoid_titles if t not in keep_titles]
    try:
        new_candidates = list(fn(avoid_titles))
    except Exception as e:
        logger.warning("generation_workflow regenerate error: %s", e)
        return {"regenerated": True, "retry_count": next_retry, "error": str(e)}
    fresh = [c for c in new_candidates if c.title not in keep_titles]
    factor_count = int(state.get("factor_count", 0) or 0)
    if factor_count > 0:
        fresh = fresh[: max(1, factor_count - len(keep))]
    added_titles = [c.title for c in fresh]
    # before/after in one line for PowerShell-side comparison.
    logger.info(
        "langgraph regen partial | parent_id=%s level=%d parent=%r attempt=%d "
        "kept=%r before=%r after=%r",
        state.get("parent_id"), state.get("target_level", 0),
        state.get("parent_factor") or "(top event)", next_retry,
        "; ".join(c.title for c in keep),
        "; ".join(problem_titles), "; ".join(added_titles),
    )
    return {
        "candidates": keep + fresh,
        "regenerated": True,
        "retry_count": next_retry,
        "regen_added_titles":
            list(state.get("regen_added_titles") or []) + added_titles,
    }


def finalize_result(state: GenerationState) -> dict:
    """Fix the final decision and, on fail_soft, restore the best attempt.

    ``fail_soft`` never raises: it hands back the attempt with the most kept
    candidates (score as tie-break, later attempts win ties) so main.py can
    persist it as a normal warning-carrying result.

    Error semantics (contract with main.py):
      - ``error`` survives to the WorkflowResult ONLY when no attempt produced
        a usable (quality-kept) candidate — i.e. generation itself failed.
        main.py then falls back to the legacy path.
      - If an error occurred (e.g. the provider died during regeneration) but
        an earlier attempt DID keep candidates, the error is cleared here and
        the run ends as a normal fail_soft result with that best attempt, so
        main.py does not regenerate from scratch.
    """
    decision = state.get("decision") or (
        DECISION_FAIL_SOFT if state.get("error") else DECISION_ACCEPT
    )
    updates: dict = {"decision": decision}
    attempts = state.get("attempts") or []
    if state.get("error") and any(a["kept_count"] > 0 for a in attempts):
        logger.info(
            "langgraph error recovered as fail_soft | error=%r "
            "(a usable earlier attempt exists; legacy fallback not needed)",
            state.get("error"),
        )
        updates["error"] = None
        decision = DECISION_FAIL_SOFT
        updates["decision"] = decision
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

    # --- Step 3.5: gate-ON terminal decisions adopt only usable candidates ---
    # accept / accept_with_warning / reject: the final candidate list is the
    # non-critical subset of the chosen attempt; its critical candidates are
    # dropped and reported in ``rejected`` (with reasons) instead of being
    # persisted as warning-carrying nodes.
    gate = bool(state.get("quality_gate", False))
    if gate and not updates.get("error", state.get("error")) and attempts and \
            decision in (DECISION_ACCEPT, DECISION_ACCEPT_WITH_WARNING,
                         DECISION_REJECT):
        if state.get("decision_basis") == "budget_spent":
            chosen = max(
                attempts,
                key=lambda a: (a.get("kept_noncritical_count", 0),
                               a["quality_score"], a["attempt"]),
            )
        else:
            chosen = attempts[-1]
        final_candidates = list(chosen.get("kept_noncritical") or [])
        rejected = list(chosen.get("critical_items") or [])
        regen_added = set(state.get("regen_added_titles") or [])
        regenerated_titles = [
            c.title for c in final_candidates if c.title in regen_added
        ]
        for item in rejected:
            logger.info(
                "langgraph reject candidate | parent_id=%s level=%d parent=%r "
                "title=%r reasons=%r decision=%s attempt=%d",
                state.get("parent_id"), state.get("target_level", 0),
                state.get("parent_factor") or "(top event)",
                item.get("title"), "; ".join(item.get("reasons") or []),
                decision, chosen["attempt"],
            )
        warnings = list(chosen.get("noncritical_warnings")
                        if chosen.get("noncritical_warnings") is not None
                        else chosen.get("warnings") or [])
        ai_returned = int(chosen.get("ai_returned", 0))
        final_outcome = classify_outcome(
            ai_returned=ai_returned,
            created=len(final_candidates),
            excluded=max(0, ai_returned - len(final_candidates)),
        )
        updates.update({
            "candidates": final_candidates,
            "rejected": rejected,
            "regenerated_titles": regenerated_titles,
            "quality_score": chosen["quality_score"],
            "warnings": warnings,
            "warning_count": len(warnings),
            "outcome": final_outcome,
            "has_critical_warning": final_outcome
            in ("all_excluded", "no_candidates"),
            "severity": SEVERITY_CRITICAL if rejected else (
                SEVERITY_WARNING if warnings else SEVERITY_OK
            ),
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
    decision: str = ""                      # accept / accept_with_warning / reject / fail_soft
    quality_score: float = 0.0              # 0–1 (avg kept overall_score / 100)
    warning_count: int = 0
    has_critical_warning: bool = False
    node_timings: list = field(default_factory=list)   # [(node, ms), …]
    # Step 3.5 fields (additive)
    severity: str = ""                      # ok / warning / critical (final)
    rejected: list = field(default_factory=list)
    # ``rejected``: [{"title":…, "reasons":[短いラベル,…]}, …] — critical
    # candidates dropped by the gate (never persisted; main.py counts them
    # as quality exclusions).
    regenerated_titles: list = field(default_factory=list)
    # final candidates that were produced by a regeneration attempt (main.py
    # marks their warning_flags so the CSV can tell regenerated factors apart)


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
    parent_id: Optional[int] = None,
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
        "level=%d parent_id=%s parent=%r",
        quality_gate, quality_threshold, max_retries,
        target_level, parent_id, parent_factor or "(top event)",
    )
    t_run = time.perf_counter()

    graph = get_compiled_graph()
    initial: GenerationState = {
        "analysis_title": analysis_title,
        "top_event": top_event,
        "target_level": target_level,
        "parent_id": parent_id,
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
        "severity": "",
        "critical_count": 0,
        "critical_items": [],
        "regen_keep": [],
        "regen_added_titles": [],
        "decision_basis": "",
        "rejected": [],
        "regenerated_titles": [],
        "_generate_fn": generate_fn,
    }
    final = graph.invoke(initial)

    elapsed_ms = int((time.perf_counter() - t_run) * 1000)
    node_timings = list(final.get("node_timings") or [])
    logger.info(
        "langgraph run summary | parent_id=%s level=%d decision=%s severity=%s "
        "outcome=%s quality_gate=%s quality_score=%.2f warnings=%d critical=%s "
        "regenerated=%s retry_count=%d rejected=%d regen_titles=%r "
        "elapsed_ms=%d node_ms=%s",
        parent_id, target_level, final.get("decision", ""),
        final.get("severity", "") or "-", final.get("outcome", ""),
        quality_gate, final.get("quality_score", 0.0),
        final.get("warning_count", 0),
        final.get("has_critical_warning", False),
        bool(final.get("regenerated", False)), int(final.get("retry_count", 0)),
        len(final.get("rejected") or []),
        "; ".join(final.get("regenerated_titles") or []),
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
        severity=final.get("severity", ""),
        rejected=list(final.get("rejected") or []),
        regenerated_titles=list(final.get("regenerated_titles") or []),
    )
