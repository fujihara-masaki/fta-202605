"""
Unit tests for the Step 3 quality-gate additions to the LangGraph workflow.

Same scripted-generate_fn approach as test_generation_workflow.py: no LLM is
needed, the provider call returns the next scripted list on each call.

Covered here (Step 3 acceptance criteria):
  - gate OFF keeps Step 2-1 behaviour (created accepted without regeneration)
  - gate ON + low-quality kept candidates → regenerate branch is taken
  - gate ON + retry budget spent → fail_soft (best attempt returned, no raise)
  - structurally invalid candidates (Pydantic) → warning / fail_soft, no raise
  - provider exception → error captured, decision fail_soft, no raise
  - config parsing for the new environment variables
"""

from app.services import generation_config
from app.services.ai_provider import GeneratedFactor
from app.services.generation_workflow import WorkflowResult, run_generation_workflow
from app.services.llm_models import validate_candidate_structure

GOOD = ("証明書の有効期限切れ", "TLS証明書の有効期限が切れていないか確認する")
GOOD2 = ("DNS応答の遅延", "DNSサーバの応答時間が劣化していないか確認する")
PARENT = "認証基盤の問題"
PARAPHRASE = (PARENT, "認証基盤に問題がある可能性")  # excluded as parent paraphrase
# Kept but warned:「汎用的すぎる要因名」→ specificity penalty → score 91/100.
GENERIC = ("確認不足", "作業前後の確認が実施されていないか確認する")


def _f(title, desc):
    return GeneratedFactor(title=title, description=desc, rationale="r", check_points=[])


class _ScriptedGen:
    """Callable generate_fn returning the next scripted list per call."""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls = 0

    def __call__(self, extra_existing):
        idx = min(self.calls, len(self.scripts) - 1)
        self.calls += 1
        return [_f(t, d) for (t, d) in self.scripts[idx]]


def _run(scripts, *, parent_factor=PARENT, max_retries=1,
         quality_gate=False, quality_threshold=0.7, factors=None):
    gen = _ScriptedGen(scripts) if factors is None else factors
    result = run_generation_workflow(
        generate_fn=gen,
        parent_factor=parent_factor,
        parent_description="",
        existing_titles=[],
        all_titles=[],
        no_rated_titles=[],
        ancestor_factors=[],
        analysis_context={},
        factor_count=4,
        max_retries=max_retries,
        quality_gate=quality_gate,
        quality_threshold=quality_threshold,
    )
    return result, gen


# --- gate OFF: Step 2-1 parity ----------------------------------------------

def test_gate_off_created_is_accepted_without_regen():
    res, gen = _run([[GOOD, GOOD2]], quality_gate=False)
    assert res.decision == "accept"
    assert res.regenerated is False
    assert gen.calls == 1
    assert res.outcome == "created"


def test_gate_off_low_score_is_still_accepted():
    """Without the gate, a kept-but-warned candidate never triggers regen."""
    res, gen = _run([[GENERIC]], quality_gate=False, quality_threshold=0.95)
    assert res.decision == "accept"
    assert gen.calls == 1
    assert res.warning_count >= 1          # 汎用的すぎる要因名
    assert 0.0 < res.quality_score < 1.0


def test_gate_off_all_excluded_regenerates_then_fail_soft():
    res, gen = _run([[PARAPHRASE], [PARAPHRASE]], quality_gate=False)
    assert res.decision == "fail_soft"
    assert res.regenerated is True
    assert res.retry_count == 1
    assert gen.calls == 2
    assert res.outcome == "all_excluded"
    assert res.has_critical_warning is True


# --- gate ON: score-based regeneration --------------------------------------

def test_gate_on_high_quality_accepted_without_regen():
    res, gen = _run([[GOOD, GOOD2]], quality_gate=True, quality_threshold=0.7)
    assert res.decision == "accept"
    assert res.regenerated is False
    assert gen.calls == 1
    assert res.quality_score >= 0.7
    assert res.has_critical_warning is False


def test_gate_on_low_quality_triggers_regeneration():
    """Kept-but-low-scoring candidates now enter the regenerate branch."""
    res, gen = _run(
        [[GENERIC], [GOOD]], quality_gate=True, quality_threshold=0.95,
    )
    assert res.decision == "accept"        # second attempt clears the bar
    assert res.regenerated is True
    assert res.retry_count == 1
    assert gen.calls == 2
    assert [c.title for c in res.candidates] == [GOOD[0]]


def test_gate_on_retry_budget_spent_accepts_best_attempt_with_warning():
    """Both attempts below threshold → budget spent → the usable (non-critical)
    part of the best attempt is accepted with warning, not dropped."""
    res, gen = _run(
        [[GENERIC], [PARAPHRASE]], quality_gate=True,
        quality_threshold=0.95, max_retries=1,
    )
    assert res.decision == "accept_with_warning"
    assert res.regenerated is True
    assert gen.calls == 2
    # Attempt 0 kept the generic candidate; attempt 1 kept nothing → best is 0.
    assert [c.title for c in res.candidates] == [GENERIC[0]]
    assert res.quality_score > 0.0
    assert res.error is None               # graded accept, not an exception


def test_gate_on_critical_warning_regenerates():
    res, gen = _run([[PARAPHRASE], [GOOD]], quality_gate=True)
    assert res.decision == "accept"
    assert res.regenerated is True
    assert gen.calls == 2
    assert res.outcome == "created"


# --- structure validation (Pydantic) -----------------------------------------

def test_structure_invalid_candidate_becomes_warning_not_exception():
    """Empty-title candidate is dropped with a warning; the good one is kept."""
    res, gen = _run([[("", "説明のみで名前がない"), GOOD]], quality_gate=False)
    assert res.decision == "accept"
    assert [c.title for c in res.candidates] == [GOOD[0]]
    assert res.warning_count >= 1
    assert res.error is None


def test_all_structure_invalid_ends_reject_without_exception():
    res, gen = _run(
        [[("", "名前なし")], [("", "また名前なし")]],
        quality_gate=True, max_retries=1,
    )
    # Budget spent and no usable candidate in any attempt → graded reject.
    assert res.decision == "reject"
    assert res.candidates == []
    assert res.has_critical_warning is True
    assert res.error is None
    assert res.outcome == "all_excluded"   # returned but rejected ≠ no_candidates


def test_validate_candidate_structure_never_raises():
    valid, errors = validate_candidate_structure(
        [_f(*GOOD), object(), _f("", "x")]
    )
    assert [c.title for c in valid] == [GOOD[0]]
    assert len(errors) == 2


# --- provider exception / error-vs-fallback contract --------------------------

class _FlakyGen:
    """Succeeds on scripted calls, raises once the script is exhausted."""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls = 0

    def __call__(self, extra_existing):
        idx = self.calls
        self.calls += 1
        if idx >= len(self.scripts):
            raise RuntimeError("provider down")
        return [_f(t, d) for (t, d) in self.scripts[idx]]


def test_provider_exception_is_fail_soft_with_error():
    """Initial generation fails → no usable attempt → error survives so
    main.py can fall back to the legacy path."""
    def boom(extra_existing):
        raise RuntimeError("provider down")

    res, _ = _run([], quality_gate=True, factors=boom)
    assert isinstance(res, WorkflowResult)
    assert res.error == "provider down"
    assert res.decision == "fail_soft"
    assert res.candidates == []


def test_regen_failure_with_usable_attempt_recovers_as_fail_soft():
    """Provider dies during regeneration but attempt 0 kept a candidate →
    normal fail_soft result with that attempt, error cleared (no legacy
    fallback / no regeneration from scratch in main.py)."""
    gen = _FlakyGen([[GENERIC]])           # call 1 ok, call 2 raises
    res, _ = _run([], quality_gate=True, quality_threshold=0.95, factors=gen)
    assert gen.calls == 2
    assert res.error is None
    assert res.decision == "fail_soft"
    assert res.regenerated is True
    assert [c.title for c in res.candidates] == [GENERIC[0]]


def test_regen_failure_without_usable_attempt_keeps_error():
    """Attempt 0 was all-excluded and the regeneration call fails → nothing
    usable exists, so the error survives and main.py falls back."""
    gen = _FlakyGen([[PARAPHRASE]])        # call 1 all-excluded, call 2 raises
    res, _ = _run([], quality_gate=False, factors=gen)
    assert gen.calls == 2
    assert res.error == "provider down"
    assert res.decision == "fail_soft"


# --- attempts record (Step 4 partial-regeneration groundwork) -----------------

def test_attempt_record_keeps_partial_regen_info():
    from app.services.generation_workflow import evaluate_quality

    state = {
        "candidates": [_f(*GOOD), _f(*PARAPHRASE)],
        "parent_factor": PARENT,
        "parent_description": "",
        "all_titles": [],
        "no_rated_titles": [],
        "ancestor_factors": [],
        "ai_returned": 2,
        "retry_count": 0,
        "attempts": [],
    }
    updates = evaluate_quality(state)
    (rec,) = updates["attempts"]
    assert rec["kept_titles"] == [GOOD[0]]
    assert rec["excluded_titles"] == [PARAPHRASE[0]]
    assert rec["reasons"] == ["親要因の言い換え"]
    assert rec["kept_count"] == 1
    assert rec["warning_count"] == len(rec["warnings"])
    assert rec["outcome"] == "partial"


# --- observability ------------------------------------------------------------

def test_node_timings_recorded_per_node():
    res, gen = _run([[GOOD]], quality_gate=True)
    names = [n for n, _ in res.node_timings]
    assert names[:4] == [
        "generate_candidates", "validate_structure",
        "evaluate_quality", "decide_next_action",
    ]
    assert names[-1] == "finalize_result"
    assert all(ms >= 0 for _, ms in res.node_timings)


def test_regeneration_loop_records_nodes_twice():
    res, _ = _run([[PARAPHRASE], [GOOD]], quality_gate=True)
    names = [n for n, _ in res.node_timings]
    assert names.count("validate_structure") == 2
    assert names.count("evaluate_quality") == 2
    assert names.count("regenerate_candidates") == 1


# --- config parsing -----------------------------------------------------------

def test_quality_gate_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_LANGGRAPH_QUALITY_GATE", raising=False)
    assert generation_config.langgraph_quality_gate_enabled() is False


def test_quality_gate_env_true(monkeypatch):
    monkeypatch.setenv("ENABLE_LANGGRAPH_QUALITY_GATE", "true")
    assert generation_config.langgraph_quality_gate_enabled() is True


def test_quality_threshold_default(monkeypatch):
    monkeypatch.delenv("LANGGRAPH_QUALITY_THRESHOLD", raising=False)
    assert generation_config.langgraph_quality_threshold() == 0.7


def test_quality_threshold_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_QUALITY_THRESHOLD", "not-a-number")
    assert generation_config.langgraph_quality_threshold() == 0.7


def test_quality_threshold_clamped(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_QUALITY_THRESHOLD", "1.5")
    assert generation_config.langgraph_quality_threshold() == 1.0
    monkeypatch.setenv("LANGGRAPH_QUALITY_THRESHOLD", "-0.2")
    assert generation_config.langgraph_quality_threshold() == 0.0


def test_workflow_reads_gate_from_env_when_not_passed(monkeypatch):
    """quality_gate=None → environment decides (default off → accept)."""
    monkeypatch.setenv("ENABLE_LANGGRAPH_QUALITY_GATE", "true")
    monkeypatch.setenv("LANGGRAPH_QUALITY_THRESHOLD", "0.95")
    gen = _ScriptedGen([[GENERIC], [GOOD]])
    res = run_generation_workflow(
        generate_fn=gen,
        parent_factor=PARENT,
        parent_description="",
        existing_titles=[],
        all_titles=[],
        no_rated_titles=[],
        ancestor_factors=[],
        analysis_context={},
        factor_count=4,
        max_retries=1,
    )
    assert res.regenerated is True
    assert res.decision == "accept"
